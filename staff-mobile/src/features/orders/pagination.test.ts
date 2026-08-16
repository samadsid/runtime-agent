import type { OrderPage } from "@/api/contracts";
import { mergeOrderPages } from "./pagination";

const item = (id: string) => ({
  order_id: id, order_reference: id, status: "CONFIRMED" as const,
  payment_method: "CASH_ON_DELIVERY", total: "10", currency: "INR", customer_name: "Customer",
  masked_phone_number: "***1", created_at: "2026-08-16T00:00:00Z", updated_at: "2026-08-16T00:00:00Z", version: 1,
});

test("merges cursor pages without duplicate orders", () => {
  const pages: OrderPage[] = [{ items: [item("a"), item("b")], next_cursor: "next" }, { items: [item("b"), item("c")], next_cursor: null }];
  expect(mergeOrderPages(pages).map(({ order_id }) => order_id)).toEqual(["a", "b", "c"]);
});
