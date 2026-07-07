from enum import Enum


class SourceType(str, Enum):
    PUBLICATION = "publication"
    SCENARIO = "scenario"
    EDIT = "edit"
    EXTERNAL = "external"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    @classmethod
    def final_values(cls) -> set[str]:
        return {cls.APPROVED.value, cls.REJECTED.value, cls.CANCELLED.value}


class ApprovalAction(str, Enum):
    CREATE = "create"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


class Permission(str, Enum):
    READ = "approval:read"
    CREATE = "approval:create"
    DECIDE = "approval:decide"
    CANCEL = "approval:cancel"

