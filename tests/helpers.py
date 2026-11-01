"""Fixtures may bypass domain policies to exercise stale/corrupt/legacy states."""

from uuid import uuid4
import aiosqlite
from database.connection import Database
from database.migrations import migrate
from domain.models import ApplicationDraft, ApplicationKind
from repositories.session import Repositories
import asyncio
import tempfile
import types
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from aiogram import Bot
from aiogram.types import Update
from bot import create_dispatcher
from handlers import states
from services.container import Services
from settings import Settings
from workers.notifications import NotificationWorker
from utils.messages import plain_text, text_length


class Fixtures:
    def __init__(self, database: Database):
        self.database = database
        self.aiosqlite = aiosqlite

    @property
    def DB_PATH(self):
        return self.database.path

    @DB_PATH.setter
    def DB_PATH(self, path):
        self.database.path = path

    async def init_db(self):
        await migrate(self.database)

    async def add_user(self, user_id, username, first_name):
        async with self.database.connection(write=True) as connection:
            await Repositories(connection).users.register(user_id, username, first_name)

    async def get_user(self, user_id):
        async with self.database.connection() as connection:
            return await Repositories(connection).users.get(user_id)

    async def get_application(self, application_id):
        async with self.database.connection() as connection:
            return await Repositories(connection).applications.get(application_id)

    async def create_application(self, user_id, kind, pet_name, description, district, additional_info, photo_id, submission_key=None):
        draft = ApplicationDraft(ApplicationKind(kind), pet_name, description, district, additional_info, photo_id, submission_key or uuid4().hex)
        async with self.database.connection(write=True) as connection:
            application, _ = await Repositories(connection).applications.create(user_id, draft)
            return application.id

    async def update_application_status(self, application_id, status):
        async with self.database.connection(write=True) as connection:
            await connection.execute("UPDATE applications SET status = ? WHERE id = ?", (status, application_id))

    async def add_response(self, application_id, user_id, location, message):
        async with self.database.connection(write=True) as connection:
            return await Repositories(connection).applications.add_response(application_id, user_id, location)

    async def add_complaint(self, application_id, user_id, reason):
        async with self.database.connection(write=True) as connection:
            return await Repositories(connection).complaints.create(application_id, user_id, reason)

    async def add_log(self, user_id, action, details="", **kwargs):
        async with self.database.connection(write=True) as connection:
            await Repositories(connection).audit.add(user_id, action, details, **kwargs)

    async def get_next_active_application(self, user_id, district=None, excluded_ids=()):
        async with self.database.connection() as connection:
            return await Repositories(connection).applications.next_active(user_id, district, excluded_ids)


class StrictHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in {"b", "i", "code"}:
            raise AssertionError(f"Unescaped user HTML: {tag}")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError(f"Unbalanced HTML: {tag}")


class BotTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1.0
        self.temp = tempfile.TemporaryDirectory(prefix="petfinder-test-")
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(bot_token="123456:" + "x" * 35, admin_ids=frozenset({9001}), database_path=Path(self.temp.name) / "test.db")
        self.services = Services.create(self.settings)
        self.db = Fixtures(self.services.database)
        self.user = states
        await self.db.init_db()
        for user_id in (101, 102, 201, 9001):
            await self.db.add_user(user_id, "", "Tester")
        self.bot = Bot(self.settings.bot_token)
        self.outgoing = []

        async def request(bot, method, timeout=None):
            for field, limit in (("text", 4096), ("caption", 1024)):
                value = getattr(method, field, None)
                if not value:
                    continue
                mode = getattr(method, "parse_mode", None)
                self.assertLessEqual(text_length(plain_text(value, mode)), limit)
                if mode == "HTML":
                    parser = StrictHTML()
                    parser.feed(value)
                    parser.close()
                    self.assertEqual(parser.stack, [])
            self.outgoing.append(method)
            return True

        self.bot.session.make_request = request
        self.dp = create_dispatcher(self.services)
        self.worker = NotificationWorker(self.services.database, self.bot, self.settings)
        self.sequence = 0

    async def asyncTearDown(self):
        await self.dp.fsm.close()
        await self.bot.session.close()

    def state(self, user_id=201):
        return self.dp.fsm.get_context(bot=self.bot, chat_id=user_id, user_id=user_id)

    async def feed(self, user_id=201, *, data=None, text=None, photo=False, first_name="Tester", drain=True):
        self.sequence += 1
        actor = {"id": user_id, "is_bot": False, "first_name": first_name}
        message = {
            "message_id": self.sequence, "date": datetime.now(timezone.utc),
            "chat": {"id": user_id, "type": "private"}, "from": actor,
        }
        if photo:
            message["photo"] = [{"file_id": "photo", "file_unique_id": "unique", "width": 100, "height": 100}]
        else:
            message["text"] = text or "Menu"
        payload = {"update_id": self.sequence}
        if data is not None:
            payload["callback_query"] = {
                "id": str(self.sequence), "from": actor, "chat_instance": "test",
                "message": message, "data": data,
            }
        else:
            if text and text.startswith("/"):
                message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            payload["message"] = message
        result = await self.dp.feed_update(self.bot, Update.model_validate(payload))
        if drain:
            await self.worker.drain()
        return result

    async def create(self, status="active", *, owner=101, district="Советский", description="Рыжий кот", photo=""):
        app_id = await self.db.create_application(owner, "lost", "Рыжик", description, district, "", photo)
        await self.db.update_application_status(app_id, status)
        return app_id

    async def rows(self, query, params=()):
        async with self.db.aiosqlite.connect(self.db.DB_PATH) as connection:
            async with connection.execute(query, params) as cursor:
                return await cursor.fetchall()
