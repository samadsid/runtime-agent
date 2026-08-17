import type { OrderListItem } from "@/api/contracts";
import { AppText, Card, Inline, StatusBadge } from "@/design-system";
import { formatDateTime, formatMoney } from "@/features/orders/presentation";
import { presentOrderStatus } from "@/features/presentation/status";

export function OrderRow({ order, onPress }: { order: OrderListItem; onPress(): void }) {
  const status = presentOrderStatus(order.status);
  return <Card variant="interactive" onPress={onPress} accessibilityLabel={`Order ${order.order_reference}, ${status.label}`}>
    <Inline between style={{ alignItems: "flex-start" }}><AppText variant="titleSmall" weight="bold" style={{ flex: 1 }}>{order.order_reference}</AppText><StatusBadge {...status} /></Inline>
    <AppText variant="bodyLarge">{order.customer_name}</AppText>
    <Inline between wrap><AppText weight="bold">{formatMoney(order.total, order.currency)}</AppText><AppText color="secondary">Updated {formatDateTime(order.updated_at)}</AppText></Inline>
  </Card>;
}
