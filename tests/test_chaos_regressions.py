"""Regression suite covering all findings from Adversarial Chaos QA."""

import asyncio
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from domain.errors import DomainError
from helpers import RealisticBotTestCase
from utils.blacklist import moderate_text
from utils.messages import send_photo_text


class ChaosRegressionTests(RealisticBotTestCase):
    async def test_pause_resume_and_delete_answer_callback_once_and_clean_cards(self):
        # [C-01] Double callback.answer() crash & leaked zombie cards
        app_id = await self.create("active", owner=201, photo="card-photo")
        await self.feed(text="/start")
        await self.click("my_applications")
        await self.click(f"my_app_manage_{app_id}")
        first_card = self.latest().message_id
        await self.click(f"app_pause_{app_id}")
        self.assertIn(first_card, self.deleted)
        paused_card = self.latest().message_id
        await self.click(f"app_resume_{app_id}")
        self.assertIn(paused_card, self.deleted)
        resumed_card = self.latest().message_id
        await self.click(f"app_delete_{app_id}")
        self.assertIn(resumed_card, self.deleted)
        self.assertEqual((await self.db.get_application(app_id)).status, "deleted")

    async def test_complaint_rejects_overflow_and_missing_app_without_trapping_user(self):
        # [C-02] SQLite int64 overflow & [M-01] missing app / #id trap
        real_app = await self.create("active", owner=101)
        await self.feed(text="/start")
        await self.click("support")
        await self.click("support_complaint")
        await self.feed(text=str(10**30))
        self.assertEqual(await self.state().get_state(), self.user.SupportStates.choosing_app.state)
        await self.feed(text="999999")
        self.assertEqual(await self.state().get_state(), self.user.SupportStates.choosing_app.state)
        await self.feed(text=f"#{real_app}")
        self.assertEqual(await self.state().get_state(), self.user.SupportStates.writing_message.state)
        await self.feed(text="Дубликат объявления")
        self.assertIsNone(await self.state().get_state())
        self.assertEqual((await self.rows("SELECT COUNT(*) FROM complaints WHERE application_id=?", (real_app,)))[0][0], 1)

    async def test_validation_errors_and_out_of_phase_text_preserve_preview_and_buttons(self):
        # [H-01] & [M-03] & [M-04] ScreenMiddleware keeps active prompts/previews & buttons
        await self.feed(text="/start")
        await self.click("lost_pet")
        await self.feed(photo="p1")
        for i in range(2, 12):
            await self.feed(photo=f"p{i}")
        # Step 2 prompt must still be visible after 11th photo
        active_buttons = [b.callback_data for m in self.sent.values() if m.message_id not in self.deleted and m.reply_markup for row in m.reply_markup.inline_keyboard for b in row]
        self.assertIn("cancel", active_buttons)
        await self.feed(text="   ")
        active_buttons = [b.callback_data for m in self.sent.values() if m.message_id not in self.deleted and m.reply_markup for row in m.reply_markup.inline_keyboard for b in row]
        self.assertIn("step_back", active_buttons)
        await self.feed(text="Симба")
        await self.feed(text="Убежал у дома 36, чип 643081234567890")
        # Step 4 district keyboard includes step_back
        dist_buttons = [b.callback_data for row in self.latest().reply_markup.inline_keyboard for b in row]
        self.assertIn("step_back", dist_buttons)
        await self.click("district_Советский")
        await self.feed(text="-")
        self.assertEqual(await self.state().get_state(), self.user.CreateApplication.waiting_for_confirm.state)
        # Out-of-phase text on confirm does not wipe confirm_ok
        await self.feed(text="Да, всё верно")
        all_visible_cbs = [b.callback_data for m in self.sent.values() if m.message_id not in self.deleted and m.reply_markup for row in m.reply_markup.inline_keyboard for b in row]
        self.assertIn("confirm_ok", all_visible_cbs)

    def test_blacklist_allows_house_36_microchips_and_normal_words(self):
        # [H-02] False positives in blacklist
        allowed = [
            "Убежал у дома 36 по ул. Ленина, рост 36 см",
            "Насчет ошейника точно не помню",
            "Видели возле мусоросборника",
            "Откликается на кличку Донателло",
            "Потерялся на улице Декарта",
            "Чип животного 643081234567890 на холке",
            "Редкий окрас ebony",
        ]
        for sample in allowed:
            with self.subTest(sample=sample):
                ok, reason = moderate_text(sample)
                self.assertTrue(ok, f"Unexpectedly blocked {sample!r}: {reason}")
        for bad in ("переведите деньги на карту", "+79991234567", "89991234567", "2202200123456789", "х у й", "xуй"):
            with self.subTest(bad=bad):
                self.assertFalse(moderate_text(bad)[0])

    async def test_slash_cancel_aborts_admin_ban_instead_of_banning_user(self):
        # [H-03] /cancel in AdminBanStates
        await self.feed(9001, data="admin_ban_prompt_101")
        self.assertEqual(await self.state(9001).get_state(), self.user.AdminBanStates.waiting_for_reason.state)
        await self.feed(9001, text="/cancel")
        self.assertIsNone(await self.state(9001).get_state())
        self.assertFalse((await self.db.get_user(101)).is_banned)

    async def test_banning_user_suspends_active_apps_blocks_admin_self_ban_and_allows_data_erasure(self):
        # [H-04], [H-05], [L-01]
        with self.assertRaises(DomainError):
            await self.services.moderation.set_ban(9001, 9001, True, "Self ban")
        app_id = await self.create("active", owner=101)
        await self.services.moderation.set_ban(9001, 101, True, "Мошенничество")
        self.assertEqual((await self.db.get_application(app_id)).status, "paused")
        self.assertIsNone(await self.services.applications.next_card(201))
        # Banned user can erase personal data via /delete_my_data without evading the ban
        await self.feed(101, text="/delete_my_data")
        self.assertIsNone(await self.db.get_application(app_id))
        banned_record = await self.db.get_user(101)
        self.assertIsNotNone(banned_record)
        self.assertTrue(banned_record.is_banned)
        self.assertEqual(banned_record.first_name, "")

    async def test_100_plus_applications_paginate_cleanly_in_user_and_admin_lists(self):
        # [H-06] >100 buttons pagination
        for i in range(105):
            await self.create("moderation", owner=201, description=f"Кот #{i}")
        await self.feed(text="/start")
        await self.click("my_applications")
        await self.click("my_apps_page_1")
        await self.feed(9001, text="/start")
        await self.click("admin_enter_mode", chat=9001)
        await self.click("admin_moderation_list", chat=9001)
        await self.click("admin_mod_page_1", chat=9001)

    async def test_group_chats_ignore_messages_and_require_consent_for_unregistered_users(self):
        # [H-07] Group chat isolation & [H-08] 152-FZ consent gate
        before = len(self.outgoing)
        await self.feed(201, text="Всем привет!", chat_id=-100555, chat_type="supergroup")
        self.assertEqual(len(self.outgoing), before)

        await self.feed(777, text="Привет")
        buttons_777 = [b.callback_data for row in self.latest(777).reply_markup.inline_keyboard for b in row]
        self.assertEqual(buttons_777, ["agree_pd"])
        await self.feed(777, text="/delete_my_data")
        self.assertIn("Данные удалены", self.latest(777).text)

    async def test_multi_photo_broken_file_id_falls_back_to_text(self):
        # [H-09] Multi-photo broken file_id fallback
        target = AsyncMock()
        target.answer_media_group.side_effect = TelegramBadRequest(method=AsyncMock(), message="wrong file identifier")
        target.answer_photo.side_effect = TelegramBadRequest(method=AsyncMock(), message="wrong file identifier")
        await send_photo_text(target, ("bad1", "bad2"), "<b>Карточка</b>", reply_markup="kb")
        target.answer.assert_awaited_once()

    def test_manage_cli_handles_empty_db_and_huge_notification_id_cleanly(self):
        # [L-06] manage.py CLI safety
        empty = Path(self.temp.name) / "empty.db"
        empty.write_bytes(b"")
        res_empty = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "manage.py"), "--database", str(empty), "notifications"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(res_empty.returncode, 0)
        self.assertNotIn("Traceback", res_empty.stderr)

        res_ovf = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "manage.py"), "--database", str(self.db.DB_PATH), "retry-notification", str(10**30)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(res_ovf.returncode, 0)
        self.assertNotIn("Traceback", res_ovf.stderr)


if __name__ == "__main__":
    unittest.main()
