"""Health and Mongo lease tests; all Mongo data stays in memory."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import json
import logging
import os
import signal
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import mongomock
from pymongo.errors import ConnectionFailure
from telegram.ext import ExtBot

from test_polling_lifecycle import bot


class HealthTests(unittest.TestCase):
    def test_health_allows_render_handoff_while_standby(self):
        bot.RUNTIME_STATE["polling"] = "standby"
        with bot.HealthServer(0) as server:
            self.assertEqual(server.server.server_address[0], "0.0.0.0")
            connection = HTTPConnection("127.0.0.1", server.server.server_port, timeout=5)
            try:
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), {"status": "ok", "polling": "standby"})
                connection.request("GET", "/readyz")
                response = connection.getresponse()
                self.assertEqual(response.status, 503)
                response.read()
                bot.RUNTIME_STATE["polling"] = "active"
                connection.request("HEAD", "/readyz")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"")
                connection.request("GET", "/anything-else")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
            finally:
                connection.close()
        self.assertFalse(server.thread.is_alive())
        self.assertEqual(server.server.fileno(), -1)

    def test_health_is_optional_for_worker(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(bot, "HealthServer") as server:
            with bot.health_endpoint() as endpoint:
                self.assertIsNone(endpoint)
        server.assert_not_called()

    def test_health_uses_render_port(self):
        with patch.dict(os.environ, {"PORT": "10000"}), patch.object(bot, "HealthServer") as server:
            with bot.health_endpoint():
                pass
        server.assert_called_once_with(10000)

    def test_signal_interrupts_standby_and_restores_handler(self):
        event = threading.Event()
        previous = signal.getsignal(signal.SIGTERM)
        timer = threading.Timer(0.05, os.kill, args=(os.getpid(), signal.SIGTERM))
        timer.start()
        try:
            self.assertTrue(bot.wait_for_shutdown(2, event))
        finally:
            timer.join()
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_http_logs_do_not_expose_token(self):
        record = logging.LogRecord("httpx", logging.WARNING, "test", 1,
                                   "POST https://api.telegram.org/bot%s/getUpdates", (bot.BOT_TOKEN,), None)
        formatted = bot.TokenRedactingFormatter().format(record)
        self.assertNotIn(bot.BOT_TOKEN, formatted)
        self.assertIn("[REDACTED]", formatted)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.collection = mongomock.MongoClient(tz_aware=True).test.bot_runtime
        self.first = bot.PollingLease(self.collection, "123456")
        self.second = bot.PollingLease(self.collection, "123456")

    def test_only_one_instance_can_acquire_and_release_is_owner_scoped(self):
        self.assertTrue(self.first.acquire())
        self.assertFalse(self.second.acquire())
        self.second.release()
        self.assertTrue(self.first.renew())
        self.first.release()
        self.assertTrue(self.second.acquire())

    def test_simultaneous_acquisitions_have_one_winner(self):
        leases = [bot.PollingLease(self.collection, "123456") for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda lease: lease.acquire(), leases))
        self.assertEqual(sum(results), 1)

    def test_crashed_owner_expires_and_cannot_renew_or_delete_successor(self):
        self.assertTrue(self.first.acquire())
        self.collection.update_one({"_id": self.first.key}, {"$set": {
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        }})
        self.assertFalse(self.first.renew())
        self.assertTrue(self.second.acquire())
        self.assertFalse(self.first.renew())
        self.first.release()
        self.assertTrue(self.second.renew())

    def test_other_bot_ids_have_independent_leases(self):
        self.assertTrue(self.first.acquire())
        self.assertTrue(bot.PollingLease(self.collection, "654321").acquire())

    def test_get_updates_never_reaches_telegram_without_ownership(self):
        for renewal in (False, ConnectionFailure("offline")):
            with self.subTest(renewal=renewal):
                lease = MagicMock()
                if isinstance(renewal, Exception):
                    lease.renew.side_effect = renewal
                else:
                    lease.renew.return_value = renewal
                client = bot.SinglePollerBot("123456:offline-test-token", lease)
                with patch.object(ExtBot, "get_updates", new_callable=AsyncMock) as outbound:
                    with self.assertRaises(bot.PollingLeaseLost):
                        asyncio.run(client.get_updates(timeout=10))
                    outbound.assert_not_called()

    def test_get_updates_renews_before_every_request_including_cleanup(self):
        lease = MagicMock()
        lease.renew.return_value = True
        client = bot.SinglePollerBot("123456:offline-test-token", lease)
        with patch.object(ExtBot, "get_updates", new_callable=AsyncMock, return_value=[]) as outbound:
            asyncio.run(client.get_updates(timeout=10))
            asyncio.run(client.get_updates(timeout=0))
        self.assertEqual(lease.renew.call_count, 2)
        self.assertEqual(outbound.await_count, 2)

    def test_render_handoff_stays_healthy_until_old_owner_releases(self):
        self.assertTrue(self.first.acquire())
        servers = []

        @contextmanager
        def health_endpoint():
            with bot.HealthServer(0) as server:
                servers.append(server)
                yield server

        def retire_old_instance(seconds, event):
            self.assertEqual(bot.RUNTIME_STATE["polling"], "standby")
            main.assert_not_called()
            connection = HTTPConnection("127.0.0.1", servers[0].server.server_port, timeout=5)
            try:
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
            finally:
                connection.close()
            # Render can now retire the old deployment and release ownership.
            self.first.release()
            return False

        with patch.object(bot, "PollingLease", return_value=self.second), \
                patch.object(bot, "health_endpoint", health_endpoint), \
                patch.object(bot, "wait_for_shutdown", side_effect=retire_old_instance), \
                patch.object(bot, "main") as main:
            bot.run_bot(max_poll_retries=1)
        main.assert_called_once_with(polling_lease=self.second)
        self.assertIsNone(self.collection.find_one({"_id": self.first.key}))
        self.assertFalse(servers[0].thread.is_alive())


if __name__ == "__main__":
    unittest.main()
