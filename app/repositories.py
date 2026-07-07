from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalAuditLog, ApprovalRequest, OutboxEvent


class ApprovalRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, request: ApprovalRequest) -> ApprovalRequest:
        self.db.add(request)
        self.db.flush()
        return request

    def get_by_id(self, workspace_id: str, request_id: str) -> ApprovalRequest | None:
        statement = select(ApprovalRequest).where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.id == request_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_by_idempotency_key(self, workspace_id: str, key: str) -> ApprovalRequest | None:
        statement = select(ApprovalRequest).where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.idempotency_key == key,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_by_workspace(self, workspace_id: str) -> list[ApprovalRequest]:
        statement = (
            select(ApprovalRequest)
            .where(ApprovalRequest.workspace_id == workspace_id)
            .order_by(ApprovalRequest.created_at.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def add_audit_log(self, log: ApprovalAuditLog) -> ApprovalAuditLog:
        self.db.add(log)
        return log

    def add_outbox_event(self, event: OutboxEvent) -> OutboxEvent:
        self.db.add(event)
        return event

