from dataclasses import dataclass
from enum import Enum
from typing import Any


class ApplicationKind(str, Enum):
    LOST = "lost"
    FOUND = "found"


class ApplicationStatus(str, Enum):
    MODERATION = "moderation"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    REJECTED = "rejected"
    DELETED = "deleted"


class NotificationMode(str, Enum):
    NONE = "none"
    CITY = "city"
    DISTRICT = "district"


class ComplaintStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class NotificationKind(str, Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    BANNED = "banned"
    UNBANNED = "unbanned"
    RESPONSE = "response"
    COMPLAINT = "complaint"
    SUPPORT = "support"
    REMINDER = "reminder"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    first_name: str
    role: str
    is_banned: bool
    ban_reason: str
    notification_mode: NotificationMode
    district: str | None
    created_at: str

    @property
    def display_name(self) -> str:
        return f"@{self.username}" if self.username else self.first_name or str(self.id)


@dataclass(frozen=True)
class Application:
    id: int
    user_id: int
    kind: ApplicationKind
    pet_name: str
    description: str
    district: str
    additional_info: str
    photo_id: str
    status: ApplicationStatus
    reject_reason: str
    views: int
    responses: int
    deleted_at: str | None
    created_at: str
    submission_key: str | None


@dataclass(frozen=True)
class ApplicationDraft:
    kind: ApplicationKind
    pet_name: str
    description: str
    district: str
    additional_info: str
    photo_id: str
    submission_key: str


@dataclass(frozen=True)
class Complaint:
    id: int
    application_id: int
    reporter_id: int
    reason: str
    status: ComplaintStatus
    created_at: str
    application_name: str | None
    district: str | None
    author_id: int | None


@dataclass(frozen=True)
class AuditEntry:
    id: int
    user_id: int
    action: str
    details: str
    created_at: str


@dataclass(frozen=True)
class Dashboard:
    users: int
    banned_users: int
    applications: dict[ApplicationStatus, int]
    pending_complaints: int
    pending_notifications: int
    failed_notifications: int


@dataclass(frozen=True)
class Notification:
    id: int
    recipient_id: int
    kind: NotificationKind
    payload: dict[str, Any]
    attempts: int


OWNER_TRANSITIONS = {
    ApplicationStatus.PAUSED: (ApplicationStatus.ACTIVE,),
    ApplicationStatus.ACTIVE: (ApplicationStatus.PAUSED,),
    ApplicationStatus.CLOSED: (ApplicationStatus.ACTIVE, ApplicationStatus.PAUSED),
    ApplicationStatus.DELETED: (ApplicationStatus.ACTIVE, ApplicationStatus.PAUSED),
}
