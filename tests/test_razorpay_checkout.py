"""Tests for Razorpay QR payments delivered directly in bot chat."""

import asyncio
from io import BytesIO
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from test_polling_lifecycle import bot
import razorpay_checkout


class RazorpayQRTests(unittest.TestCase):
    def test_create_qr_requires_integer_amount_of_at_least_one_rupee(self):
        for amount in (True, 99, 100.0, "100"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                razorpay_checkout.create_qr_code(amount, "key", "secret", "Store", "test")

    def test_create_qr_requests_fixed_single_use_upi_and_downloads_image(self):
        client = MagicMock()
        client.qrcode.create.return_value = {
            "id": "qr_test", "image_url": "https://rzp.io/i/qr_test",
        }
        response = MagicMock()
        response.content = b"png-image"
        response.headers = {"Content-Type": "image/png"}
        with patch.object(razorpay_checkout.razorpay, "Client", return_value=client), \
                patch.object(razorpay_checkout.requests, "get", return_value=response):
            qr = razorpay_checkout.create_qr_code(
                2500, "key", "secret", "My Store", "Wallet top-up"
            )

        payload = client.qrcode.create.call_args.args[0]
        self.assertEqual(payload["type"], "upi_qr")
        self.assertEqual(payload["usage"], "single_use")
        self.assertTrue(payload["fixed_amount"])
        self.assertEqual(payload["payment_amount"], 2500)
        self.assertEqual(qr["id"], "qr_test")
        self.assertEqual(qr["image"], b"png-image")
        response.raise_for_status.assert_called_once()

    def test_validate_credentials_maps_unauthorized_provider_response(self):
        session = MagicMock()
        session.last_status_code = 401
        client = MagicMock(session=session)
        client.qrcode.all.side_effect = RuntimeError("unauthorized")
        with patch.object(razorpay_checkout.razorpay, "Client", return_value=client):
            with self.assertRaises(razorpay_checkout.PaymentAuthenticationError):
                razorpay_checkout.validate_credentials("rzp_test_id", "secret")

    def test_qr_verification_requires_captured_matching_amount(self):
        client = MagicMock()
        client.qrcode.fetch_all_payments.return_value = {
            "items": [
                {
                    "id": "pay_pending", "qr_code_id": "qr_test",
                    "amount": 2500, "currency": "INR", "status": "authorized",
                },
                {
                    "id": "pay_wrong_amount", "qr_code_id": "qr_test",
                    "amount": 2000, "currency": "INR", "status": "captured",
                },
            ],
        }
        with patch.object(razorpay_checkout.razorpay, "Client", return_value=client):
            pending = razorpay_checkout.verify_qr_payment(
                "qr_test", 2500, "key", "secret"
            )
        self.assertFalse(pending["verified"])

        client.qrcode.fetch_all_payments.return_value["items"].append({
            "id": "pay_captured", "qr_code_id": "qr_test",
            "amount": 2500, "currency": "INR", "status": "captured",
            "acquirer_data": {"rrn": "123456789012"},
            "created_at": 1760000000,
        })
        with patch.object(razorpay_checkout.razorpay, "Client", return_value=client):
            verified = razorpay_checkout.verify_qr_payment(
                "qr_test", 2500, "key", "secret"
            )
        self.assertTrue(verified["verified"])
        self.assertEqual(verified["transaction_id"], "pay_captured")
        self.assertEqual(verified["utr"], "123456789012")


class RazorpayBotFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_can_select_only_configured_razorpay_gateway(self):
        query = SimpleNamespace(
            data="adm_gateway_razorpay",
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=1),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(reply_text=AsyncMock()),
        )
        database = SimpleNamespace(
            set_setting=AsyncMock(),
            log_admin_action=AsyncMock(),
        )
        settings = {
            "razorpay_key_id": "rzp_test_id",
            "razorpay_key_secret": "secret",
            "razorpay_credentials_error": "",
        }
        with patch.object(bot, "ADMIN_IDS", [1]), \
                patch.object(bot, "db", database), \
                patch.object(bot, "_payment_settings", new=AsyncMock(return_value=settings)), \
                patch.object(bot, "show_payment_session", new=AsyncMock()):
            await bot.handle_admin_callbacks(update, SimpleNamespace())

        database.set_setting.assert_awaited_once_with("payment_gateway", "razorpay")

    async def test_admin_cannot_activate_razorpay_without_validated_credentials(self):
        query = SimpleNamespace(
            data="adm_gateway_razorpay",
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=1),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(reply_text=AsyncMock()),
        )
        database = SimpleNamespace(
            set_setting=AsyncMock(),
            log_admin_action=AsyncMock(),
        )
        with patch.object(bot, "ADMIN_IDS", [1]), \
                patch.object(bot, "db", database), \
                patch.object(bot, "_payment_settings", new=AsyncMock(return_value={
                    "razorpay_key_id": "",
                    "razorpay_key_secret": "",
                    "razorpay_credentials_error": "",
                })), \
                patch.object(bot, "show_payment_session", new=AsyncMock()):
            await bot.handle_admin_callbacks(update, SimpleNamespace())

        database.set_setting.assert_not_awaited()
        query.answer.assert_awaited_once_with(
            "Connect and validate Razorpay credentials first.", show_alert=True
        )

    async def test_wallet_top_up_uses_selected_razorpay_gateway_only(self):
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(id=42),
            callback_query=None,
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        context = SimpleNamespace()
        with patch.object(bot, "_active_payment_gateway", new=AsyncMock(return_value="razorpay")), \
                patch.object(bot, "_send_razorpay_qr", new=AsyncMock()) as create_qr, \
                patch.object(bot, "_get_pm", new=AsyncMock()) as get_fam_payment_manager:
            await bot._process_add_fund(update, context, 10.00)

        create_qr.assert_awaited_once_with(
            context, user_id=42, amount_paise=1000, plan_id=None, order_type="FUND"
        )
        get_fam_payment_manager.assert_not_awaited()

    async def test_qr_is_sent_as_chat_photo_and_request_is_marked_razorpay(self):
        fake_db = SimpleNamespace(
            create_fund_request_with_order=AsyncMock(return_value=True)
        )
        message = SimpleNamespace(message_id=7)
        context = SimpleNamespace(
            bot=SimpleNamespace(send_photo=AsyncMock(return_value=message)),
            job_queue=MagicMock(),
        )
        settings = {
            "razorpay_key_id": "rzp_test_id",
            "razorpay_key_secret": "secret",
            "razorpay_credentials_error": "",
            "payee_name": "Store",
        }
        with patch.object(bot, "db", fake_db), \
                patch.object(bot, "_payment_settings", new=AsyncMock(return_value=settings)), \
                patch.object(razorpay_checkout, "create_qr_code", return_value={
                    "id": "qr_test", "image": b"png-image",
                }):
            await bot._send_razorpay_qr(
                context, user_id=42, amount_paise=2500,
                plan_id=3, order_type="PRODUCT",
            )

        fake_db.create_fund_request_with_order.assert_awaited_once_with(
            42, "qr_test", 3, 2500, "PRODUCT", payment_gateway="razorpay"
        )
        sent = context.bot.send_photo.await_args.kwargs
        self.assertEqual(sent["chat_id"], 42)
        self.assertIsInstance(sent["photo"], BytesIO)
        self.assertEqual(sent["photo"].getvalue(), b"png-image")
        self.assertIn("SCAN", sent["caption"])
        context.job_queue.run_once.assert_called_once()

    async def test_only_selected_gateway_is_returned(self):
        database = SimpleNamespace(
            get_setting=AsyncMock(return_value="razorpay")
        )
        with patch.object(bot, "db", database):
            self.assertEqual(await bot._active_payment_gateway(), "razorpay")

    async def test_razorpay_credentials_are_encrypted_in_admin_setup(self):
        admin_db = MagicMock()
        admin_db.set_setting = AsyncMock()
        admin_db.log_admin_action = AsyncMock()
        request = SimpleNamespace(
            message=SimpleNamespace(text="secret1234567890", delete=AsyncMock()),
            effective_message=None,
            effective_user=SimpleNamespace(id=1),
            effective_chat=SimpleNamespace(type="private"),
            callback_query=None,
        )
        context = SimpleNamespace(user_data={"razorpay_setup_key_id": "rzp_test_key123"})
        with patch.object(bot, "db", admin_db), \
                patch.object(razorpay_checkout, "validate_credentials", return_value=True), \
                patch.object(bot, "show_payment_session", new=AsyncMock(return_value=0)):
            await bot.receive_razorpay_key_secret(request, context)

        request.message.delete.assert_awaited_once()
        saved = admin_db.set_setting.await_args.args[1]
        self.assertEqual(saved["key_id"], "rzp_test_key123")
        self.assertNotIn("secret1234567890", str(saved))
        self.assertEqual(
            bot._payment_cipher().decrypt(saved["key_secret_enc"].encode()).decode(),
            "secret1234567890",
        )
        self.assertNotIn("razorpay_setup_key_id", context.user_data)


if __name__ == "__main__":
    unittest.main()
