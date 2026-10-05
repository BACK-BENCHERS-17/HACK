"""Exercise PTB's real polling/shutdown lifecycle without external services.

Run with: python -W error::RuntimeWarning -m unittest discover -s tests -v
"""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import ANY, AsyncMock, MagicMock, patch

from telegram.error import Conflict, NetworkError
from telegram.ext import Application
from telegram.request import BaseRequest


def load_bot():
    # bot.py constructs the database at import time. Replace that dependency
    # and config so the regression tests cannot touch a real DB or bot token.
    config = types.ModuleType("config")
    config.BOT_TOKEN = "123456:offline-test-token"
    config.ADMIN_IDS = [1]
    database = types.ModuleType("database")
    database.DatabaseManager = MagicMock()
    spec = importlib.util.spec_from_file_location(
        "bot_under_test", Path(__file__).resolve().parents[1] / "bot.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Restore only our two injected modules. patch.dict(sys.modules) also
    # removes dependencies imported by bot.py, causing duplicate SDK/Pillow
    # module instances (and mocks attached to the wrong GmailService class).
    originals = {name: sys.modules.get(name) for name in ("config", "database")}
    sys.modules.update(config=config, database=database)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module


bot = load_bot()


class OfflineTelegramRequest(BaseRequest):
    """Simulate Telegram responses while retaining PTB's actual updater."""

    def __init__(self, conflict=False):
        self.conflict = conflict
        self.app = None
        self.shutdown_calls = 0
        self.poll_calls = 0
        self.dropped_updates = []

    @property
    def read_timeout(self):
        return 5

    async def initialize(self):
        pass

    async def shutdown(self):
        self.shutdown_calls += 1

    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        if endpoint == "getMe":
            result = {"id": 123456, "is_bot": True, "first_name": "Test", "username": "test_bot"}
        elif endpoint == "deleteWebhook":
            self.dropped_updates.append(request_data.parameters.get("drop_pending_updates"))
            result = True
        elif endpoint == "getUpdates":
            if request_data.parameters.get("timeout", 0):
                while not self.app.running:
                    await asyncio.sleep(0)
                self.poll_calls += 1
                if self.conflict:
                    self.conflict = False
                    return 409, json.dumps({
                        "ok": False, "error_code": 409,
                        "description": "Conflict: terminated by other getUpdates request",
                    }).encode()
                # Simulate a clean stop once the next instance is polling.
                asyncio.get_running_loop().call_soon(self.app.stop_running)
                await asyncio.sleep(0)
            result = []
        else:
            raise AssertionError(f"Unexpected Telegram endpoint: {endpoint}")
        return 200, json.dumps({"ok": True, "result": result}).encode()


class PollingLifecycleTests(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(None)
        self.lease = MagicMock()
        self.lease.acquire.return_value = True
        self.lease.renew.return_value = True
        lease_patch = patch.object(bot, "PollingLease", return_value=self.lease)
        lease_patch.start()
        self.addCleanup(lease_patch.stop)
        health_patch = patch.object(bot, "health_endpoint")
        health_patch.start()
        self.addCleanup(health_patch.stop)

    def assert_loops_closed(self, loops):
        for loop in loops:
            self.assertTrue(loop.is_closed())
            self.assertFalse(asyncio.all_tasks(loop))
        with self.assertRaises(RuntimeError):
            asyncio.get_event_loop()

    def test_real_ptb_conflict_then_success_uses_fresh_loop(self):
        original_builder = Application.builder
        applications, requests, loops = [], [], []

        def builder():
            loop = asyncio.get_event_loop()
            self.assertFalse(loop.is_closed())
            loops.append(loop)
            request = OfflineTelegramRequest(conflict=not applications)
            requests.append(request)
            return original_builder().job_queue(None)

        original_bot = bot.SinglePollerBot

        def offline_bot(token, lease):
            return original_bot(token, lease, request=requests[-1], get_updates_request=requests[-1])

        async def post_init(app):
            applications.append(app)
            requests[-1].app = app

        # Reproduce the exact precondition from Render: the previous attempt
        # left a closed event loop installed in the main thread.
        stale_loop = asyncio.new_event_loop()
        stale_loop.close()
        asyncio.set_event_loop(stale_loop)
        with patch.object(Application, "builder", side_effect=builder), \
                patch.object(bot, "SinglePollerBot", side_effect=offline_bot), \
                patch.object(bot, "post_init", post_init), \
                patch.object(bot, "wait_for_shutdown", return_value=False) as sleep:
            bot.run_bot()

        self.assertEqual(len(applications), 2)
        self.assertIsNot(loops[0], loops[1])
        sleep.assert_called_once_with(15, ANY)
        self.assertEqual(self.lease.release.call_count, 2)
        self.assertGreater(self.lease.renew.call_count, 0)
        for app, request in zip(applications, requests):
            self.assertFalse(app.running)
            self.assertFalse(app.updater.running)
            self.assertGreater(request.shutdown_calls, 0)
            self.assertGreater(request.poll_calls, 0)
            self.assertTrue(request.dropped_updates)
            self.assertFalse(any(request.dropped_updates))
        self.assert_loops_closed(loops)

    def test_network_failure_during_startup_gets_new_loop(self):
        loops = []

        def attempt(**kwargs):
            loops.append(asyncio.get_event_loop())
            if len(loops) == 1:
                raise NetworkError("offline")
            loops[-1].run_until_complete(asyncio.sleep(0))

        with patch.object(bot, "main", side_effect=attempt), \
                patch.object(bot, "wait_for_shutdown", return_value=False) as sleep:
            bot.run_bot()
        self.assertEqual(len(loops), 2)
        self.assertIsNot(loops[0], loops[1])
        sleep.assert_called_once_with(15, ANY)
        self.assert_loops_closed(loops)

    def test_exhausted_retries_raise_and_do_not_sleep_again(self):
        loops = []

        def attempt(**kwargs):
            loops.append(asyncio.get_event_loop())
            raise Conflict("another instance")

        with patch.object(bot, "main", side_effect=attempt), \
                patch.object(bot, "wait_for_shutdown", return_value=False) as sleep:
            with self.assertRaises(Conflict):
                bot.run_bot(max_poll_retries=2)
        self.assertEqual(len(loops), 2)
        sleep.assert_called_once_with(15, ANY)
        self.assert_loops_closed(loops)

    def test_fatal_error_closes_loop_without_retry(self):
        loops = []

        def attempt(**kwargs):
            loops.append(asyncio.get_event_loop())
            raise ValueError("bad configuration")

        with patch.object(bot, "main", side_effect=attempt), \
                patch.object(bot, "wait_for_shutdown", return_value=False) as sleep:
            with self.assertRaises(ValueError):
                bot.run_bot()
        sleep.assert_not_called()
        self.assert_loops_closed(loops)

    def test_runner_cancels_remaining_tasks_on_shutdown(self):
        loops = []
        finished = AsyncMock()

        async def background():
            try:
                await asyncio.Event().wait()
            finally:
                await finished()

        def attempt(**kwargs):
            loop = asyncio.get_event_loop()
            loops.append(loop)
            loop.create_task(background())
            loop.run_until_complete(asyncio.sleep(0))

        with patch.object(bot, "main", side_effect=attempt):
            bot.run_bot()
        finished.assert_awaited_once()
        self.assert_loops_closed(loops)

    def test_waits_for_owner_before_building_telegram_application(self):
        self.lease.acquire.side_effect = [False, False, True]
        with patch.object(bot, "main") as main, \
                patch.object(bot, "wait_for_shutdown", return_value=False) as wait:
            bot.run_bot(max_poll_retries=1)
        self.assertEqual(wait.call_count, 2)
        main.assert_called_once_with(polling_lease=self.lease)
        self.lease.release.assert_called_once()

    def test_shutdown_while_in_standby_never_polls_or_releases_other_owner(self):
        self.lease.acquire.return_value = False
        with patch.object(bot, "main") as main, \
                patch.object(bot, "wait_for_shutdown", return_value=True):
            bot.run_bot()
        main.assert_not_called()
        self.lease.release.assert_not_called()

    def test_lost_lease_reacquires_before_restart(self):
        with patch.object(bot, "main", side_effect=[bot.PollingLeaseLost("lost"), None]) as main, \
                patch.object(bot, "wait_for_shutdown", return_value=False):
            bot.run_bot(max_poll_retries=1)
        self.assertEqual(main.call_count, 2)
        self.assertEqual(self.lease.acquire.call_count, 2)
        self.assertEqual(self.lease.release.call_count, 2)


if __name__ == "__main__":
    unittest.main()
