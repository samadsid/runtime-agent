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

        return "\n".join(lines)
