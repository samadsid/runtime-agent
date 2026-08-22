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
            "✅ *Order confirmed*\n\n"
            "*Order:* {order_reference}\n*Payment:* {payment_method}"
        ),
        NotificationType.ORDER_PREPARING: "📦 *Order update*\n\nOrder {order_reference} is now being prepared.",
        NotificationType.ORDER_OUT_FOR_DELIVERY: "🚚 *Order update*\n\nOrder {order_reference} is out for delivery.",
        NotificationType.ORDER_DELIVERED: "✅ *Order delivered*\n\nOrder {order_reference} has been delivered.",
        NotificationType.ORDER_CANCELLED: "*Order cancelled*\n\nOrder {order_reference} has been cancelled.",
    },
    "hi-IN": {
        NotificationType.ORDER_CONFIRMED: (
            "✅ *ऑर्डर कन्फ़र्म हो गया*\n\n"
            "*ऑर्डर:* {order_reference}\n*भुगतान:* {payment_method}"
        ),
        NotificationType.ORDER_PREPARING: "📦 *ऑर्डर अपडेट*\n\nऑर्डर {order_reference} तैयार किया जा रहा है।",
        NotificationType.ORDER_OUT_FOR_DELIVERY: "🚚 *ऑर्डर अपडेट*\n\nऑर्डर {order_reference} डिलीवरी के लिए निकल गया है।",
        NotificationType.ORDER_DELIVERED: "✅ *ऑर्डर डिलीवर हो गया*\n\nऑर्डर {order_reference} डिलीवर हो गया है।",
        NotificationType.ORDER_CANCELLED: "*ऑर्डर रद्द हो गया*\n\nऑर्डर {order_reference} रद्द कर दिया गया है।",
    },
    "hi-Latn-IN": {
        NotificationType.ORDER_CONFIRMED: (
            "✅ *Order confirm ho gaya*\n\n"
            "*Order:* {order_reference}\n*Payment:* {payment_method}"
        ),
        NotificationType.ORDER_PREPARING: "📦 *Order update*\n\nOrder {order_reference} taiyar ho raha hai.",
        NotificationType.ORDER_OUT_FOR_DELIVERY: "🚚 *Order update*\n\nOrder {order_reference} delivery ke liye nikal gaya hai.",
        NotificationType.ORDER_DELIVERED: "✅ *Order deliver ho gaya*\n\nOrder {order_reference} deliver ho gaya hai.",
        NotificationType.ORDER_CANCELLED: "*Order cancel ho gaya*\n\nOrder {order_reference} cancel ho gaya hai.",
    },
}

_PAYMENT_LABELS = {
    "en-IN": {"CASH_ON_DELIVERY": "Cash on Delivery", "ONLINE": "Online Payment"},
    "hi-IN": {"CASH_ON_DELIVERY": "कैश ऑन डिलीवरी", "ONLINE": "ऑनलाइन भुगतान"},
    "hi-Latn-IN": {"CASH_ON_DELIVERY": "Cash on Delivery", "ONLINE": "Online Payment"},
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
                channel=ChannelName.WHATSAPP,
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
        values["payment_method"] = _PAYMENT_LABELS.get(template.locale, {}).get(
            payload.payment_method, payload.payment_method
        )
        allowed = set(type(payload).model_fields)
        referenced = set(template.provider_variables)
        if not referenced <= allowed:
            raise NotificationTemplateError("Template contains an unknown placeholder.")
        for field in template.provider_variables:
            value = str(values[field])
            if (
                "\n" in value
                or "\r" in value
                or "*" in value
                or "```" in value
                or value.lstrip()[:1].isdigit() and ". " in value[:4]
            ):
                raise NotificationTemplateError(
                    "Template value contains unsafe presentation markup."
                )
        try:
            body = template.body_template.format_map(values)
        except (KeyError, ValueError) as error:
            raise NotificationTemplateError("Template rendering failed.") from error
        variables = {
            str(index): str(values[field])
            for index, field in enumerate(template.provider_variables, start=1)
        }
        return body, variables
