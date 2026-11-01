import asyncio
from dataclasses import replace
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.storage.base import StorageKey

from bot import create_dispatcher
from domain.errors import AccessDenied, ApplicationUnavailable, ValidationError
from domain.models import ApplicationDraft, ApplicationKind, ApplicationStatus
from repositories.outbox import OutboxRepository
from services.container import Services
from storage.sqlite import SQLiteStorage
from workers.notifications import NotificationWorker
from helpers import BotTestCase


class ArchitectureTests(BotTestCase):
    def draft(self, **changes):
        draft = ApplicationDraft(ApplicationKind.LOST, "Рыжик", "Небольшой рыжий кот", "Советский", "", "photo", uuid4().hex)
        return replace(draft, **changes)

    async def test_service_checks_admin_rights_without_telegram_filters(self):
        application_id = await self.create("moderation")
        complaint_id = await self.db.add_complaint(application_id, 201, "Test")
        for operation in (
            lambda: self.services.moderation.approve(201, application_id),
            lambda: self.services.moderation.reject(201, application_id, "Test"),
            lambda: self.services.moderation.set_ban(201, 101, True, "Test"),
            lambda: self.services.moderation.resolve_complaint(201, complaint_id, True),
            lambda: self.services.moderation.dashboard(201),
        ):
            with self.assertRaises(AccessDenied):
                await operation()
        self.assertEqual((await self.db.get_application(application_id)).status, ApplicationStatus.MODERATION)
        self.assertFalse((await self.db.get_user(101)).is_banned)
        self.assertEqual(await self.rows("SELECT * FROM logs"), [])
        self.assertEqual(await self.rows("SELECT * FROM notification_outbox"), [])

    async def test_service_checks_owner_status_and_submission_validation(self):
        application_id = await self.create("rejected")
        for actor in (101, 201):
            with self.assertRaises(ApplicationUnavailable):
                await self.services.applications.change_status(actor, application_id, ApplicationStatus.ACTIVE)
        with self.assertRaises(ApplicationUnavailable):
            await self.services.applications.delete_permanently(201, application_id)
        with self.assertRaises(ValidationError):
            await self.services.applications.submit(201, self.draft(description="A" * 2001))
        with self.assertRaises(AccessDenied):
            await self.services.applications.submit(999, self.draft())
        self.assertEqual((await self.rows("SELECT COUNT(*) FROM applications"))[0][0], 1)

    async def test_submission_audit_and_delivery_are_one_transaction(self):
        with patch.object(OutboxRepository, "enqueue", AsyncMock(side_effect=RuntimeError("queue storage failure"))):
            with self.assertRaises(RuntimeError):
                await self.services.applications.submit(201, self.draft())
        self.assertEqual(await self.rows("SELECT * FROM applications"), [])
        self.assertEqual(await self.rows("SELECT * FROM logs"), [])
        self.assertEqual(await self.rows("SELECT * FROM notification_outbox"), [])
        draft = self.draft()
        first, second = await asyncio.gather(self.services.applications.submit(201, draft), self.services.applications.submit(201, draft))
        self.assertEqual(first.id, second.id)
        self.assertEqual((await self.rows("SELECT COUNT(*) FROM logs"))[0][0], 1)
        self.assertEqual(await self.rows("SELECT recipient_id, status FROM notification_outbox"), [(9001, "pending")])
        self.assertEqual(self.outgoing, [])

    async def test_approval_rolls_back_if_notification_cannot_be_queued(self):
        application_id = await self.create("moderation")
        with patch.object(OutboxRepository, "enqueue", AsyncMock(side_effect=RuntimeError("queue storage failure"))):
            with self.assertRaises(RuntimeError):
                await self.services.moderation.approve(9001, application_id)
        self.assertEqual((await self.db.get_application(application_id)).status, ApplicationStatus.MODERATION)
        self.assertEqual(await self.rows("SELECT * FROM logs"), [])
        await self.services.accounts.set_notifications(201, "city")
        await self.services.moderation.approve(9001, application_id)
        self.assertEqual(await self.rows("SELECT recipient_id, kind FROM notification_outbox ORDER BY id"), [(101, "approved"), (201, "published")])
        with self.assertRaises(ApplicationUnavailable):
            await self.services.moderation.approve(9001, application_id)
        self.assertEqual((await self.rows("SELECT COUNT(*) FROM notification_outbox"))[0][0], 2)

    async def test_response_rolls_back_together_with_counter_and_audit(self):
        application_id = await self.create()
        with patch.object(OutboxRepository, "enqueue", AsyncMock(side_effect=RuntimeError("queue storage failure"))):
            with self.assertRaises(RuntimeError):
                await self.services.applications.respond(201, application_id, "Park")
        self.assertEqual((await self.db.get_application(application_id)).responses, 0)
        self.assertEqual(await self.rows("SELECT * FROM responses"), [])
        self.assertEqual(await self.rows("SELECT * FROM logs"), [])

    async def test_network_error_retries_using_persisted_schedule(self):
        application_id = await self.create()
        await self.services.applications.respond(201, application_id, "Park")
        now = [int(time.time())]
        worker = NotificationWorker(self.services.database, self.bot, self.settings, clock=lambda: now[0])
        original = self.bot.session.make_request
        failed = False

        async def network(bot, method, timeout=None):
            nonlocal failed
            if not failed:
                failed = True
                raise TelegramNetworkError(method, "offline")
            return await original(bot, method, timeout)

        self.bot.session.make_request = network
        self.assertTrue(await worker.process_one())
        self.assertEqual(await self.rows("SELECT status, attempts FROM notification_outbox"), [("pending", 1)])
        self.assertFalse(await worker.process_one())
        now[0] += 3
        restarted = NotificationWorker(self.services.database, self.bot, self.settings, clock=lambda: now[0])
        self.assertTrue(await restarted.process_one())
        self.assertEqual(await self.rows("SELECT status, attempts, last_error FROM notification_outbox"), [("sent", 2, None)])
        self.assertEqual(len(self.outgoing), 1)

    async def test_rate_limit_uses_retry_after(self):
        application_id = await self.create()
        await self.services.applications.respond(201, application_id, "Park")
        await self.services.applications.respond(102, application_id, "Second message")
        now = int(time.time())

        async def limited(bot, method, timeout=None):
            raise TelegramRetryAfter(method, "Too Many Requests", retry_after=17)

        self.bot.session.make_request = limited
        worker = NotificationWorker(self.services.database, self.bot, self.settings, clock=lambda: now)
        await worker.process_one()
        self.assertEqual((await self.rows("SELECT status, available_at FROM notification_outbox ORDER BY id"))[0], ("pending", now + 17))
        self.assertFalse(await worker.process_one())
        restarted = NotificationWorker(self.services.database, self.bot, self.settings, clock=lambda: now)
        self.assertFalse(await restarted.process_one())

    async def test_failed_notification_can_be_retried_explicitly(self):
        application_id = await self.create()
        await self.services.applications.respond(201, application_id, "Park")
        original = self.bot.session.make_request

        async def forbidden(bot, method, timeout=None):
            raise TelegramForbiddenError(method, "bot was blocked by the user")

        self.bot.session.make_request = forbidden
        await self.worker.process_one()
        async with self.services.database.connection(write=True) as connection:
            outbox = OutboxRepository(connection)
            failures = await outbox.failures()
            self.assertEqual(len(failures), 1)
            self.assertTrue(await outbox.retry_failed(failures[0]["id"], int(time.time())))
            self.assertFalse(await outbox.retry_failed(failures[0]["id"], int(time.time())))
        self.bot.session.make_request = original
        await self.worker.process_one()
        self.assertEqual(await self.rows("SELECT status, attempts FROM notification_outbox"), [("sent", 1)])

    async def test_support_and_all_admin_views_use_the_same_models(self):
        application_id = await self.create("moderation")
        await self.feed(data="support")
        await self.feed(data="support_complaint")
        await self.feed(text=str(application_id))
        await self.feed(text="Причина <проверка> & текст")
        complaint_id = (await self.rows("SELECT id FROM complaints"))[0][0]
        for callback in (
            "admin_enter_mode", "admin_stats", "admin_users_list", "admin_logs",
            "admin_moderation_list", f"admin_moderate_{application_id}", "admin_complaints_list",
            f"admin_complaint_view_{complaint_id}", "admin_user_detail_201",
        ):
            await self.feed(9001, data=callback)
        await self.feed(9001, data=f"admin_complaint_confirm_{complaint_id}")
        self.assertEqual((await self.db.get_application(application_id)).status, ApplicationStatus.REJECTED)
        await self.feed(data="support")
        await self.feed(data="support_idea")
        await self.feed(text="Предложение <текст>")
        self.assertEqual((await self.rows("SELECT COUNT(*) FROM notification_outbox WHERE kind='support'"))[0][0], 1)

    async def test_invalid_callback_ids_are_rejected_before_database_access(self):
        for user_id, callback in ((9001, "admin_approve_bad"), (201, "app_pause_-1"), (201, "my_app_manage_99999999999999999999999999999999999999999")):
            await self.feed(user_id, data=callback)
            self.assertEqual(self.outgoing[-1].__api_method__, "answerCallbackQuery")
        self.assertEqual(await self.rows("SELECT * FROM applications"), [])

    async def test_permanent_failure_is_visible_and_does_not_block_queue(self):
        application_id = await self.create()
        await self.services.applications.respond(201, application_id, "First")
        await self.services.applications.respond(102, application_id, "Second")
        original = self.bot.session.make_request
        failed = False

        async def forbidden(bot, method, timeout=None):
            nonlocal failed
            if not failed:
                failed = True
                raise TelegramForbiddenError(method, "bot was blocked by the user")
            return await original(bot, method, timeout)

        self.bot.session.make_request = forbidden
        await self.worker.drain()
        self.assertEqual(await self.rows("SELECT status FROM notification_outbox ORDER BY id"), [("failed",), ("sent",)])
        self.assertEqual((await self.services.moderation.dashboard(9001)).failed_notifications, 1)

    async def test_expired_delivery_lease_is_recovered_after_restart(self):
        application_id = await self.create()
        await self.services.applications.respond(201, application_id, "Park")
        now = int(time.time())
        async with self.services.database.connection(write=True) as connection:
            job = await OutboxRepository(connection).claim(now)
        self.assertIsNotNone(job)
        worker = NotificationWorker(self.services.database, self.bot, self.settings, clock=lambda: now + 59)
        self.assertFalse(await worker.process_one())
        recovered = NotificationWorker(self.services.database, self.bot, self.settings, clock=lambda: now + 61)
        self.assertTrue(await recovered.process_one())
        self.assertEqual(await self.rows("SELECT status, attempts FROM notification_outbox"), [("sent", 2)])

    async def test_dialog_and_submission_key_survive_dispatcher_restart(self):
        await self.feed(data="lost_pet")
        await self.feed(photo=True)
        await self.feed(text="Рыжик")
        expected_state = await self.state().get_state()
        expected_data = await self.state().get_data()
        await self.dp.fsm.close()
        self.dp = create_dispatcher(Services.create(self.settings))
        self.assertEqual(await self.state().get_state(), expected_state)
        self.assertEqual(await self.state().get_data(), expected_data)
        await self.feed(text="Рыжий кот")
        await self.feed(data="district_Советский")
        await self.feed(text="-")
        await self.feed(data="confirm_ok")
        self.assertEqual((await self.rows("SELECT submission_key FROM applications"))[0][0], expected_data["submission_key"])

    async def test_storage_keys_are_isolated_and_data_updates_are_atomic(self):
        storage = SQLiteStorage(self.services.database)
        first = StorageKey(bot_id=self.bot.id, chat_id=201, user_id=201, thread_id=1)
        second = replace(first, thread_id=2)
        other_bot = replace(first, bot_id=self.bot.id + 1)
        await storage.set_state(first, "first")
        await storage.set_state(second, "second")
        self.assertEqual(await storage.get_state(first), "first")
        self.assertEqual(await storage.get_state(second), "second")
        self.assertIsNone(await storage.get_state(other_bot))
        await asyncio.gather(storage.update_data(first, {"a": 1}), storage.update_data(first, {"b": 2}))
        self.assertEqual(await storage.get_data(first), {"a": 1, "b": 2})

    async def test_daily_jobs_and_one_week_reminder_survive_restart(self):
        active = await self.create()
        deleted = await self.create("deleted")
        await self.db.add_response(deleted, 201, "Park", "")
        await self.db.add_complaint(deleted, 201, "Test")
        async with self.services.database.connection(write=True) as connection:
            await connection.execute("UPDATE applications SET created_at=datetime('now', '-8 days') WHERE id=?", (active,))
            await connection.execute("UPDATE applications SET deleted_at=datetime('now', '-8 days') WHERE id=?", (deleted,))
        now = int(time.time())
        self.assertTrue(await self.services.maintenance.run_due(now))
        self.assertIsNone(await self.db.get_application(deleted))
        self.assertEqual(await self.rows("SELECT * FROM responses"), [])
        self.assertEqual(await self.rows("SELECT * FROM complaints"), [])
        self.assertEqual(await self.rows("SELECT kind FROM notification_outbox"), [("reminder",)])
        restarted = Services.create(self.settings)
        self.assertFalse(await restarted.maintenance.run_due(now + 60))
        self.assertTrue(await restarted.maintenance.run_due(now + 86400))
        self.assertEqual((await self.rows("SELECT COUNT(*) FROM notification_outbox"))[0][0], 1)

    async def test_delete_data_removes_sessions_and_queued_or_delivered_payloads(self):
        target = await self.create()
        await self.services.applications.respond(201, target, "Personal text")
        await self.worker.drain()
        await self.services.applications.submit(201, self.draft())
        await self.services.applications.respond(102, target, "Unrelated text")
        await self.state().set_state(self.user.CreateApplication.waiting_for_name)
        await self.state().set_data({"personal": "text"})
        await self.services.accounts.delete_data(201)
        self.assertEqual(await self.rows("SELECT * FROM dialog_sessions WHERE user_id=201"), [])
        self.assertEqual(await self.rows("SELECT subject_user_id FROM notification_outbox"), [(102,)])
        self.assertEqual((await self.db.get_application(target)).responses, 1)

    async def test_migrations_are_versioned_and_connections_enforce_foreign_keys(self):
        await self.db.init_db()
        self.assertEqual(await self.rows("SELECT version FROM schema_migrations ORDER BY version"), [(1,), (2,)])
        async with self.services.database.connection() as connection:
            async with connection.execute("PRAGMA foreign_keys") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 1)
