import unittest

from bot import create_dispatcher
from domain.districts import NOVOSIBIRSK_DISTRICTS
from helpers import RealisticBotTestCase
from services.geolocation import detect_district, district_boundaries, in_ring


class GeographyTests(unittest.TestCase):
    def test_landmarks_all_ten_districts_and_outside_city(self):
        # Fixed landmarks spread across the city, including Akademgorodok.
        samples = [
            (55.0303, 82.9204, "Центральный"), (55.0359, 82.8964, "Железнодорожный"),
            (55.0677, 82.9127, "Заельцовский"), (55.079, 82.938, "Калининский"),
            (55.049, 82.978, "Дзержинский"), (55.015, 82.903, "Ленинский"),
            (54.967, 82.936, "Кировский"), (55.012, 82.962, "Октябрьский"),
            (54.925, 83.111, "Первомайский"), (54.843, 83.094, "Советский"),
        ]
        self.assertEqual({f["properties"]["name"] for f in district_boundaries()}, set(NOVOSIBIRSK_DISTRICTS))
        for lat, lon, expected in samples:
            with self.subTest(expected=expected):
                self.assertEqual(detect_district(lat, lon), expected)
        for point in [(55, 83.4), (0, 0), (float("nan"), 82.9), (55, float("inf"))]:
            self.assertIsNone(detect_district(*point))

    def test_polygon_edges_and_holes(self):
        ring = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
        self.assertTrue(in_ring(1, 1, ring))
        self.assertTrue(in_ring(0, 1, ring))
        self.assertFalse(in_ring(3, 1, ring))


class UXTests(RealisticBotTestCase):
    async def test_cleanup_keeps_submission_receipt_across_navigation_and_restart(self):
        await self.feed(text="/start")
        await self.click("lost_pet")
        first_prompt = self.latest().message_id
        await self.feed(photo="photo-1")
        self.assertIn(first_prompt, self.deleted)
        await self.feed(photo="photo-2")
        await self.feed(text="Барсик")
        await self.feed(text="Рыжий кот")
        await self.click("district_Советский")
        await self.feed(text="-")
        album = next(m for m in reversed(self.outgoing) if m.__api_method__ == "sendMediaGroup")
        self.assertEqual([item.media for item in album.media], ["photo-1", "photo-2"])
        preview_ids = [mid for mid, durable in await self.rows("SELECT message_id, durable FROM chat_screens") if not durable]
        self.assertEqual(len(preview_ids), 3)  # two photos and confirmation controls
        await self.click("confirm_ok")
        receipt = self.latest()
        self.assertTrue(all(mid in self.deleted for mid in preview_ids))
        app = await self.db.get_application(1)
        self.assertEqual(app.photo_ids, ("photo-1", "photo-2"))
        await self.click("open_settings", message=receipt)
        self.assertNotIn(receipt.message_id, self.deleted)
        self.assertIn("отправлена на модерацию", self.sent[receipt.message_id].text)
        settings_id = self.latest().message_id
        await self.dp.fsm.close()
        self.dp = create_dispatcher(self.services)
        await self.feed(text="/start")
        self.assertIn(settings_id, self.deleted)
        self.assertNotIn(receipt.message_id, self.deleted)
        self.assertEqual(await self.rows("SELECT durable FROM chat_screens WHERE message_id=?", (receipt.message_id,)), [(1,)])

    async def test_settings_update_same_screen_with_one_blue_selected_button(self):
        await self.feed(text="/start")
        await self.click("open_settings")
        mid = self.latest().message_id
        sends = sum(m.__api_method__ == "sendMessage" for m in self.outgoing)
        await self.click("set_notif_city")
        self.assertEqual(self.latest().message_id, mid)
        self.assertEqual(sum(m.__api_method__ == "sendMessage" for m in self.outgoing), sends)
        buttons = [b for row in self.latest().reply_markup.inline_keyboard for b in row]
        selected = [b for b in buttons if b.style == "primary"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].callback_data, "set_notif_city")
        self.assertTrue(selected[0].text.startswith("●"))
        self.assertEqual((await self.db.get_user(201)).notification_mode, "city")

    async def test_location_confirmation_allows_user_to_check_without_storing_coordinates(self):
        await self.feed(text="/set_district")
        await self.click("detect_district")
        prompt = next(m for m in reversed(self.outgoing) if m.__api_method__ == "sendMessage")
        self.assertTrue(prompt.reply_markup.keyboard[0][0].request_location)
        await self.feed(location={"latitude": 55.0303, "longitude": 82.9204})
        self.assertIn(self.sequence, self.deleted)
        self.assertIsNone((await self.db.get_user(201)).district)
        await self.click("geo_use")
        self.assertEqual((await self.db.get_user(201)).district, "Центральный")
        self.assertIsNone(await self.state().get_state())
        for row in await self.rows("SELECT data FROM dialog_sessions"):
            self.assertNotIn("55.0303", row[0])
            self.assertNotIn("82.9204", row[0])
            self.assertNotIn("latitude", row[0])
        self.assertFalse(any(getattr(m, "latitude", None) for m in self.outgoing))

    async def test_location_in_found_draft_resumes_form_and_preserves_photo(self):
        await self.feed(text="/start")
        await self.click("found_pet")
        await self.feed(photo="found-photo")
        await self.click("detect_district")
        await self.feed(location={"latitude": 55.0303, "longitude": 82.9204})
        await self.click("geo_use")
        self.assertEqual(await self.state().get_state(), self.user.FoundPet.waiting_for_description.state)
        self.assertEqual((await self.state().get_data())["photo_id"], "found-photo")
        await self.feed(text="Кот с ошейником")
        preview = self.latest()
        self.assertEqual(preview.photo[-1].file_id, "found-photo")
        self.assertIn("Центральный", preview.caption)

    async def test_outside_city_and_manual_cancel_restore_district_selection(self):
        await self.feed(text="/set_district")
        await self.click("detect_district")
        await self.feed(location={"latitude": 0, "longitude": 0})
        self.assertEqual(await self.state().get_state(), self.user.SettingsStates.choosing_district.state)
        self.assertIsNone((await self.db.get_user(201)).district)
        await self.click("detect_district")
        await self.feed(text="Выбрать район вручную")
        await self.click("district_Ленинский")
        self.assertEqual((await self.db.get_user(201)).district, "Ленинский")

    async def test_backlog_is_delivered_once_with_photos_and_direct_moderation_buttons(self):
        app_id = await self.create("moderation", photo="moderation-photo")
        await self.services.moderation.queue_pending_requests()
        await self.services.moderation.queue_pending_requests()
        self.assertEqual(await self.rows("SELECT recipient_id, kind FROM notification_outbox"), [(9001, "submitted")])
        await self.worker.drain()
        request = self.latest(9001)
        self.assertEqual(request.photo[-1].file_id, "moderation-photo")
        actions = [b.callback_data for row in request.reply_markup.inline_keyboard for b in row]
        self.assertIn(f"admin_approve_{app_id}", actions)
        self.assertIn(f"admin_reject_{app_id}", actions)
        await self.click(f"admin_approve_{app_id}", chat=9001, message=request)
        self.assertEqual((await self.db.get_application(app_id)).status, "active")
        self.assertNotIn(request.message_id, self.deleted)
        self.assertIsNone(self.sent[request.message_id].reply_markup)
        await self.services.moderation.queue_pending_requests()
        self.assertEqual(await self.rows("SELECT COUNT(*) FROM notification_outbox WHERE kind='submitted'"), [(1,)])
