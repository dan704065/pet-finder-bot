"""Regression tests for authorization, application workflows and Telegram rendering."""

import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4


from helpers import BotTestCase

from utils.blacklist import check_profanity, moderate_text
from utils.messages import h, send_photo_text, send_text, text_length


class BotRegressionTests(BotTestCase):


    async def test_all_admin_callbacks_reject_non_admin(self):
        app_id = await self.create("moderation")
        complaint_id = await self.db.add_complaint(app_id, 201, "Test")
        callbacks = [
            "admin_enter_mode", "admin_exit_mode", "admin_stats", "admin_users_list", "admin_logs",
            "admin_moderation_list", f"admin_moderate_{app_id}", f"admin_approve_{app_id}",
            f"admin_reject_{app_id}", "admin_ban_user_101", "admin_ban_prompt_101",
            "admin_unban_101", "admin_user_detail_101", "admin_complaints_list",
            f"admin_complaint_view_{complaint_id}", f"admin_complaint_confirm_{complaint_id}",
            f"admin_complaint_reject_{complaint_id}",
        ]
        for data in callbacks:
            with self.subTest(data=data):
                before = len(self.outgoing)
                await self.feed(data=data)
                self.assertEqual(len(self.outgoing), before + 1)
                self.assertEqual(self.outgoing[-1].__api_method__, "answerCallbackQuery")
                self.assertIn("Доступ запрещён", self.outgoing[-1].text)
                self.assertEqual((await self.db.get_application(app_id)).status, "moderation")
                self.assertEqual((await self.db.get_user(101)).is_banned, 0)
                self.assertIsNone(await self.state().get_state())
        self.assertEqual((await self.rows("SELECT status FROM complaints"))[0][0], "pending")
        self.assertEqual(await self.rows("SELECT * FROM logs"), [])

    async def test_non_admin_cannot_finish_admin_reason_state(self):
        await self.state().set_state(self.user.AdminBanStates.waiting_for_reason)
        await self.state().set_data({"action": "ban", "ban_target_user_id": 101})
        await self.feed(text="Ban this user")
        self.assertEqual((await self.db.get_user(101)).is_banned, 0)

    async def test_admin_workflows_still_work_and_ignore_stale_buttons(self):
        app_id = await self.create("moderation")
        await self.feed(9001, data=f"admin_approve_{app_id}")
        self.assertEqual((await self.db.get_application(app_id)).status, "active")
        await self.db.update_application_status(app_id, "closed")
        await self.feed(9001, data=f"admin_approve_{app_id}")
        self.assertEqual((await self.db.get_application(app_id)).status, "closed")
        rejected = await self.create("moderation")
        await self.feed(9001, data=f"admin_reject_{rejected}")
        await self.feed(9001, text="Причина <проверка>")
        self.assertEqual((await self.db.get_application(rejected)).status, "rejected")
        await self.feed(9001, data="admin_ban_prompt_101")
        await self.feed(9001, text="Spam <reason>")
        self.assertEqual((await self.db.get_user(101)).is_banned, 1)
        await self.feed(9001, data="admin_unban_101")
        self.assertEqual((await self.db.get_user(101)).is_banned, 0)

    async def test_foreign_application_cannot_be_read_or_changed(self):
        for prefix, status in [
            ("my_app_manage", "active"), ("app_pause", "active"), ("app_resume", "paused"),
            ("app_found", "active"), ("app_delete", "active"),
            ("app_hard_delete", "deleted"), ("app_confirm_hard_delete", "deleted"),
        ]:
            with self.subTest(prefix=prefix):
                app_id = await self.create(status)
                await self.feed(data=f"{prefix}_{app_id}")
                self.assertEqual((await self.db.get_application(app_id)).status, status)
                self.assertEqual(self.outgoing[-1].__api_method__, "answerCallbackQuery")

    async def test_owner_transitions_and_hard_delete(self):
        app_id = await self.create()
        for prefix, status in [("app_pause", "paused"), ("app_resume", "active"), ("app_found", "closed")]:
            await self.feed(101, data=f"{prefix}_{app_id}")
            self.assertEqual((await self.db.get_application(app_id)).status, status)
        other = await self.create()
        await self.db.add_response(other, 201, "Park", "")
        await self.db.add_complaint(other, 201, "Test")
        await self.feed(101, data=f"app_delete_{other}")
        await self.feed(101, data=f"app_confirm_hard_delete_{other}")
        self.assertIsNone(await self.db.get_application(other))
        self.assertEqual(await self.rows("SELECT * FROM responses WHERE application_id=?", (other,)), [])
        self.assertEqual(await self.rows("SELECT * FROM complaints WHERE application_id=?", (other,)), [])

    async def test_stale_owner_buttons_cannot_bypass_moderation(self):
        for status in ("moderation", "rejected", "closed", "deleted"):
            app_id = await self.create(status)
            for prefix in ("app_pause", "app_resume", "app_found", "app_delete"):
                with self.subTest(status=status, prefix=prefix):
                    await self.feed(101, data=f"{prefix}_{app_id}")
                    self.assertEqual((await self.db.get_application(app_id)).status, status)

    async def test_response_uses_clicked_card_not_latest_card(self):
        first = await self.create(owner=101)
        latest = await self.create(owner=102)
        await self.state().set_state(self.user.SwipeStates.swiping)
        await self.state().set_data({"current_app_id": latest, "viewed_apps": [first, latest]})
        await self.feed(data=f"swipe_seen_{first}")
        await self.feed(text="У дома <номер> & парк")
        self.assertEqual((await self.rows("SELECT application_id FROM responses"))[0][0], first)
        owner_messages = [m for m in self.outgoing if m.__api_method__ == "sendMessage" and m.chat_id == 101]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("&lt;номер&gt; &amp;", owner_messages[0].text)
        self.assertFalse(any(m.__api_method__ == "sendMessage" and m.chat_id == 102 for m in self.outgoing))

    async def test_response_rechecks_status_at_save_time(self):
        app_id = await self.create()
        await self.state().set_state(self.user.SwipeStates.swiping)
        await self.state().set_data({"current_app_id": app_id, "viewed_apps": [app_id]})
        await self.feed(data=f"swipe_seen_{app_id}")
        await self.db.update_application_status(app_id, "paused")
        await self.feed(text="Park")
        self.assertEqual(await self.rows("SELECT * FROM responses"), [])

    async def test_parallel_confirmation_creates_one_lost_or_found_application(self):
        for kind, state in [("lost", self.user.CreateApplication.waiting_for_confirm), ("found", self.user.FoundPet.waiting_for_confirm)]:
            with self.subTest(kind=kind):
                await self.state().set_state(state)
                await self.state().set_data({
                    "submission_key": uuid4().hex, "pet_name": "Pet", "description": "Description",
                    "found_description": "Description", "district": "Советский", "photo_id": "photo", "additional_info": "",
                })
                await asyncio.gather(self.feed(data="confirm_ok"), self.feed(data="confirm_ok"))
                self.assertEqual((await self.rows("SELECT count(*) FROM applications WHERE type=?", (kind,)))[0][0], 1)
                self.assertIsNone(await self.state().get_state())

    async def test_database_submission_key_is_idempotent(self):
        args = (101, "lost", "Pet", "Description", "Советский", "", "photo")
        key = uuid4().hex
        ids = await asyncio.gather(*[self.db.create_application(*args, submission_key=key) for _ in range(3)])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual((await self.rows("SELECT count(*) FROM applications"))[0][0], 1)

    async def test_complete_lost_and_found_flows_escape_html(self):
        await self.feed(301, text="/start", first_name="<Имя> & тест")
        await self.feed(301, data="agree_pd")
        await self.feed(301, data="prompt_initial_district")
        await self.feed(301, data="district_Советский")
        await self.feed(301, data="lost_pet")
        await self.feed(301, photo=True)
        await self.feed(301, text="Кот <Рыжик>")
        await self.feed(301, text="Небольшой кот & рыжий окрас")
        await self.feed(301, data="district_Советский")
        await self.feed(301, text="Возраст < 3 лет")
        await self.feed(301, data="confirm_ok")
        self.assertEqual((await self.rows("SELECT count(*) FROM applications WHERE type='lost'"))[0][0], 1)
        await self.feed(301, data="found_pet")
        await self.feed(301, photo=True)
        await self.feed(301, data="district_Советский")
        await self.feed(301, text="Серебристый окрас <ошейник>")
        await self.feed(301, data="confirm_ok")
        self.assertEqual((await self.rows("SELECT count(*) FROM applications WHERE type='found'"))[0][0], 1)
        self.assertTrue(any("&lt;Рыжик&gt;" in (getattr(m, "text", "") or "") for m in self.outgoing))

    async def test_input_limits_keep_user_on_current_step(self):
        cases = [
            (self.user.CreateApplication.waiting_for_name, 80, 201),
            (self.user.CreateApplication.waiting_for_description, 2000, 201),
            (self.user.CreateApplication.waiting_for_additional, 1000, 201),
            (self.user.FoundPet.waiting_for_description, 2000, 201),
            (self.user.SwipeStates.writing_response, 2000, 201),
            (self.user.SupportStates.writing_message, 2000, 201),
            (self.user.AdminBanStates.waiting_for_reason, 1000, 9001),
        ]
        for state, limit, user_id in cases:
            for text in ("A" * (limit + 1), "🐾" * (limit // 2 + 1), "   "):
                with self.subTest(state=state.state, length=len(text)):
                    await self.state(user_id).set_state(state)
                    await self.state(user_id).set_data({})
                    await self.feed(user_id, text=text)
                    self.assertEqual(await self.state(user_id).get_state(), state.state)
                    self.assertEqual(await self.state(user_id).get_data(), {})

    async def test_largest_allowed_preview_and_legacy_long_photo_are_deliverable(self):
        await self.state().set_state(self.user.CreateApplication.waiting_for_additional)
        await self.state().set_data({"pet_name": "A" * 80, "description": "A" * 2000, "district": "Советский"})
        await self.feed(text="A" * 1000)
        self.assertEqual(await self.state().get_state(), self.user.CreateApplication.waiting_for_confirm.state)
        app_id = await self.create(description="<legacy & text>🐾" * 1000, photo="photo")
        before = len(self.outgoing)
        await self.feed(data=f"notify_show_{app_id}")
        sent = self.outgoing[before:]
        self.assertTrue(any(m.__api_method__ == "sendPhoto" and not m.caption for m in sent))
        chunks = [m for m in sent if m.__api_method__ == "sendMessage"]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(m.parse_mode is None for m in chunks))
        self.assertIn("<legacy & text>", "".join(m.text for m in chunks))
        self.assertIsNotNone(chunks[-1].reply_markup)

    async def test_search_reaches_older_matching_and_unviewed_applications(self):
        oldest = await self.create(district="Советский")
        async with self.db.aiosqlite.connect(self.db.DB_PATH) as connection:
            await connection.execute("UPDATE applications SET created_at='2020-01-01' WHERE id=?", (oldest,))
            await connection.executemany("""INSERT INTO applications(user_id,type,pet_name,description,district,status)
                VALUES (101,'lost','Pet','Description','Центральный','active')""", [()] * 120)
            await connection.commit()
        await self.feed(data="help_choose_district")
        await self.feed(data="district_Советский")
        self.assertEqual((await self.state().get_data())["current_app_id"], oldest)
        all_ids = [r[0] for r in await self.rows("SELECT id FROM applications WHERE id != ?", (oldest,))]
        self.assertEqual((await self.db.get_next_active_application(201, excluded_ids=all_ids)).id, oldest)

    async def test_setting_district_does_not_start_search(self):
        await self.create()
        await self.state().set_state(self.user.CreateApplication.waiting_for_description)
        await self.feed(text="/set_district")
        self.assertEqual(await self.state().get_state(), self.user.SettingsStates.choosing_district.state)
        await self.feed(data="district_Советский")
        self.assertEqual((await self.db.get_user(201)).district, "Советский")
        self.assertIsNone(await self.state().get_state())
        self.assertTrue(any("Район изменён" in (getattr(m, "text", "") or "") for m in self.outgoing))
        self.assertFalse(any("Приметы" in (getattr(m, "text", "") or "") for m in self.outgoing))

    async def test_invalid_district_cannot_be_saved(self):
        await self.feed(text="/set_district")
        await self.feed(data="district_<invalid>")
        self.assertIsNone((await self.db.get_user(201)).district)
        self.assertEqual(await self.state().get_state(), self.user.SettingsStates.choosing_district.state)

    async def test_notifications_do_not_open_inactive_applications_or_reset_drafts(self):
        for status in ("moderation", "rejected", "paused", "closed", "deleted"):
            with self.subTest(status=status):
                app_id = await self.create(status)
                await self.state().set_state(self.user.CreateApplication.waiting_for_photo)
                await self.state().set_data({"submission_key": "draft"})
                await self.feed(data=f"notify_show_{app_id}")
                self.assertEqual(await self.state().get_state(), self.user.CreateApplication.waiting_for_photo.state)
                self.assertEqual(await self.state().get_data(), {"submission_key": "draft"})

    async def test_delete_data_clears_logs_related_rows_and_active_state(self):
        own = await self.create(owner=201)
        other = await self.create(owner=101)
        await self.db.add_response(own, 101, "Park", "")
        await self.db.add_response(other, 201, "Park", "")
        await self.db.add_complaint(own, 101, "Test")
        await self.db.add_complaint(other, 201, "Test")
        await self.db.add_log(201, "Own log", "Personal text")
        await self.db.add_log(9001, "Subject log", "Personal text", subject_user_id=201)
        await self.db.add_log(101, "Application log", "Personal text", application_id=own)
        await self.db.add_log(9001, "Legacy log", "ID: 201, reason")
        await self.db.add_log(101, "Unrelated", "Keep this")
        await self.state().set_state(self.user.CreateApplication.waiting_for_name)
        await self.state().set_data({"pet_name": "Personal text"})
        await self.feed(text="/delete_my_data")
        self.assertIsNone(await self.db.get_user(201))
        self.assertIsNone(await self.db.get_application(own))
        self.assertIsNotNone(await self.db.get_application(other))
        self.assertEqual(await self.rows("SELECT * FROM responses"), [])
        self.assertEqual(await self.rows("SELECT * FROM complaints"), [])
        self.assertEqual(await self.rows("SELECT action, details FROM logs"), [("Unrelated", "Keep this")])
        self.assertIsNone(await self.state().get_state())
        self.assertEqual(await self.state().get_data(), {})

    async def test_schema_upgrade_preserves_existing_applications(self):
        self.db.DB_PATH = Path(self.temp.name) / "legacy.db"
        async with self.db.aiosqlite.connect(self.db.DB_PATH) as connection:
            await connection.execute("""CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT,
                pet_name TEXT, description TEXT, district TEXT, additional_info TEXT,
                photo_id TEXT, status TEXT DEFAULT 'moderation',
                views INTEGER DEFAULT 0, responses INTEGER DEFAULT 0, deleted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            await connection.execute("INSERT INTO applications(user_id,type,pet_name,status) VALUES (101,'lost','Existing','active')")
            await connection.execute("""CREATE TABLE users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, role TEXT,
                is_banned INTEGER DEFAULT 0, ban_reason TEXT, district TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            await connection.execute("INSERT INTO users(user_id,district) VALUES (101,'Советский')")
            await connection.execute("CREATE TABLE logs(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, details TEXT, created_at TIMESTAMP)")
            await connection.commit()
        await self.db.init_db()
        await self.db.init_db()
        self.assertEqual((await self.db.get_application(1)).pet_name, "Existing")
        self.assertIsNone((await self.db.get_application(1)).submission_key)
        self.assertEqual((await self.db.get_application(1)).status, "active")
        self.assertEqual(((await self.db.get_user(101)).notification_mode, (await self.db.get_user(101)).district), ("none", "Советский"))
        await self.db.add_log(101, "Upgraded", subject_user_id=201, application_id=1)


class TextRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_ordinary_descriptions_pass_and_obscene_words_remain_blocked(self):
        for text in ("небольшой кот", "серебристый окрас", "белая шерсть", "ребёнок видел кота", "люблю кота"):
            with self.subTest(text=text):
                self.assertTrue(moderate_text(text)[0])
        for text in ("ебать", "заебал", "пиздец", "хуй", "х у й", "xуй", "блядь", "сука", "охуеть", "долбоеб", "отъебись"):
            with self.subTest(text=text):
                self.assertTrue(check_profanity(text))

    async def test_long_unicode_text_is_split_without_losing_content(self):
        send = AsyncMock()
        content = "🐾<&>" * 2000
        await send_text(send, "<b>" + h(content) + "</b>", parse_mode="HTML", reply_markup="last")
        calls = send.call_args_list
        self.assertGreater(len(calls), 1)
        self.assertEqual("".join(call.kwargs["text"] for call in calls), content)
        self.assertTrue(all(text_length(call.kwargs["text"]) <= 4096 for call in calls))
        self.assertTrue(all(call.kwargs["reply_markup"] is None for call in calls[:-1]))
        self.assertEqual(calls[-1].kwargs["reply_markup"], "last")

    async def test_long_photo_caption_keeps_photo_and_sends_text_separately(self):
        message = types.SimpleNamespace(answer_photo=AsyncMock(), answer=AsyncMock())
        await send_photo_text(message, "photo", "<b>" + "A" * 1500 + "</b>", reply_markup="buttons")
        message.answer_photo.assert_awaited_once_with(photo="photo")
        self.assertEqual(message.answer.call_args.kwargs["reply_markup"], "buttons")


if __name__ == "__main__":
    unittest.main()
