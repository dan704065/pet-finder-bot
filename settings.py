from dataclasses import dataclass, field
from importlib import import_module
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(repr=False)
    admin_ids: frozenset[int] = field(default_factory=frozenset)
    database_path: Path = Path(__file__).parent / "database.db"
    log_path: Path = Path(__file__).parent / "logs" / "bot.log"
    support_url: str = "https://t.me/dan704035"

    @classmethod
    def load(cls):
        # Existing private config.py remains supported, while imports stay side-effect free.
        try:
            legacy = import_module("config")
        except ModuleNotFoundError as exc:
            if exc.name != "config":
                raise
            legacy = None
        token = os.environ.get("BOT_TOKEN") or getattr(legacy, "BOT_TOKEN", "")
        if not token:
            raise RuntimeError("Задайте BOT_TOKEN в окружении или config.py. См. README.md.")
        raw_admins = os.environ.get("ADMIN_IDS")
        admins = frozenset(int(value.strip()) for value in raw_admins.split(",") if value.strip()) if raw_admins is not None else frozenset(getattr(legacy, "ADMIN_IDS", ()))
        return cls(
            bot_token=token,
            admin_ids=admins,
            database_path=Path(os.environ.get("DATABASE_PATH", cls.database_path)),
            log_path=Path(os.environ.get("LOG_PATH", cls.log_path)),
        )
