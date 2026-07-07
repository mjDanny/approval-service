from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ApprovalStatus, SourceType


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ApprovalRequestCreate(ApiModel):
    source_type: SourceType = Field(alias="sourceType")
    source_id: str = Field(min_length=1, max_length=256, alias="sourceId")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    reviewer_user_ids: list[str] = Field(min_length=1, alias="reviewerUserIds")

    @field_validator("source_id", "title")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("reviewer_user_ids")
    @classmethod
    def non_empty_reviewers(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("reviewerUserIds must not contain empty strings")
        return cleaned


class ApproveRequest(ApiModel):
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RejectRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def non_empty_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be empty")
        return stripped


class CancelRequest(RejectRequest):
    pass


class ApprovalRequestResponse(ApiModel):
    id: str
    workspace_id: str
    source_type: SourceType
    source_id: str
    title: str
    description: str | None
    reviewer_user_ids: list[str]
    status: ApprovalStatus
    created_by: str
    decided_by: str | None
    decision_comment: str | None
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None

