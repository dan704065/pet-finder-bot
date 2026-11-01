from database.connection import Database
import time


async def _initial_schema(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        role TEXT DEFAULT 'user', is_banned INTEGER DEFAULT 0,
        ban_reason TEXT DEFAULT '', notification_mode TEXT DEFAULT 'none',
        district TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    await db.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT,
        pet_name TEXT, description TEXT, district TEXT, additional_info TEXT,
        photo_id TEXT, status TEXT DEFAULT 'moderation', reject_reason TEXT DEFAULT '',
        views INTEGER DEFAULT 0, responses INTEGER DEFAULT 0, deleted_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id))""")

    await db.execute("""CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER, user_id INTEGER,
        location TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (application_id) REFERENCES applications(id),
        FOREIGN KEY (user_id) REFERENCES users(user_id))""")

    await db.execute("""CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER, reporter_id INTEGER,
        reason TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (application_id) REFERENCES applications(id))""")

    await db.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT,
        details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    for table, column, definition in (
        ("applications", "reject_reason", "TEXT DEFAULT ''"),
        ("users", "notification_mode", "TEXT DEFAULT 'none'"),
    ):
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}
        if column not in existing_columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    async with db.execute("PRAGMA table_info(applications)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if "submission_key" not in columns:
        await db.execute("ALTER TABLE applications ADD COLUMN submission_key TEXT")
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS application_submission_key ON applications(submission_key)")
    await db.execute("CREATE INDEX IF NOT EXISTS application_feed ON applications(status, district, created_at, id)")

    async with db.execute("PRAGMA table_info(logs)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    for column in ("subject_user_id", "application_id"):
        if column not in columns:
            await db.execute(f"ALTER TABLE logs ADD COLUMN {column} INTEGER")


async def _durable_workflows(db):
    await db.execute("""CREATE TABLE notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL UNIQUE,
        recipient_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        application_id INTEGER,
        subject_user_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        available_at INTEGER NOT NULL,
        locked_until INTEGER,
        last_error TEXT,
        created_at INTEGER NOT NULL,
        delivered_at INTEGER)""")
    await db.execute("CREATE INDEX outbox_due ON notification_outbox(status, available_at, locked_until)")
    await db.execute("""CREATE TABLE dialog_sessions (
        session_key TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
        state TEXT, data TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL)""")
    await db.execute("CREATE INDEX dialog_user ON dialog_sessions(user_id)")
    await db.execute("""CREATE TABLE scheduled_jobs (
        name TEXT PRIMARY KEY, next_run_at INTEGER NOT NULL, last_run_at INTEGER)""")
    await db.execute("""CREATE TABLE application_reminders (
        application_id INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
        queued_at INTEGER NOT NULL)""")


MIGRATIONS = ((1, "initial_schema", _initial_schema), (2, "durable_workflows", _durable_workflows))


async def migrate(database: Database) -> None:
    database.path.parent.mkdir(parents=True, exist_ok=True)
    async with database.connection() as connection:
        async with connection.execute("PRAGMA journal_mode = WAL") as cursor:
            await cursor.fetchone()
    async with database.connection(write=True) as connection:
        await connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL)")
        async with connection.execute("SELECT version FROM schema_migrations") as cursor:
            applied = {row[0] for row in await cursor.fetchall()}
        if applied and max(applied) > MIGRATIONS[-1][0]:
            raise RuntimeError("Database schema is newer than this application")
        for version, name, migration in MIGRATIONS:
            if version not in applied:
                await migration(connection)
                await connection.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)", (version, name, int(time.time())))
