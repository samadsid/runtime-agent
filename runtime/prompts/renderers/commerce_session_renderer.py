from __future__ import annotations

from commerce.models import CommerceSession


class CommerceSessionRenderer:
    def render(self, session: CommerceSession) -> str:
        lines: list[str] = ["Recent product results:"]

        if session.recent_product_results:
            for ordinal, product in enumerate(
                session.recent_product_results,
                start=1,
            ):
                lines.append(f"{ordinal}. {product.name}")
        else:
            lines.append("None.")

        lines.append("Current catalog browse (separate ordinal namespace):")
        browse = session.catalog_browse
        if browse is None:
            lines.append("None.")
        else:
            lines.append(f"Kind: {browse.kind.value}")
            lines.append(f"Page: {browse.page}")
            lines.append(f"Has previous: {browse.has_previous}")
            lines.append(f"Has next: {browse.has_next}")
            lines.append(f"Created at: {browse.created_at.isoformat()}")
            if browse.category_id is not None:
                lines.append(f"Category context ID: {browse.category_id}")
            for ordinal, category in enumerate(browse.categories, 1):
                lines.append(f"{ordinal}. Category: {category.name}")
            for ordinal, browse_product in enumerate(browse.products, 1):
                lines.append(f"{ordinal}. Product: {browse_product.name}")

        lines.append("Selected product:")
        lines.append(
            session.selected_product.name
            if session.selected_product is not None
            else "None."
        )

        lines.append("Cart items:")
        if session.cart_items:
            for ordinal, item in enumerate(session.cart_items, start=1):
                lines.append(
                    f"{ordinal}. {item.product.name} — "
                    f"{format(item.quantity, 'f')} {item.product.unit}"
                )
        else:
            lines.append("None.")

        lines.append("Pending cart clear:")
        if session.pending_cart_clear is None:
            lines.append("None.")
        else:
            lines.append("Present.")
            lines.append(f"Reviewed cart ID: {session.pending_cart_clear.cart_id}")
            lines.append(
                f"Reviewed cart version: {session.pending_cart_clear.cart_version}"
            )

        lines.append("Pending direct cart addition (separate ordinal namespace):")
        pending_addition = session.pending_cart_addition
        if pending_addition is None:
            lines.append("None.")
        else:
            lines.append(f"Quantity: {format(pending_addition.quantity, 'f')}")
            lines.append(
                f"Stated unit: {pending_addition.stated_unit or 'not provided'}"
            )
            for ordinal, option in enumerate(pending_addition.options, 1):
                lines.append(
                    f"{ordinal}. {option.display_name} — {option.canonical_unit}"
                )

        checkout = session.checkout
        lines.append("Checkout state:")
        lines.append(f"Stage: {checkout.stage.value}")
        lines.append(
            "Source cart: present"
            if checkout.source_cart_id is not None
            else "Source cart: missing"
        )
        lines.append(
            f"Reviewed checkout cart version: {checkout.source_cart_version}"
            if checkout.source_cart_version is not None
            else "Reviewed checkout cart version: missing"
        )
        lines.append(
            "Customer name: provided"
            if checkout.customer_name is not None
            else "Customer name: missing"
        )
        lines.append(
            "Phone number: provided"
            if checkout.phone_number is not None
            else "Phone number: missing"
        )
        lines.append(
            "Delivery address: provided"
            if checkout.delivery_address is not None
            else "Delivery address: missing"
        )
        lines.append("Pending delivery correction:")
        lines.append(
            checkout.pending_delivery_correction.value
            if checkout.pending_delivery_correction is not None
            else "None."
        )
        if checkout.stage.value != "NONE":
            lines.append(
                f"Payment method: {checkout.payment_method.value}"
                if checkout.payment_method is not None
                else "Payment method: not selected"
            )
        lines.append("Stock recovery:")
        recovery = checkout.stock_recovery
        if recovery is None:
            lines.append("None.")
        else:
            lines.append(f"Recovery cart version: {recovery.cart_version}")
            lines.append("Shortages (separate ordinal namespace):")
            for ordinal, shortage in enumerate(recovery.shortages, start=1):
                lines.append(
                    f"{ordinal}. {shortage.product_name} — requested "
                    f"{format(shortage.requested_quantity, 'f')} {shortage.unit}; "
                    f"available {format(shortage.available_quantity, 'f')} "
                    f"{shortage.unit}"
                )
            lines.append("Recovery choices (separate ordinal namespace):")
            for recovery_option in recovery.options:
                target = ""
                if recovery_option.shortage_ordinal is not None:
                    target += f"; shortage ordinal {recovery_option.shortage_ordinal}"
                if recovery_option.cart_ordinal is not None:
                    target += f"; cart ordinal {recovery_option.cart_ordinal}"
                lines.append(
                    f"{recovery_option.ordinal}. {recovery_option.action.value}{target}"
                )

        lines.append("Recent order results:")
        if session.recent_order_results:
            for ordinal, order in enumerate(session.recent_order_results, start=1):
                lines.append(
                    f"{ordinal}. Order {order.order_id} — {order.status.value}"
                )
        else:
            lines.append("None.")

        lines.append("Pending order cancellation:")
        lines.append(
            "Present." if session.pending_order_cancellation is not None else "None."
        )

        lines.append("Recent saved addresses (separate ordinal namespace):")
        if session.recent_saved_addresses:
            for ordinal, address in enumerate(session.recent_saved_addresses, start=1):
                default = " — default" if address.is_default else ""
                lines.append(f"{ordinal}. {address.label}{default}")
        else:
            lines.append("None.")
        lines.append("Pending saved profile use:")
        if session.pending_saved_profile_use is None:
            lines.append("None.")
        else:
            lines.append("Present.")
            lines.append(
                "Saved name offered."
                if session.pending_saved_profile_use.customer_name is not None
                else "Saved name not offered."
            )
            lines.append(
                "Saved phone offered."
                if session.pending_saved_profile_use.phone_number is not None
                else "Saved phone not offered."
            )
        lines.append("Pending saved details confirmation:")
        lines.append(
            session.pending_saved_details_save.reason.value
            if session.pending_saved_details_save is not None
            else "None."
        )

        onboarding = session.customer_onboarding
        if onboarding != type(onboarding)():
            lines.append("Customer onboarding:")
            lines.append(f"Stage: {onboarding.stage.value}")
            lines.append(
                "Name: provided"
                if onboarding.pending_customer_name is not None
                else "Name: missing"
            )
            lines.append(
                "Phone: provided"
                if onboarding.pending_phone_number is not None
                else "Phone: missing"
            )
            lines.append(
                "Address: provided"
                if onboarding.pending_delivery_address is not None
                else "Address: missing"
            )

        return "\n".join(lines)
