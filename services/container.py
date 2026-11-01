from dataclasses import dataclass

from database.connection import Database
from services.accounts import AccountService
from services.applications import ApplicationService
from services.maintenance import MaintenanceService
from services.moderation import ModerationService
from services.support import SupportService
from settings import Settings


@dataclass(frozen=True)
class Services:
    database: Database
    settings: Settings
    accounts: AccountService
    applications: ApplicationService
    moderation: ModerationService
    support: SupportService
    maintenance: MaintenanceService

    @classmethod
    def create(cls, settings: Settings, database: Database | None = None):
        database = database or Database(settings.database_path)
        return cls(database, settings, AccountService(database), ApplicationService(database, settings), ModerationService(database, settings), SupportService(database, settings), MaintenanceService(database))
