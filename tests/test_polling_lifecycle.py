"""Exercise PTB's real polling/shutdown lifecycle without external services.

Run with: python -W error::RuntimeWarning -m unittest discover -s tests -v
"""

import asyncio
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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
    with patch.dict("sys.modules", {"config": config, "database": database}):
        spec.loader.exec_module(module)
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
            return original_builder().request(request).get_updates_request(request).job_queue(None)

        async def post_init(app):
            applications.append(app)
            requests[-1].app = app

        # Reproduce the exact precondition from Render: the previous attempt
        # left a closed event loop installed in the main thread.
        stale_loop = asyncio.new_event_loop()
        stale_loop.close()
        asyncio.set_event_loop(stale_loop)
        with patch.object(Application, "builder", side_effect=builder), \
                patch.object(bot, "post_init", post_init), \
                patch.object(bot.time, "sleep") as sleep:
            bot.run_bot()

        self.assertEqual(len(applications), 2)
        self.assertIsNot(loops[0], loops[1])
        sleep.assert_called_once_with(15)
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

        def attempt():
            loops.append(asyncio.get_event_loop())
            if len(loops) == 1:
                raise NetworkError("offline")
            loops[-1].run_until_complete(asyncio.sleep(0))

        with patch.object(bot, "main", side_effect=attempt), \
                patch.object(bot.time, "sleep") as sleep:
            bot.run_bot()
        self.assertEqual(len(loops), 2)
        self.assertIsNot(loops[0], loops[1])
        sleep.assert_called_once_with(15)
        self.assert_loops_closed(loops)

    def test_exhausted_retries_raise_and_do_not_sleep_again(self):
        loops = []

        def attempt():
            loops.append(asyncio.get_event_loop())
            raise Conflict("another instance")

        with patch.object(bot, "main", side_effect=attempt), \
                patch.object(bot.time, "sleep") as sleep:
            with self.assertRaises(Conflict):
                bot.run_bot(max_poll_retries=2)
        self.assertEqual(len(loops), 2)
        sleep.assert_called_once_with(15)
        self.assert_loops_closed(loops)

    def test_fatal_error_closes_loop_without_retry(self):
        loops = []

        def attempt():
            loops.append(asyncio.get_event_loop())
            raise ValueError("bad configuration")

        with patch.object(bot, "main", side_effect=attempt), \
                patch.object(bot.time, "sleep") as sleep:
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

        def attempt():
            loop = asyncio.get_event_loop()
            loops.append(loop)
            loop.create_task(background())
            loop.run_until_complete(asyncio.sleep(0))

        with patch.object(bot, "main", side_effect=attempt):
            bot.run_bot()
        finished.assert_awaited_once()
        self.assert_loops_closed(loops)


if __name__ == "__main__":
    unittest.main()
