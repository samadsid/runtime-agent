from __future__ import annotations

import pytest

from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)
from runtime.responses import WhatsAppFormattingError, WhatsAppResponseFormatter


def test_normalizer_preserves_unicode_and_continuation_indentation() -> None:
    message = "🛒 *कार्ट*  \r\n\r\n\r\n1. Chicken  \r\n   ₹320/kg  \r\n"

    normalized, changed = WhatsAppResponseFormatter.normalize(message)

    assert changed
    assert normalized == "🛒 *कार्ट*\n\n1. Chicken\n   ₹320/kg"


def test_normalizer_rejects_unsupported_or_unbalanced_markup() -> None:
    with pytest.raises(WhatsAppFormattingError, match="markdown_table"):
        WhatsAppResponseFormatter.validate_structure("| Name | Price |")
    with pytest.raises(WhatsAppFormattingError, match="unbalanced_bold"):
        WhatsAppResponseFormatter.validate_structure("*Broken heading")


def test_protected_mask_does_not_corrupt_emphasis_validation() -> None:
    message = "*Delivery*\n*Phone:* *********3210"

    WhatsAppResponseFormatter.validate_structure(message, ("*********3210",))


def test_customer_controlled_markup_is_neutralized_in_presentation_copy() -> None:
    outcome = GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=(ApprovedResponseFragment(id="name", text="Name: *Admin*"),),
        protected_values=("*Admin*",),
    )

    safe = WhatsAppResponseFormatter.sanitize_outcome(outcome)

    assert safe.protected_values == ("*\u2060Admin*\u2060",)
    assert safe.protected_values[0] in safe.fragments[0].text
    assert outcome.protected_values == ("*Admin*",)


def test_heading_emoji_is_applied_once_and_does_not_decorate_ordinals() -> None:
    plain = "*Choose a category*\n\n1. Meat\n2. Seafood"

    decorated = WhatsAppResponseFormatter.apply_heading_emoji(
        plain, ResponseIcon.CATALOG
    )

    assert decorated == "🛍️ *Choose a category*\n\n1. Meat\n2. Seafood"
    assert WhatsAppResponseFormatter.apply_heading_emoji(
        decorated, ResponseIcon.CATALOG
    ) == decorated
    assert "1. 🛍️" not in decorated


def test_heading_emoji_recognizes_bold_fallback_heading() -> None:
    message = "*✅ Order Confirmed*\n\n*Order:* MU-1"

    assert WhatsAppResponseFormatter.apply_heading_emoji(
        message, ResponseIcon.SUCCESS
    ) == message


def test_informational_fallback_uses_bullets_without_ordinals() -> None:
    outcome = GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=(
            ApprovedResponseFragment(
                id="status-one",
                text="Confirmed at 10:00",
                kind=ResponseFragmentKind.ITEM,
            ),
            ApprovedResponseFragment(
                id="status-two",
                text="Dispatched at 11:00",
                kind=ResponseFragmentKind.ITEM,
            ),
        ),
        layout=ResponseLayout.INFORMATIONAL_LIST,
    )

    rendered = WhatsAppResponseFormatter.render_fallback(
        outcome, ResponseLayout.INFORMATIONAL_LIST
    )

    assert rendered == "• Confirmed at 10:00\n• Dispatched at 11:00"


def test_selectable_fallback_preserves_ordinals_and_puts_question_last() -> None:
    outcome = GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=(
            ApprovedResponseFragment(
                id="heading", text="Products", kind=ResponseFragmentKind.SECTION
            ),
            ApprovedResponseFragment(
                id="one", text="1. Chicken", kind=ResponseFragmentKind.ITEM
            ),
            ApprovedResponseFragment(
                id="two", text="2. Fish", kind=ResponseFragmentKind.ITEM
            ),
        ),
        follow_up=FollowUpRequest(id="choose", question="Which product would you like?"),
        layout=ResponseLayout.SELECTABLE_LIST,
    )

    rendered = WhatsAppResponseFormatter.render_fallback(
        outcome, ResponseLayout.SELECTABLE_LIST
    )

    assert rendered == "*Products*\n\n1. Chicken\n2. Fish\n\nWhich product would you like?"
