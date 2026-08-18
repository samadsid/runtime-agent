from __future__ import annotations

from commerce.models import NotificationTemplate, NotificationType

from .models import ApprovedTemplateMessage, WhatsAppProviderName


class WhatsAppTemplateError(ValueError):
    pass


class WhatsAppTemplateRegistry:
    """Maps reviewed channel templates to provider-owned identifiers."""

    def __init__(
        self,
        *,
        content_sids: dict[str, str],
        meta_templates: dict[str, dict[str, str]],
    ) -> None:
        self._content_sids = content_sids
        self._meta_templates = meta_templates

    def get(
        self, template: NotificationTemplate, provider: WhatsAppProviderName
    ) -> ApprovedTemplateMessage:
        key = f"{template.notification_type.value}:{template.locale}"
        if provider == WhatsAppProviderName.TWILIO:
            sid = self._content_sids.get(key, "")
            if not sid.startswith("HX"):
                raise WhatsAppTemplateError("Missing approved Twilio template.")
            return ApprovedTemplateMessage(key=template.key, name=sid, parameters={})
        mapping = self._meta_templates.get(key, {})
        name = mapping.get("name", "")
        language = mapping.get("language", "")
        if not name or not language:
            raise WhatsAppTemplateError("Missing approved Meta template.")
        return ApprovedTemplateMessage(
            key=template.key, name=name, language=language, parameters={}
        )

    def validate(
        self, provider: WhatsAppProviderName, locales: tuple[str, ...]
    ) -> None:
        events = (
            NotificationType.ORDER_CONFIRMED,
            NotificationType.ORDER_PREPARING,
            NotificationType.ORDER_OUT_FOR_DELIVERY,
            NotificationType.ORDER_DELIVERED,
            NotificationType.ORDER_CANCELLED,
        )
        for locale in locales:
            for event in events:
                key = f"{event.value}:{locale}"
                if provider == WhatsAppProviderName.TWILIO:
                    valid = self._content_sids.get(key, "").startswith("HX")
                else:
                    mapping = self._meta_templates.get(key, {})
                    valid = bool(mapping.get("name") and mapping.get("language"))
                if not valid:
                    raise WhatsAppTemplateError(
                        f"Missing approved {provider.value} notification template: {key}"
                    )
