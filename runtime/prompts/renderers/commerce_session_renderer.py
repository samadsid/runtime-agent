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

        checkout = session.checkout
        lines.append("Checkout state:")
        lines.append(f"Stage: {checkout.stage.value}")
        lines.append(
            "Source cart: present"
            if checkout.source_cart_id is not None
            else "Source cart: missing"
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

        return "\n".join(lines)
