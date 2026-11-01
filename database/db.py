import aiosqlite
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "database.db"

NOVOSIBIRSK_DISTRICTS = [
    "Заельцовский", "Дзержинский", "Железнодорожный", "Калининский",
    "Кировский", "Ленинский", "Октябрьский", "Первомайский",
    "Советский", "Центральный"
]

def get_district_prepositional(district: str) -> str:
    mapping = {
        "Заельцовский": "Заельцовском", "Дзержинский": "Дзержинском",
        "Железнодорожный": "Железнодорожном", "Калининский": "Калининском",
        "Кировский": "Кировском", "Ленинский": "Ленинском",
        "Октябрьский": "Октябрьском", "Первомайский": "Первомайском",
        "Советский": "Советском", "Центральный": "Центральном",
    }
    return mapping.get(district, district)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
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
        
        try: await db.execute("ALTER TABLE applications ADD COLUMN reject_reason TEXT DEFAULT ''")
        except Exception: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN notification_mode TEXT DEFAULT 'none'")
        except Exception: pass
        
        await db.commit()
        print("База данных инициализирована")

async def add_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone() is None:
                await db.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username, first_name))
                await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def set_notification_mode(user_id: int, mode: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET notification_mode = ? WHERE user_id = ?", (mode, user_id))
        await db.commit()

async def ban_user(user_id: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))
        await db.commit()

async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 0, ban_reason = '' WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_all_users_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor: return (await cursor.fetchone())[0]

async def get_applications_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status != 'deleted'") as cursor: return (await cursor.fetchone())[0]

async def get_applications_by_status(status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status = ?", (status,)) as cursor: return (await cursor.fetchone())[0]

async def create_application(user_id: int, app_type: str, pet_name: str, description: str, district: str, additional_info: str, photo_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO applications (user_id, type, pet_name, description, district, additional_info, photo_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, app_type, pet_name, description, district, additional_info, photo_id))
        await db.commit()
        return cursor.lastrowid

async def get_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM applications WHERE id = ?", (app_id,)) as cursor: return await cursor.fetchone()

async def get_applications_by_status_list(status: str, limit: int = 100, offset: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM applications WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (status, limit, offset)) as cursor: return await cursor.fetchall()

async def get_active_applications(limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM applications WHERE status = 'active' ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor: return await cursor.fetchall()

async def update_application_status(app_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
        await db.commit()

async def reject_application(app_id: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET status = 'rejected', reject_reason = ? WHERE id = ?", (reason, app_id))
        await db.commit()

async def soft_delete_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET status = 'deleted', deleted_at = ? WHERE id = ?", (datetime.now().isoformat(), app_id))
        await db.commit()

async def hard_delete_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        await db.commit()

async def increment_views(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET views = views + 1 WHERE id = ?", (app_id,))
        await db.commit()

async def add_response(application_id: int, user_id: int, location: str, message: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO responses (application_id, user_id, location, message) VALUES (?, ?, ?, ?)", (application_id, user_id, location, message))
        await db.execute("UPDATE applications SET responses = responses + 1 WHERE id = ?", (application_id,))
        await db.commit()

async def add_complaint(application_id: int, reporter_id: int, reason: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO complaints (application_id, reporter_id, reason) VALUES (?, ?, ?)", (application_id, reporter_id, reason))
        await db.commit()
        return cursor.lastrowid

async def add_log(user_id: int, action: str, details: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)", (user_id, action, details))
        await db.commit()

async def delete_user_data(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM responses WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM complaints WHERE reporter_id = ?", (user_id,))
        await db.commit()

async def get_users_for_notification(district: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id FROM users 
            WHERE notification_mode = 'city'
               OR (notification_mode = 'district' AND district = ?)
        """, (district,)) as cursor:
            return [row[0] for row in await cursor.fetchall()]

async def search_applications(query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT * FROM applications 
            WHERE status != 'deleted' AND (
                CAST(id AS TEXT) LIKE ? OR 
                pet_name LIKE ? OR 
                district LIKE ?
            ) ORDER BY created_at DESC LIMIT 20
        """, (f"%{query}%", f"%{query}%", f"%{query}%")) as cursor:
            return await cursor.fetchall()

async def get_7_day_reminder_applications():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, user_id, pet_name FROM applications 
            WHERE status = 'active' AND created_at <= datetime('now', '-7 days')
        """) as cursor:
            return await cursor.fetchall()

async def cleanup_old_deleted_applications():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM applications 
            WHERE status = 'deleted' AND deleted_at <= datetime('now', '-7 days')
        """)
        await db.commit()