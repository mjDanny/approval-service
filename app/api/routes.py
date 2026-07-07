from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_permission
from app.database import get_db
from app.enums import Permission
from app.schemas import (
    ApprovalRequestCreate,
    ApprovalRequestResponse,
    ApproveRequest,
    CancelRequest,
    RejectRequest,
)
from app.services import (
    ApprovalRequestConflictError,
    ApprovalRequestNotFoundError,
    ApprovalRequestService,
)

router = APIRouter(prefix="/api/v1", tags=["approval-requests"])


def service_from_db(db: Session) -> ApprovalRequestService:
    return ApprovalRequestService(db)


@router.post(
    "/workspaces/{workspace_id}/approval-requests",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_approval_request(
    workspace_id: str,
    data: ApprovalRequestCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission(Permission.CREATE))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    result = service_from_db(db).create_request(
        workspace_id=workspace_id,
        data=data,
        user=user,
        idempotency_key=idempotency_key,
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.request


@router.get(
    "/workspaces/{workspace_id}/approval-requests",
    response_model=list[ApprovalRequestResponse],
)
def list_approval_requests(
    workspace_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission(Permission.READ))],
):
    return service_from_db(db).list_requests(workspace_id)


@router.get(
    "/workspaces/{workspace_id}/approval-requests/{request_id}",
    response_model=ApprovalRequestResponse,
)
def get_approval_request(
    workspace_id: str,
    request_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission(Permission.READ))],
):
    try:
        return service_from_db(db).get_request(workspace_id, request_id)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found") from exc


@router.post(
    "/workspaces/{workspace_id}/approval-requests/{request_id}/approve",
    response_model=ApprovalRequestResponse,
)
def approve_approval_request(
    workspace_id: str,
    request_id: str,
    data: ApproveRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission(Permission.DECIDE))],
):
    try:
        return service_from_db(db).approve_request(workspace_id, request_id, data, user)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found") from exc
    except ApprovalRequestConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/workspaces/{workspace_id}/approval-requests/{request_id}/reject",
    response_model=ApprovalRequestResponse,
)
def reject_approval_request(
    workspace_id: str,
    request_id: str,
    data: RejectRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission(Permission.DECIDE))],
):
    try:
        return service_from_db(db).reject_request(workspace_id, request_id, data, user)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found") from exc
    except ApprovalRequestConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/workspaces/{workspace_id}/approval-requests/{request_id}/cancel",
    response_model=ApprovalRequestResponse,
)
def cancel_approval_request(
    workspace_id: str,
    request_id: str,
    data: CancelRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission(Permission.CANCEL))],
):
    try:
        return service_from_db(db).cancel_request(workspace_id, request_id, data, user)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found") from exc
    except ApprovalRequestConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

