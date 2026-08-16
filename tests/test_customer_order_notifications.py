from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config.settings import Settings
from commerce.models import (
    ChannelName,
    NotificationTemplate,
    NotificationType,
    OrderNotificationPayload,
)
from commerce.services import NotificationTemplateError, NotificationTemplateRegistry


def test_notification_delivery_is_explicitly_opt_in() -> None:
    assert Settings.model_fields["CUSTOMER_NOTIFICATIONS_ENABLED"].default is False


def payload(payment_method: str = "CASH_ON_DELIVERY") -> OrderNotificationPayload:
    return OrderNotificationPayload(
        order_reference="51fdca70-a64d-4494-8dcb-88d3ce397034",
        order_status="CONFIRMED",
        payment_method=payment_method,
        currency="INR",
        total_amount="1600.00",
        occurred_at=datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("locale", ["en-IN", "hi-IN", "hi-Latn-IN"])
@pytest.mark.parametrize(
    "notification_type",
    [
        NotificationType.ORDER_CONFIRMED,
        NotificationType.ORDER_PREPARING,
        NotificationType.ORDER_OUT_FOR_DELIVERY,
        NotificationType.ORDER_DELIVERED,
        NotificationType.ORDER_CANCELLED,
    ],
)
def test_reviewed_templates_preserve_order_reference(
    locale: str, notification_type: NotificationType
) -> None:
    registry = NotificationTemplateRegistry(
        version=1, default_locale="en-IN", content_sids={}
    )
    template, fell_back = registry.get(notification_type, locale)
    body, variables = registry.render(template, payload())

    assert not fell_back
    assert payload().order_reference in body
    assert payload().order_reference in variables.values()
    assert "paid" not in body.lower()


def test_unknown_locale_uses_configured_fallback() -> None:
    registry = NotificationTemplateRegistry(
        version=1, default_locale="en-IN", content_sids={}
    )
    template, fell_back = registry.get(NotificationType.ORDER_PREPARING, "mr-IN")

    assert fell_back
    assert template.locale == "en-IN"


def test_template_unknown_placeholder_fails_without_evaluation() -> None:
    template = NotificationTemplate(
        key="invalid",
        version=1,
        notification_type=NotificationType.ORDER_CONFIRMED,
        channel=ChannelName.TWILIO_WHATSAPP,
        locale="en-IN",
        body_template="{order_reference} {internal_reason}",
        provider_variables=("order_reference", "internal_reason"),
    )

    with pytest.raises(NotificationTemplateError):
        NotificationTemplateRegistry.render(template, payload())


def test_twilio_mapping_validation_requires_every_enabled_template() -> None:
    registry = NotificationTemplateRegistry(
        version=1,
        default_locale="en-IN",
        content_sids={"ORDER_CONFIRMED:en-IN": "not-a-content-sid"},
    )

    with pytest.raises(NotificationTemplateError):
        registry.validate_twilio_mappings()
