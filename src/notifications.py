"""Provider-neutral notification contracts with offline-only P0 services.

This module deliberately has no external delivery integration.  Its Preview
and Null services make it possible to inspect the exact request that a future
adapter would receive without requiring a credential, network access, or a
channel choice in the application UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from urllib.parse import urlencode


NOTIFICATION_SCHEMA_VERSION = "notification.v1"
NOTIFICATION_STATUSES = ("PREVIEW", "NOT_SENT", "SENT")
NotificationStatus = Literal["PREVIEW", "NOT_SENT", "SENT"]

_ALLOWED_DEEP_LINK_PARAMETERS = ("alert_id", "customer_id")
_SAFE_IDENTIFIER_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)


class NotificationService(Protocol):
    """Future delivery boundary; P0 implementations never send externally."""

    service_id: str

    def notify(self, request: "NotificationRequest") -> "NotificationResult":
        """Return one explicit result for an immutable notification request."""


@dataclass(frozen=True)
class NotificationIntent:
    """Human-review notification content referring to an existing AlertCase."""

    intent_id: str
    alert_id: str
    customer_id: str
    title: str
    body: str
    deep_link: str
    schema_version: str = NOTIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "intent_id": self.intent_id,
                "alert_id": self.alert_id,
                "customer_id": self.customer_id,
                "title": self.title,
                "body": self.body,
                "deep_link": self.deep_link,
            }
        )
        if self.schema_version != NOTIFICATION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {NOTIFICATION_SCHEMA_VERSION}")
        expected_link = build_alert_customer_deep_link(
            alert_id=self.alert_id,
            customer_id=self.customer_id,
        )
        if self.deep_link != expected_link:
            raise ValueError("deep_link must use only the allowed alert/customer parameters")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "intent_id": self.intent_id,
            "alert_id": self.alert_id,
            "customer_id": self.customer_id,
            "title": self.title,
            "body": self.body,
            "deep_link": self.deep_link,
        }


@dataclass(frozen=True)
class NotificationRequest:
    """An explicit request passed to a provider-neutral notification service."""

    request_id: str
    intent: NotificationIntent
    requested_at: datetime
    schema_version: str = NOTIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty({"request_id": self.request_id})
        _validate_aware_datetime(self.requested_at, "requested_at")
        if self.schema_version != NOTIFICATION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {NOTIFICATION_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "requested_at": self.requested_at.isoformat(),
            "intent": self.intent.to_dict(),
        }


@dataclass(frozen=True)
class NotificationResult:
    """A result that keeps preview, non-delivery, and future sending distinct."""

    request_id: str
    intent_id: str
    service_id: str
    status: NotificationStatus
    external_delivery_attempted: bool
    captured_preview: str | None
    schema_version: str = NOTIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "request_id": self.request_id,
                "intent_id": self.intent_id,
                "service_id": self.service_id,
            }
        )
        if self.status not in NOTIFICATION_STATUSES:
            raise ValueError(f"status must be one of {NOTIFICATION_STATUSES}")
        if not isinstance(self.external_delivery_attempted, bool):
            raise ValueError("external_delivery_attempted must be a bool")
        if self.status == "PREVIEW":
            if self.external_delivery_attempted or not self.captured_preview:
                raise ValueError("PREVIEW must have captured_preview without external delivery")
        elif self.status == "NOT_SENT":
            if self.external_delivery_attempted or self.captured_preview is not None:
                raise ValueError("NOT_SENT must have no preview or external delivery")
        elif self.status == "SENT":
            if not self.external_delivery_attempted or self.captured_preview is not None:
                raise ValueError("SENT requires external delivery and no preview payload")
        if self.schema_version != NOTIFICATION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {NOTIFICATION_SCHEMA_VERSION}")

    @property
    def sent(self) -> bool:
        """Return true only for a future adapter that actually sent externally."""

        return self.status == "SENT"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "intent_id": self.intent_id,
            "service_id": self.service_id,
            "status": self.status,
            "sent": self.sent,
            "external_delivery_attempted": self.external_delivery_attempted,
            "captured_preview": self.captured_preview,
        }


class PreviewNotificationService:
    """Offline implementation that deterministically renders and retains requests."""

    service_id = "offline_preview"

    def __init__(self) -> None:
        self._captured_requests: list[NotificationRequest] = []

    @property
    def captured_requests(self) -> tuple[NotificationRequest, ...]:
        """Return requests in local invocation order for an offline preview UI."""

        return tuple(self._captured_requests)

    def notify(self, request: NotificationRequest) -> NotificationResult:
        preview = _render_preview(request)
        self._captured_requests.append(request)
        return NotificationResult(
            request_id=request.request_id,
            intent_id=request.intent.intent_id,
            service_id=self.service_id,
            status="PREVIEW",
            external_delivery_attempted=False,
            captured_preview=preview,
        )


class NullNotificationService:
    """Offline no-op implementation for contexts where even a preview is not wanted."""

    service_id = "offline_null"

    def notify(self, request: NotificationRequest) -> NotificationResult:
        return NotificationResult(
            request_id=request.request_id,
            intent_id=request.intent.intent_id,
            service_id=self.service_id,
            status="NOT_SENT",
            external_delivery_attempted=False,
            captured_preview=None,
        )


def build_alert_customer_deep_link(*, alert_id: str, customer_id: str) -> str:
    """Build the sole supported relative deep link using only identity references."""

    _validate_safe_identifier(alert_id, "alert_id")
    _validate_safe_identifier(customer_id, "customer_id")
    return "/rm/cases?" + urlencode(
        {"alert_id": alert_id, "customer_id": customer_id},
        safe="-_",
    )


def _render_preview(request: NotificationRequest) -> str:
    """Use canonical JSON so equivalent requests always render identically."""

    return json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_non_empty(values: dict[str, str]) -> None:
    missing = sorted(name for name, value in values.items() if not str(value).strip())
    if missing:
        raise ValueError(f"required fields must be non-empty: {', '.join(missing)}")


def _validate_safe_identifier(value: str, label: str) -> None:
    if not str(value).strip() or any(character not in _SAFE_IDENTIFIER_CHARACTERS for character in value):
        raise ValueError(f"{label} must contain only safe identifier characters")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
