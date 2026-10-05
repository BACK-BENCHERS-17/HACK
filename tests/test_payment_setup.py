"""In-bot payment setup, encrypted persistence, and SDK reload regressions."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import importlib.util
import os
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import mongomock
from pymongo.errors import ConnectionFailure
from telegram.error import BadRequest
from telegram.ext import ConversationHandler

from payment_template.config import AppConfig
from payment_template.exceptions import GmailError
from payment_template.gmail import GmailMessage, GmailService
from payment_template.utils import utcnow
from test_polling_lifecycle import bot


PASSWORD = "abcdefghijklmnop"
CHECK_PAYMENT_STORAGE = bot._check_payment_storage


def database_type():
    config = types.ModuleType("config")
    config.MONGO_URI = "mongodb://unused"
    config.MONGO_DB_NAME = "test"
    spec = importlib.util.spec_from_file_location(
        "database_under_test", Path(__file__).resolve().parents[1] / "database.py"
    )
    module = importlib.util.module_from_spec(spec)
    original = sys.modules.get("config")
    sys.modules["config"] = config
    try:
        spec.loader.exec_module(module)
    finally:
        if original is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = original
    return module.DatabaseManager


DatabaseManager = database_type()


def update(text="", callback=None, owner=1, chat_type="private"):
    message = types.SimpleNamespace(
        text=text, reply_text=AsyncMock(), delete=AsyncMock(),
    )
    query = types.SimpleNamespace(
        data=callback, answer=AsyncMock(), from_user=types.SimpleNamespace(id=owner),
    ) if callback else None
    return types.SimpleNamespace(
        message=message, effective_message=message, callback_query=query,
        effective_user=types.SimpleNamespace(id=owner),
        effective_chat=types.SimpleNamespace(type=chat_type, id=owner),
    )


class PaymentSetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = DatabaseManager.__new__(DatabaseManager)
        self.manager.client = mongomock.MongoClient(tz_aware=True)
        self.manager.db = self.manager.client.test
        self.context = types.SimpleNamespace(user_data={})
        patches = [
            patch.object(bot, "db", self.manager),
            patch.object(bot, "_pm_singleton", None),
            patch.object(bot, "_pm_config_key", None),
            patch.object(bot, "_pm_last_error", ""),
            patch.object(bot, "_PM_AVAILABLE", True),
            patch.object(bot, "_check_payment_storage"),
            patch.dict(os.environ, {"MONGO_URI": "mongodb://unused", "MONGO_DB_NAME": "test"}, clear=True),
            patch("payment_template.config.load_dotenv"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    async def save_account(self, username="payments@gmail.com", password=PASSWORD):
        await self.manager.set_setting("payment_gmail", {
            "username": username,
            "password_enc": bot._payment_cipher().encrypt(password.encode()).decode(),
        })

    async def test_complete_setup_saves_encrypted_login_and_initializes_sdk(self):
        self.context.user_data["payment_setup_email"] = "payments@gmail.com"
        request = update("abcd efgh ijkl mnop")
        await self.manager.set_setting("upi_id", "store@fam")
        with patch.object(GmailService, "check_connection") as check, \
                patch.object(bot, "_ping_payment_database"):
            state = await bot.receive_payment_password(request, self.context)
        self.assertEqual(state, ConversationHandler.END)
        request.message.delete.assert_awaited_once()
        self.assertGreaterEqual(check.call_count, 1)
        record = await self.manager.get_setting("payment_gmail")
        self.assertEqual(record["username"], "payments@gmail.com")
        self.assertNotIn(PASSWORD, str(record))
        self.assertNotIn("payment_setup_email", self.context.user_data)
        self.assertNotIn(PASSWORD, str(request.message.reply_text.call_args_list))
        self.assertNotIn(PASSWORD, str(list(self.manager.db.admin_logs.find())))
        pm = await bot._get_pm()
        self.assertIsNotNone(pm)
        self.assertEqual(pm._config.imap_username, "payments@gmail.com")
        self.assertEqual(pm._config.imap_app_password, PASSWORD)
        self.assertNotIn(PASSWORD, repr(pm._config))

        # A new process loads the same saved credentials without IMAP env vars.
        bot._pm_singleton = None
        bot._pm_config_key = None
        restarted = await bot._get_pm()
        self.assertIsNot(restarted, pm)
        self.assertEqual(restarted._config.imap_app_password, PASSWORD)

    async def test_invalid_or_failed_login_keeps_previous_account(self):
        await self.save_account()
        original = await self.manager.get_setting("payment_gmail")
        self.context.user_data["payment_setup_email"] = "replacement@gmail.com"
        invalid = update("not-an-app-password")
        with patch.object(GmailService, "check_connection") as check:
            self.assertEqual(await bot.receive_payment_password(invalid, self.context), bot.WAIT_FOR_PAYMENT_PASSWORD)
        check.assert_not_called()
        request = update(PASSWORD)
        with patch.object(GmailService, "check_connection", side_effect=GmailError("Login failed")):
            self.assertEqual(await bot.receive_payment_password(request, self.context), bot.WAIT_FOR_PAYMENT_PASSWORD)
        self.assertEqual(await self.manager.get_setting("payment_gmail"), original)
        self.assertNotIn(PASSWORD, str(request.message.reply_text.call_args_list))

    async def test_owner_and_private_chat_required_on_every_setup_step(self):
        handlers = [
            bot.show_payment_session, bot.prompt_payment_gmail, bot.receive_payment_email,
            bot.receive_payment_password, bot.prompt_set_upi, bot.receive_set_upi,
            bot.prompt_payment_payee, bot.receive_payment_payee,
            bot.prompt_payment_mailbox, bot.receive_payment_mailbox, bot.cancel_payment_setup,
        ]
        for handler in handlers:
            for owner, chat_type in ((2, "private"), (1, "group")):
                with self.subTest(handler=handler.__name__, owner=owner, chat=chat_type):
                    request = update(PASSWORD, callback="forged", owner=owner, chat_type=chat_type)
                    result = await handler(request, self.context)
                    self.assertEqual(result, ConversationHandler.END)
                    request.callback_query.answer.assert_awaited_once()
        self.assertEqual(self.manager.db.settings.count_documents({}), 0)

    async def test_cancel_clears_partial_account_without_changing_saved_credentials(self):
        await self.save_account()
        original = await self.manager.get_setting("payment_gmail")
        self.context.user_data["payment_setup_email"] = "not-saved@gmail.com"
        with patch.object(bot, "show_payment_session", new_callable=AsyncMock):
            await bot.cancel_payment_setup(update("/cancel"), self.context)
        self.assertNotIn("payment_setup_email", self.context.user_data)
        self.assertEqual(await self.manager.get_setting("payment_gmail"), original)

    async def test_failed_db_save_remains_retryable(self):
        self.context.user_data["payment_setup_email"] = "payments@gmail.com"
        with patch.object(GmailService, "check_connection"), \
                patch.object(self.manager, "set_setting", new_callable=AsyncMock, side_effect=RuntimeError("offline")):
            self.assertEqual(await bot.receive_payment_password(update(PASSWORD), self.context), bot.WAIT_FOR_PAYMENT_PASSWORD)
        self.assertIsNone(await self.manager.get_setting("payment_gmail", None))
        self.assertEqual(self.context.user_data["payment_setup_email"], "payments@gmail.com")

    async def test_password_message_delete_failure_does_not_block_setup(self):
        self.context.user_data["payment_setup_email"] = "payments@gmail.com"
        request = update(PASSWORD)
        request.message.delete.side_effect = BadRequest("message cannot be deleted")
        with patch.object(GmailService, "check_connection"), \
                patch.object(bot, "show_payment_session", new_callable=AsyncMock):
            await bot.receive_payment_password(request, self.context)
        self.assertIsNotNone(await self.manager.get_setting("payment_gmail", None))

    async def test_panel_shows_upi_and_gmail_even_when_sdk_cannot_initialize(self):
        await self.manager.set_setting("upi_id", "store@fam")
        await self.manager.set_setting("payment_gmail", {"username": "payments@gmail.com", "password_enc": "broken"})
        request = update(callback="admin_svc_session")
        with patch.object(bot, "safe_edit_text", new_callable=AsyncMock) as edit, \
                patch.object(bot, "_ping_payment_database"):
            await bot.show_payment_session(request, self.context)
        text = edit.call_args.args[2]
        self.assertIn("store@fam", text)
        self.assertIn("payments@gmail.com", text)
        self.assertIn("NOT INITIALIZED", text)
        self.assertIn("Connect / Change Gmail", text)
        self.assertIn("CONNECTED", text)  # DB status is independent of SDK/Gmail.

    async def test_index_failure_keeps_real_bot_database_connected_on_each_refresh(self):
        await self.save_account()
        await self.manager.set_setting("upi_id", "store@fam")
        pm = await bot._get_pm()
        pm._repository._db = self.manager.db
        # Reproduce a real unique-index failure in an otherwise live database.
        self.manager.db.orders.insert_many([{"id": "duplicate"}, {"id": "duplicate"}])
        request = update(callback="admin_svc_session")
        with patch.object(bot, "safe_edit_text", new_callable=AsyncMock) as edit, \
                patch.object(GmailService, "check_connection"), \
                patch.object(bot, "_check_payment_storage", wraps=CHECK_PAYMENT_STORAGE):
            for _ in range(2):
                await bot.show_payment_session(request, self.context)
                text = edit.call_args.args[2]
                self.assertIn("<b>MongoDB:</b> " + bot.ce("success") + " CONNECTED", text)
                self.assertIn("<b>Payment storage:</b> " + bot.ce("fail") + " CHECK FAILED", text)
                self.assertNotIn("Ready for payment verification", text)
                self.assertFalse(pm._repository._indexes_ready)

            # Once the duplicate is fixed, the SDK must retry its indexes.
            duplicate = self.manager.db.orders.find_one({"id": "duplicate"})
            self.manager.db.orders.delete_one({"_id": duplicate["_id"]})
            await bot.show_payment_session(request, self.context)
            text = edit.call_args.args[2]
            self.assertIn("<b>MongoDB:</b> " + bot.ce("success") + " CONNECTED", text)
            self.assertIn("<b>Payment storage:</b> " + bot.ce("success") + " READY", text)
            self.assertIn("Ready for payment verification", text)
            self.assertTrue(pm._repository._indexes_ready)

    async def test_missing_gmail_does_not_hide_working_database(self):
        request = update(callback="admin_svc_session")
        with patch.object(bot, "safe_edit_text", new_callable=AsyncMock) as edit, \
                patch.object(bot, "_check_payment_storage") as storage:
            await bot.show_payment_session(request, self.context)
        text = edit.call_args.args[2]
        self.assertIn("NOT INITIALIZED", text)
        self.assertIn("<b>MongoDB:</b> " + bot.ce("success") + " CONNECTED", text)
        self.assertIn("<b>Payment storage:</b> NOT CHECKED", text)
        storage.assert_not_called()

    async def test_real_connection_failure_still_reports_disconnected(self):
        request = update(callback="admin_svc_session")
        with patch.object(bot, "safe_edit_text", new_callable=AsyncMock) as edit, \
                patch.object(self.manager.db, "command", side_effect=ConnectionFailure("offline")):
            await bot.show_payment_session(request, self.context)
        text = edit.call_args.args[2]
        self.assertIn("<b>MongoDB:</b> " + bot.ce("fail") + " DISCONNECTED", text)
        self.assertIn("Bot database connection check failed.", text)

    async def test_credentials_work_before_upi_is_set(self):
        self.context.user_data["payment_setup_email"] = "payments@gmail.com"
        with patch.object(GmailService, "check_connection"), \
                patch.object(bot, "_ping_payment_database"):
            await bot.receive_payment_password(update(PASSWORD), self.context)
        self.assertIsNotNone(await self.manager.get_setting("payment_gmail", None))
        self.assertIsNone(await bot._get_pm())
        self.assertIn("DEFAULT_UPI_ID", bot._pm_last_error)

    async def test_saved_credentials_override_env_and_rotated_token_requires_reconnect(self):
        await self.save_account()
        with patch.dict(os.environ, {"IMAP_USERNAME": "old@gmail.com", "IMAP_APP_PASSWORD": "old-password"}):
            settings = await bot._payment_settings()
            self.assertEqual(settings["imap_username"], "payments@gmail.com")
            self.assertEqual(settings["imap_app_password"], PASSWORD)
            with patch.object(bot, "BOT_TOKEN", "123456:rotated"):
                changed = await bot._payment_settings()
                self.assertEqual(changed["imap_app_password"], "")
                self.assertIn("Connect / Change Gmail", changed["credentials_error"])

    async def test_env_fallback_is_preserved_until_account_is_saved(self):
        with patch.dict(os.environ, {
            "IMAP_USERNAME": "env@gmail.com", "IMAP_APP_PASSWORD": "abcd efgh ijkl mnop",
            "DEFAULT_UPI_ID": "env@fam", "DEFAULT_PAYEE_NAME": "Env Store",
        }):
            settings = await bot._payment_settings()
            self.assertEqual(settings["imap_app_password"], PASSWORD)
            self.assertEqual(settings["upi_id"], "env@fam")
            self.assertIsNotNone(await bot._get_pm())

    async def test_sdk_reload_after_upi_payee_mailbox_and_gmail_changes(self):
        await self.save_account()
        await self.manager.set_setting("upi_id", "first@fam")
        first = await bot._get_pm()
        self.assertIs(await bot._get_pm(), first)
        await self.save_account("new@gmail.com", "ponmlkjihgfedcba")
        await self.manager.set_setting("upi_id", "second@fam")
        await self.manager.set_setting("global_brand_name", "New Store")
        await self.manager.set_setting("payment_imap_mailbox", "[Gmail]/All Mail")
        second = await bot._get_pm()
        self.assertIsNot(first, second)
        self.assertIs(first._repository, second._repository)
        self.assertEqual(first._config.imap_username, "payments@gmail.com")
        self.assertEqual(second._config.imap_username, "new@gmail.com")
        self.assertEqual(second._config.default_upi_id, "second@fam")
        self.assertEqual(second._config.default_payee_name, "New Store")
        self.assertEqual(second._config.imap_mailbox, "[Gmail]/All Mail")

    async def test_connection_check_runs_off_event_loop(self):
        await self.save_account()
        settings = await bot._payment_settings()
        threads = []
        def check(service):
            threads.append(threading.get_ident())
        with patch.object(GmailService, "check_connection", check):
            self.assertEqual(await bot._check_payment_gmail(settings), (True, ""))
        self.assertNotEqual(threads[0], threading.get_ident())

    async def test_input_validation_and_successful_upi_payee_mailbox_save(self):
        for handler, invalid, state in (
            (bot.receive_payment_email, "bad", bot.WAIT_FOR_PAYMENT_EMAIL),
            (bot.receive_set_upi, "bad", bot.WAIT_FOR_SETTING_UPI),
            (bot.receive_payment_payee, "", bot.WAIT_FOR_PAYMENT_PAYEE),
            (bot.receive_payment_mailbox, "a\nb", bot.WAIT_FOR_PAYMENT_MAILBOX),
        ):
            self.assertEqual(await handler(update(invalid), self.context), state)
        self.assertEqual(self.manager.db.settings.count_documents({}), 0)
        self.assertEqual(await bot.receive_payment_email(update("New@Gmail.com"), self.context), bot.WAIT_FOR_PAYMENT_PASSWORD)
        self.assertEqual(self.context.user_data["payment_setup_email"], "new@gmail.com")
        with patch.object(bot, "show_payment_session", new_callable=AsyncMock):
            await bot.receive_set_upi(update("store@fam"), self.context)
            await bot.receive_payment_payee(update("Store & Co"), self.context)
            await bot.receive_payment_mailbox(update("[Gmail]/All Mail"), self.context)
        self.assertEqual(await self.manager.get_setting("upi_id"), "store@fam")
        self.assertEqual(await self.manager.get_setting("global_brand_name"), "Store & Co")
        self.assertEqual(await self.manager.get_setting("payment_imap_mailbox"), "[Gmail]/All Mail")

    async def test_saved_bot_settings_drive_real_sdk_order_and_verification(self):
        await self.save_account()
        await self.manager.set_setting("upi_id", "store@fam")
        pm = await bot._get_pm()
        pm._repository._db = self.manager.db
        pm._repository._ensure_indexes()
        # mongomock cannot evaluate a sparse index on an array value. All
        # proofs in this test contain payment_references, so retain uniqueness
        # with a non-sparse test index (production keeps its sparse index).
        self.manager.db.verification_logs.drop_index("payment_references_1")
        self.manager.db.verification_logs.create_index("payment_references", unique=True)
        order = await asyncio.to_thread(pm.create, user_id=123, amount="12.50")
        self.assertIn("pa=store%40fam", order.upi_uri)
        self.assertTrue(order.qr_image.startswith(b"\x89PNG"))
        message = GmailMessage(
            message_id="setup-test-message", subject="You received ₹12.50 in your FamApp account",
            body="You have successfully received ₹12.50 from Test User. UTR: 123456789012",
            timestamp=utcnow() + timedelta(seconds=1), purpose=order.purpose, amount=order.amount,
        )
        with patch.object(pm._gmail, "find_matching_incoming_payment", return_value=message):
            result = await asyncio.to_thread(pm.verify, order.id)
        self.assertTrue(result["verified"])
        self.assertEqual(result["amount"], "12.50")
        self.assertEqual(self.manager.db.orders.find_one({"id": order.id})["status"], "verified")
        self.assertEqual(self.manager.db.verification_logs.count_documents({"order_id": order.id}), 1)

        # Verify that the bot's real I'VE PAID path uses the configured SDK
        # and credits the wallet, rather than failing during async UTR checks.
        await self.manager.add_user(123, "test_user", "Test User")
        await self.manager.create_fund_request_with_order(123, order.id, None, 1250, "FUND")
        request = update(callback=f"verify_pay_{order.id}", owner=123)
        with patch.object(bot, "ADMIN_IDS", [123]), \
                patch.object(bot, "safe_edit_text", new_callable=AsyncMock) as edit:
            await bot.handle_user_callbacks(request, self.context)
            self.assertIn("FUNDS ADDED SUCCESSFULLY", edit.call_args.args[2])
            await bot.handle_user_callbacks(request, self.context)
        self.assertEqual((await self.manager.get_user(123))["balance"], 1250)
        self.assertEqual((await self.manager.get_fund_request_by_order(order.id))["status"], "APPROVED")

    async def test_bot_rejects_duplicate_reference_before_wallet_credit(self):
        await self.manager.add_user(1, "test_user", "Test User")
        await self.manager.create_fund_request_with_order(1, "ORD-OLD", None, 1250, "FUND")
        await self.manager.update_fund_request_by_order("ORD-OLD", "APPROVED", utr="123456789012")
        await self.manager.create_fund_request_with_order(1, "ORD-NEW", None, 1250, "FUND")
        manager = MagicMock()
        manager.verify.return_value = {
            "verified": True, "status": "verified", "utr": "123456789012",
            "transaction_id": "NEW12345678", "amount": "12.50",
        }
        with patch.object(bot, "_get_pm", new_callable=AsyncMock, return_value=manager), \
                patch.object(bot, "safe_edit_text", new_callable=AsyncMock):
            await bot.handle_user_callbacks(update(callback="verify_pay_ORD-NEW"), self.context)
        self.assertEqual((await self.manager.get_user(1))["balance"], 0)
        self.assertEqual((await self.manager.get_fund_request_by_order("ORD-NEW"))["status"], "REJECTED_DUPLICATE_UTR")


class GmailConnectionTests(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig(mongodb_uri="", db_name="", default_upi_id="",
                                imap_username="test@gmail.com", imap_app_password=PASSWORD)

    def test_tests_readonly_mailbox_and_closes_connection(self):
        client = MagicMock()
        client.login.return_value = ("OK", [])
        client.select.return_value = ("OK", [])
        with patch("payment_template.gmail.imaplib.IMAP4_SSL", return_value=client) as connect:
            GmailService(replace(self.config, imap_mailbox="[Gmail]/All Mail")).check_connection()
        connect.assert_called_once_with("imap.gmail.com", 993, timeout=15)
        client.login.assert_called_once_with("test@gmail.com", PASSWORD)
        client.select.assert_called_once_with('"[Gmail]/All Mail"', readonly=True)
        client.logout.assert_called_once()

    def test_failed_login_and_mailbox_close_connection(self):
        for login, select in (("NO", "OK"), ("OK", "NO")):
            with self.subTest(login=login, mailbox=select):
                client = MagicMock()
                client.login.return_value = (login, [])
                client.select.return_value = (select, [])
                with patch("payment_template.gmail.imaplib.IMAP4_SSL", return_value=client):
                    with self.assertRaises(GmailError):
                        GmailService(self.config).check_connection()
                client.logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
