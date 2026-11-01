from repositories.applications import ApplicationRepository
from repositories.audit import AuditRepository
from repositories.maintenance import MaintenanceRepository
from repositories.moderation import ComplaintRepository
from repositories.outbox import OutboxRepository
from repositories.users import UserRepository


class Repositories:
    """All repositories use one connection and one transaction for a use case."""

    def __init__(self, connection):
        self.users = UserRepository(connection)
        self.applications = ApplicationRepository(connection)
        self.complaints = ComplaintRepository(connection)
        self.audit = AuditRepository(connection)
        self.outbox = OutboxRepository(connection)
        self.maintenance = MaintenanceRepository(connection)
