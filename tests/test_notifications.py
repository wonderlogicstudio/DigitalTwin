"""Contracts for offline, provider-neutral notification previews."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.notifications as notifications
from src.alert_case import AlertCase
from src.notifications import (
    NotificationIntent,
    NotificationRequest,
    NotificationResult,
    NotificationService,
    NullNotificationService,
    PreviewNotificationService,
    build_alert_customer_deep_link,
)


REQUESTED_AT = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _request() -> NotificationRequest:
    return NotificationRequest(
        request_id="NTF-REQUEST-000001",
        requested_at=REQUESTED_AT,
        intent=NotificationIntent(
            intent_id="NTF-INTENT-000001",
            alert_id="ALT-000001",
            customer_id="C000001",
            title="Review case",
            body="A human review work item is ready for review.",
            deep_link=build_alert_customer_deep_link(
                alert_id="ALT-000001",
                customer_id="C000001",
            ),
        ),
    )


def test_model_serialization_and_deep_link_allow_only_alert_customer_parameters() -> None:
    request = _request()

    assert request.to_dict() == {
        "schema_version": "notification.v1",
        "request_id": "NTF-REQUEST-000001",
        "requested_at": "2026-08-23T09:00:00+00:00",
        "intent": {
            "schema_version": "notification.v1",
            "intent_id": "NTF-INTENT-000001",
            "alert_id": "ALT-000001",
            "customer_id": "C000001",
            "title": "Review case",
            "body": "A human review work item is ready for review.",
            "deep_link": "/rm/cases?alert_id=ALT-000001&customer_id=C000001",
        },
    }
    with pytest.raises(ValueError, match="safe identifier"):
        build_alert_customer_deep_link(alert_id="ALT-000001", customer_id="C000001&role=admin")
    with pytest.raises(ValueError, match="allowed alert/customer"):
        NotificationIntent(
            intent_id="NTF-INTENT-000001",
            alert_id="ALT-000001",
            customer_id="C000001",
            title="Review case",
            body="A human review work item is ready for review.",
            deep_link="/rm/cases?alert_id=ALT-000001&customer_id=C000001&role=admin",
        )


def test_preview_is_deterministic_captured_and_never_sent() -> None:
    service = PreviewNotificationService()
    request = _request()

    first = service.notify(request)
    second = service.notify(request)

    assert first.status == second.status == "PREVIEW"
    assert first.sent is False
    assert first.external_delivery_attempted is False
    assert first.captured_preview == second.captured_preview
    assert service.captured_requests == (request, request)
    assert first.to_dict()["sent"] is False


def test_null_result_is_explicitly_not_sent_and_distinct_from_preview() -> None:
    request = _request()
    preview = PreviewNotificationService().notify(request)
    result = NullNotificationService().notify(request)

    assert result.status == "NOT_SENT"
    assert result.sent is False
    assert result.external_delivery_attempted is False
    assert result.captured_preview is None
    assert result != preview
    with pytest.raises(ValueError, match="PREVIEW"):
        NotificationResult(
            request_id=request.request_id,
            intent_id=request.intent.intent_id,
            service_id="invalid",
            status="PREVIEW",
            external_delivery_attempted=False,
            captured_preview=None,
        )


def test_fake_future_adapter_satisfies_protocol_without_a_p0_external_implementation() -> None:
    class FakeFutureAdapter:
        service_id = "future_adapter_fake"

        def notify(self, request: NotificationRequest) -> NotificationResult:
            return NotificationResult(
                request_id=request.request_id,
                intent_id=request.intent.intent_id,
                service_id=self.service_id,
                status="SENT",
                external_delivery_attempted=True,
                captured_preview=None,
            )

    adapter: NotificationService = FakeFutureAdapter()
    result = adapter.notify(_request())
    assert result.status == "SENT"
    assert result.sent is True


def test_alert_model_has_no_notification_or_delivery_fields() -> None:
    field_names = set(AlertCase.__dataclass_fields__)
    assert {"notification", "provider", "channel", "recipient", "webhook"}.isdisjoint(field_names)


def test_notification_import_has_no_network_or_credential_side_effects() -> None:
    source = Path(notifications.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        alias.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "streamlit" not in source.lower()
    assert not any(
        marker in module
        for module in imported_modules
        for marker in ("requests", "http", "socket", "smtp", "boto", "azure", "google", "slack")
    )
    assert "os.getenv" not in source
    assert "environ" not in source
    assert "retry" not in source.lower()
    assert "http://" not in source.lower()
    assert "https://" not in source.lower()
