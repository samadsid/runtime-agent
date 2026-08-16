import type { OrderListItem, OrderPage } from "@/api/contracts";

export function mergeOrderPages(pages: OrderPage[] | undefined): OrderListItem[] {
  const unique = new Map<string, OrderListItem>();
  pages?.forEach((page) => page.items.forEach((item) => unique.set(item.order_id, item)));
  return [...unique.values()];
}
