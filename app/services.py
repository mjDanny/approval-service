from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.enums import ApprovalAction, ApprovalStatus
from app.models import ApprovalAuditLog, ApprovalRequest, OutboxEvent
from app.repositories import ApprovalRequestRepository
from app.schemas import ApprovalRequestCreate, ApproveRequest, CancelRequest, RejectRequest
from app.utils.sanitization import clean_optional_text, clean_required_text, sanitize_payload


class ApprovalRequestNotFoundError(Exception):
    pass


class ApprovalRequestConflictError(Exception):
    pass


@dataclass(frozen=True)
class CreateApprovalResult:
    request: ApprovalRequest
    created: bool


class ApprovalRequestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ApprovalRequestRepository(db)

    def create_request(
        self,
        workspace_id: str,
        data: ApprovalRequestCreate,
        user: CurrentUser,
        idempotency_key: str | None,
    ) -> CreateApprovalResult:
        # Idempotency is scoped by workspace_id so clients can safely retry create requests.
        if idempotency_key:
            existing = self.repo.get_by_idempotency_key(workspace_id, idempotency_key)
            if existing:
                return CreateApprovalResult(request=existing, created=False)

        request = ApprovalRequest(
            workspace_id=workspace_id,
            source_type=data.source_type.value,
            source_id=clean_required_text(data.source_id),
            title=clean_required_text(data.title),
            description=clean_optional_text(data.description),
            reviewer_user_ids=[clean_required_text(item) for item in data.reviewer_user_ids],
            status=ApprovalStatus.PENDING.value,
            created_by=user.user_id,
            idempotency_key=idempotency_key,
        )

        try:
            self.repo.create(request)
            self._add_audit_log(
                request=request,
                actor_user_id=user.user_id,
                action=ApprovalAction.CREATE,
                old_status=None,
                new_status=ApprovalStatus.PENDING.value,
            )
            self._add_outbox_event("approval_request.created", request)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if idempotency_key:
                existing = self.repo.get_by_idempotency_key(workspace_id, idempotency_key)
                if existing:
                    return CreateApprovalResult(request=existing, created=False)
            raise

        self.db.refresh(request)
        return CreateApprovalResult(request=request, created=True)

    def list_requests(self, workspace_id: str) -> list[ApprovalRequest]:
        return self.repo.list_by_workspace(workspace_id)

    def get_request(self, workspace_id: str, request_id: str) -> ApprovalRequest:
        request = self.repo.get_by_id(workspace_id, request_id)
        if request is None:
            raise ApprovalRequestNotFoundError
        return request

    def approve_request(
        self,
        workspace_id: str,
        request_id: str,
        data: ApproveRequest,
        user: CurrentUser,
    ) -> ApprovalRequest:
        return self._finalize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            action=ApprovalAction.APPROVE,
            new_status=ApprovalStatus.APPROVED,
            user=user,
            comment=clean_optional_text(data.comment),
            reason=None,
        )

    def reject_request(
        self,
        workspace_id: str,
        request_id: str,
        data: RejectRequest,
        user: CurrentUser,
    ) -> ApprovalRequest:
        return self._finalize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            action=ApprovalAction.REJECT,
            new_status=ApprovalStatus.REJECTED,
            user=user,
            comment=None,
            reason=clean_required_text(data.reason),
        )

    def cancel_request(
        self,
        workspace_id: str,
        request_id: str,
        data: CancelRequest,
        user: CurrentUser,
    ) -> ApprovalRequest:
        return self._finalize_request(
            workspace_id=workspace_id,
            request_id=request_id,
            action=ApprovalAction.CANCEL,
            new_status=ApprovalStatus.CANCELLED,
            user=user,
            comment=None,
            reason=clean_required_text(data.reason),
        )

    def _finalize_request(
        self,
        workspace_id: str,
        request_id: str,
        action: ApprovalAction,
        new_status: ApprovalStatus,
        user: CurrentUser,
        comment: str | None,
        reason: str | None,
    ) -> ApprovalRequest:
        request = self.get_request(workspace_id, request_id)
        if request.status in ApprovalStatus.final_values():
            # Final states are immutable to avoid conflicting downstream publication decisions.
            raise ApprovalRequestConflictError(
                f"Approval request is already finalized with status '{request.status}'"
            )

        old_status = request.status
        now = datetime.now(timezone.utc)
        request.status = new_status.value
        request.decided_by = user.user_id
        request.decision_comment = comment
        request.decision_reason = reason
        request.decided_at = now
        request.updated_at = now

        self._add_audit_log(
            request=request,
            actor_user_id=user.user_id,
            action=action,
            old_status=old_status,
            new_status=new_status.value,
            comment=comment,
            reason=reason,
        )
        self._add_outbox_event(f"approval_request.{new_status.value}", request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def _add_audit_log(
        self,
        request: ApprovalRequest,
        actor_user_id: str,
        action: ApprovalAction,
        old_status: str | None,
        new_status: str,
        comment: str | None = None,
        reason: str | None = None,
    ) -> None:
        # Audit trail captures successful state changes without storing raw provider payloads.
        self.repo.add_audit_log(
            ApprovalAuditLog(
                workspace_id=request.workspace_id,
                request_id=request.id,
                actor_user_id=actor_user_id,
                action=action.value,
                old_status=old_status,
                new_status=new_status,
                comment=comment,
                reason=reason,
            )
        )

    def _add_outbox_event(self, event_type: str, request: ApprovalRequest) -> None:
        # Outbox event is committed with the domain change and can be published later.
        payload = sanitize_payload(
            {
                "requestId": request.id,
                "workspaceId": request.workspace_id,
                "sourceType": request.source_type,
                "sourceId": request.source_id,
                "title": request.title,
                "reviewerUserIds": request.reviewer_user_ids,
                "status": request.status,
                "createdBy": request.created_by,
                "decidedBy": request.decided_by,
                "decisionComment": request.decision_comment,
                "decisionReason": request.decision_reason,
            }
        )
        self.repo.add_outbox_event(
            OutboxEvent(
                event_type=event_type,
                workspace_id=request.workspace_id,
                aggregate_id=request.id,
                payload_json=payload,
            )
        )

