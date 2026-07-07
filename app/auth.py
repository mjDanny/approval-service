from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.enums import Permission


class CurrentUser(BaseModel):
    user_id: str
    actions: set[str]


def get_current_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_actions: Annotated[str | None, Header(alias="X-User-Actions")] = None,
) -> CurrentUser:
    # Local auth stub: gateway/JWT integration can replace this dependency later.
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header is required",
        )

    actions = {
        action.strip()
        for action in (x_user_actions or "").split(",")
        if action.strip()
    }
    return CurrentUser(user_id=x_user_id.strip(), actions=actions)


def require_permission(permission: Permission):
    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if permission.value not in user.actions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission.value}",
            )
        return user

    return dependency

