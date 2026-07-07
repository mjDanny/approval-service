from sqlalchemy import select

from app.models import ApprovalAuditLog, ApprovalRequest, OutboxEvent


BASE_PATH = "/api/v1/workspaces/ws_1/approval-requests"


def auth_headers(actions: str, user_id: str = "usr_1") -> dict[str, str]:
    return {"X-User-Id": user_id, "X-User-Actions": actions}


def create_payload(**overrides):
    payload = {
        "sourceType": "publication",
        "sourceId": "pub_123",
        "title": "Instagram reel draft",
        "description": "Needs final approval",
        "reviewerUserIds": ["usr_2", "usr_3"],
    }
    payload.update(overrides)
    return payload


def create_request(client, workspace_id: str = "ws_1", extra_headers: dict[str, str] | None = None):
    headers = auth_headers("approval:create")
    if extra_headers:
        headers.update(extra_headers)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/approval-requests",
        json=create_payload(),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ok"}


def test_create_request(client):
    response = client.post(BASE_PATH, json=create_payload(), headers=auth_headers("approval:create"))

    assert response.status_code == 201
    body = response.json()
    assert body["workspaceId"] == "ws_1"
    assert body["sourceType"] == "publication"
    assert body["sourceId"] == "pub_123"
    assert body["reviewerUserIds"] == ["usr_2", "usr_3"]
    assert body["status"] == "pending"
    assert body["createdBy"] == "usr_1"
    assert body["decidedBy"] is None


def test_list_requests_in_workspace(client):
    first = create_request(client, "ws_1")
    create_request(client, "ws_2")

    response = client.get(BASE_PATH, headers=auth_headers("approval:read"))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == first["id"]
    assert body[0]["workspaceId"] == "ws_1"


def test_get_request(client):
    created = create_request(client)

    response = client.get(f"{BASE_PATH}/{created['id']}", headers=auth_headers("approval:read"))

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_workspace_isolation_returns_404(client):
    created = create_request(client, "ws_1")

    response = client.get(
        f"/api/v1/workspaces/ws_2/approval-requests/{created['id']}",
        headers=auth_headers("approval:read"),
    )

    assert response.status_code == 404


def test_approve_pending_request(client):
    created = create_request(client)

    response = client.post(
        f"{BASE_PATH}/{created['id']}/approve",
        json={"comment": "Approved"},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["decidedBy"] == "usr_2"
    assert body["decisionComment"] == "Approved"
    assert body["decisionReason"] is None
    assert body["decidedAt"] is not None


def test_reject_pending_request(client):
    created = create_request(client)

    response = client.post(
        f"{BASE_PATH}/{created['id']}/reject",
        json={"reason": "Brand tone is wrong"},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["decisionReason"] == "Brand tone is wrong"


def test_cancel_pending_request(client):
    created = create_request(client)

    response = client.post(
        f"{BASE_PATH}/{created['id']}/cancel",
        json={"reason": "Draft was removed"},
        headers=auth_headers("approval:cancel", user_id="usr_1"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["decisionReason"] == "Draft was removed"


def test_final_request_cannot_be_changed(client):
    created = create_request(client)
    approve = client.post(
        f"{BASE_PATH}/{created['id']}/approve",
        json={"comment": "Approved"},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )
    assert approve.status_code == 200

    response = client.post(
        f"{BASE_PATH}/{created['id']}/reject",
        json={"reason": "Changed mind"},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )

    assert response.status_code == 409
    assert "already finalized" in response.json()["detail"]


def test_idempotency_key_does_not_create_duplicate(client, db_session):
    headers = auth_headers("approval:create")
    headers["Idempotency-Key"] = "create-pub-123"

    first = client.post(BASE_PATH, json=create_payload(), headers=headers)
    second = client.post(BASE_PATH, json=create_payload(title="Changed title"), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["title"] == "Instagram reel draft"

    requests = db_session.execute(select(ApprovalRequest)).scalars().all()
    assert len(requests) == 1


def test_missing_permission_returns_403(client):
    response = client.post(BASE_PATH, json=create_payload(), headers=auth_headers("approval:read"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing permission: approval:create"


def test_missing_user_id_returns_401(client):
    response = client.get(BASE_PATH, headers={"X-User-Actions": "approval:read"})

    assert response.status_code == 401
    assert response.json()["detail"] == "X-User-Id header is required"


def test_audit_log_created_after_successful_change(client, db_session):
    created = create_request(client)

    response = client.post(
        f"{BASE_PATH}/{created['id']}/approve",
        json={"comment": "Approved"},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )

    assert response.status_code == 200
    logs = db_session.execute(
        select(ApprovalAuditLog).where(ApprovalAuditLog.request_id == created["id"])
    ).scalars().all()
    actions = {log.action for log in logs}
    assert actions == {"create", "approve"}
    approve_log = next(log for log in logs if log.action == "approve")
    assert approve_log.old_status == "pending"
    assert approve_log.new_status == "approved"
    assert approve_log.actor_user_id == "usr_2"


def test_outbox_event_created_after_creation_and_decision(client, db_session):
    created = create_request(client)

    response = client.post(
        f"{BASE_PATH}/{created['id']}/reject",
        json={"reason": "Brand tone is wrong"},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )

    assert response.status_code == 200
    events = db_session.execute(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == created["id"])
    ).scalars().all()
    assert [event.event_type for event in events] == [
        "approval_request.created",
        "approval_request.rejected",
    ]
    assert events[1].payload_json["decisionReason"] == "Brand tone is wrong"


def test_validation_rejects_empty_reviewers_and_reason(client):
    invalid_create = client.post(
        BASE_PATH,
        json=create_payload(reviewerUserIds=["usr_2", ""]),
        headers=auth_headers("approval:create"),
    )
    assert invalid_create.status_code == 422

    created = create_request(client)
    invalid_reject = client.post(
        f"{BASE_PATH}/{created['id']}/reject",
        json={"reason": " "},
        headers=auth_headers("approval:decide", user_id="usr_2"),
    )
    assert invalid_reject.status_code == 422

