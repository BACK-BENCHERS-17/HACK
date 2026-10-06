"""Regression tests for access without Telegram phone-number sharing."""

import types
import inspect
import unittest
from unittest.mock import AsyncMock, patch

from test_polling_lifecycle import bot


def make_update(user_id=42):
    message = types.SimpleNamespace(reply_text=AsyncMock())
    return types.SimpleNamespace(
        effective_user=types.SimpleNamespace(
            id=user_id, username="test_user", first_name="Test User",
        ),
        effective_message=message,
        callback_query=None,
        message=message,
    )


class AccessWithoutPhoneTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_member_alert_contains_mention_identity_and_count(self):
        photos = types.SimpleNamespace(
            total_count=1,
            photos=[[types.SimpleNamespace(file_id="profile-photo")]],
        )
        telegram_bot = types.SimpleNamespace(
            get_user_profile_photos=AsyncMock(return_value=photos),
            send_photo=AsyncMock(),
            send_message=AsyncMock(),
        )
        context = types.SimpleNamespace(bot=telegram_bot)
        user = types.SimpleNamespace(id=42, first_name="A <Member>", username="member")

        with patch.object(bot, "ADMIN_IDS", [1001, 1002]):
            await bot.notify_new_member(context, user, 25)

        self.assertEqual(telegram_bot.send_photo.await_count, 2)
        self.assertEqual(telegram_bot.send_message.await_count, 0)
        caption = telegram_bot.send_photo.await_args.kwargs["caption"]
        self.assertIn("Total Members:</b> <b>25", caption)
        self.assertIn("<code>@member</code>", caption)
        self.assertIn("tg://user?id=42", caption)
        self.assertIn("A &lt;Member&gt;", caption)

    async def test_start_notifies_only_when_member_is_created(self):
        database = types.SimpleNamespace(
            add_user=AsyncMock(side_effect=[True, False]),
            get_user=AsyncMock(return_value={"is_banned": 0, "balance": 0}),
            get_setting=AsyncMock(return_value="0"),
        )
        message = types.SimpleNamespace(reply_text=AsyncMock())
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(
                id=42, username="member", first_name="Member",
            ),
            message=message,
        )
        context = types.SimpleNamespace(args=[])
        with patch.object(bot, "db", database), \
                patch.object(bot, "notify_new_member", new_callable=AsyncMock) as notify, \
                patch.object(bot, "ADMIN_IDS", []):
            database.get_all_users_count = AsyncMock(return_value=25)
            await bot.cmd_start(update, context)
            await bot.cmd_start(update, context)

        notify.assert_awaited_once_with(context, update.effective_user, 25)

    async def test_broadcast_records_sent_and_blocked_recipients_from_db(self):
        status_message = types.SimpleNamespace(edit_text=AsyncMock())
        source_message = types.SimpleNamespace(
            chat_id=900,
            message_id=77,
            reply_text=AsyncMock(return_value=status_message),
        )
        database = types.SimpleNamespace(
            is_staff=AsyncMock(return_value=True),
            get_all_user_ids=AsyncMock(return_value=[101, 202]),
            record_broadcast_result=AsyncMock(),
            log_admin_action=AsyncMock(),
        )
        telegram_bot = types.SimpleNamespace(
            copy_message=AsyncMock(side_effect=[None, RuntimeError("Forbidden: bot was blocked")]),
        )
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=42),
            effective_message=source_message,
        )
        context = types.SimpleNamespace(bot=telegram_bot)

        with patch.object(bot, "db", database), patch.object(bot, "ADMIN_IDS", []):
            await bot.receive_broadcast(update, context)

        self.assertEqual(telegram_bot.copy_message.await_count, 2)
        database.record_broadcast_result.assert_any_await(101, "SENT", "")
        database.record_broadcast_result.assert_any_await(
            202, "BLOCKED", "Forbidden: bot was blocked",
        )
        self.assertIn("Successfully Sent:</b> 1", status_message.edit_text.await_args_list[-1].args[0])
        self.assertIn("Blocked/Deleted:</b> 1", status_message.edit_text.await_args_list[-1].args[0])

    async def test_existing_user_with_legacy_unverified_flag_is_allowed(self):
        database = types.SimpleNamespace(
            get_setting=AsyncMock(return_value="0"),
            get_user=AsyncMock(return_value={"is_banned": 0, "verified": 0}),
            add_user=AsyncMock(),
        )
        target = AsyncMock(return_value="allowed")
        guarded = bot.user_access_required(target)

        with patch.object(bot, "db", database), patch.object(bot, "ADMIN_IDS", []):
            result = await guarded(make_update(), types.SimpleNamespace())

        self.assertEqual(result, "allowed")
        target.assert_awaited_once()

    async def test_new_user_is_created_and_allowed_without_contact(self):
        database = types.SimpleNamespace(
            get_setting=AsyncMock(return_value="0"),
            get_user=AsyncMock(return_value={"is_banned": 0, "verified": 0}),
            add_user=AsyncMock(),
        )
        target = AsyncMock(return_value="allowed")
        guarded = bot.user_access_required(target)

        with patch.object(bot, "db", database), patch.object(bot, "ADMIN_IDS", []):
            result = await guarded(make_update(), types.SimpleNamespace())

        self.assertEqual(result, "allowed")
        database.add_user.assert_awaited_once_with(42, "test_user", "Test User")
        target.assert_awaited_once()

    async def test_banned_user_is_still_blocked(self):
        database = types.SimpleNamespace(
            get_setting=AsyncMock(return_value="0"),
            get_user=AsyncMock(return_value={"is_banned": 1, "verified": 0}),
            add_user=AsyncMock(),
        )
        target = AsyncMock()
        guarded = bot.user_access_required(target)
        request = make_update()

        with patch.object(bot, "db", database), patch.object(bot, "ADMIN_IDS", []):
            result = await guarded(request, types.SimpleNamespace())

        self.assertIsNone(result)
        target.assert_not_awaited()
        request.effective_message.reply_text.assert_awaited_once()

    async def test_user_conversation_entry_does_not_return_phone_verification(self):
        source = inspect.getsource(bot)
        self.assertNotIn("Share Phone Number", source)
        self.assertNotIn("request_contact", source)
        self.assertNotIn("contact_handler", bot.__dict__)


if __name__ == "__main__":
    unittest.main()
