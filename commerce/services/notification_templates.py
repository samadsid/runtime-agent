from __future__ import annotations

from string import Formatter

from commerce.models import (
    ChannelName,
    NotificationTemplate,
    NotificationType,
    OrderNotificationPayload,
)

_BODIES: dict[str, dict[NotificationType, str]] = {
    "en-IN": {
        NotificationType.ORDER_CONFIRMED: (
            "Your order {order_reference} has been confirmed. "
            "Payment method: {payment_method}."
        ),
        NotificationType.ORDER_PREPARING: "Your order {order_reference} is now being prepared.",
        NotificationType.ORDER_OUT_FOR_DELIVERY: "Your order {order_reference} is out for delivery.",
        NotificationType.ORDER_DELIVERED: "Your order {order_reference} has been marked delivered.",
        NotificationType.ORDER_CANCELLED: "Your order {order_reference} has been cancelled.",
    },
    "hi-IN": {
        NotificationType.ORDER_CONFIRMED: (
            "आपका ऑर्डर {order_reference} कन्फ़र्म हो गया है। भुगतान का तरीका: {payment_method}।"
        ),
        NotificationType.ORDER_PREPARING: "आपका ऑर्डर {order_reference} तैयार किया जा रहा है।",
        NotificationType.ORDER_OUT_FOR_DELIVERY: "आपका ऑर्डर {order_reference} डिलीवरी के लिए निकल गया है।",
        NotificationType.ORDER_DELIVERED: "आपका ऑर्डर {order_reference} डिलीवर किया गया है।",
        NotificationType.ORDER_CANCELLED: "आपका ऑर्डर {order_reference} रद्द कर दिया गया है।",
    },
    "hi-Latn-IN": {
        NotificationType.ORDER_CONFIRMED: (
            "Aapka order {order_reference} confirm ho gaya hai. Payment method: {payment_method}."
        ),
        NotificationType.ORDER_PREPARING: "Aapka order {order_reference} taiyar kiya ja raha hai.",
        NotificationType.ORDER_OUT_FOR_DELIVERY: "Aapka order {order_reference} delivery ke liye nikal gaya hai.",
        NotificationType.ORDER_DELIVERED: "Aapka order {order_reference} deliver ho gaya hai.",
        NotificationType.ORDER_CANCELLED: "Aapka order {order_reference} cancel ho gaya hai.",
    },
}


class NotificationTemplateError(ValueError):
    pass


class NotificationTemplateRegistry:
    def __init__(
        self,
        *,
        version: int,
        default_locale: str,
        content_sids: dict[str, str],
    ) -> None:
        self.version = version
        self.default_locale = default_locale
        self._content_sids = content_sids
        if default_locale not in _BODIES:
            raise NotificationTemplateError("Unsupported notification default locale.")

    @property
    def locales(self) -> tuple[str, ...]:
        return tuple(_BODIES)

    def get(
        self, notification_type: NotificationType, locale: str | None
    ) -> tuple[NotificationTemplate, bool]:
        selected = locale if locale in _BODIES else self.default_locale
        body = _BODIES.get(selected, {}).get(notification_type)
        if body is None:
            raise NotificationTemplateError("Unsupported notification template.")
        sid = self._content_sids.get(f"{notification_type.value}:{selected}")
        fields = tuple(
            name for _, name, _, _ in Formatter().parse(body) if name is not None
        )
        return (
            NotificationTemplate(
                key=f"order.{notification_type.value.lower()}.{selected}",
                version=self.version,
                notification_type=notification_type,
                channel=ChannelName.TWILIO_WHATSAPP,
                locale=selected,
                body_template=body,
                provider_content_sid=sid,
                provider_variables=fields,
            ),
            selected != locale and locale is not None,
        )

    def validate_twilio_mappings(self) -> None:
        missing = [
            f"{event.value}:{locale}"
            for locale in _BODIES
            for event in _BODIES[locale]
            if not self._content_sids.get(f"{event.value}:{locale}", "").startswith(
                "HX"
            )
        ]
        if missing:
            raise NotificationTemplateError(
                "Missing or invalid Twilio notification Content SIDs: "
                + ", ".join(missing)
            )

    @staticmethod
    def render(
        template: NotificationTemplate, payload: OrderNotificationPayload
    ) -> tuple[str, dict[str, str]]:
        values = payload.model_dump(mode="json")
        allowed = set(type(payload).model_fields)
        referenced = set(template.provider_variables)
        if not referenced <= allowed:
            raise NotificationTemplateError("Template contains an unknown placeholder.")
        try:
            body = template.body_template.format_map(values)
        except (KeyError, ValueError) as error:
            raise NotificationTemplateError("Template rendering failed.") from error
        variables = {
            str(index): str(values[field])
            for index, field in enumerate(template.provider_variables, start=1)
        }
        return body, variables
