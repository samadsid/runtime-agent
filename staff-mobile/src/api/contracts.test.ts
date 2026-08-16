import { dashboardSummarySchema, orderDetailsSchema, orderPageSchema, staffIdentitySchema } from "./contracts";

const order = {
  order_id: "00000000-0000-4000-8000-000000000001",
  order_reference: "00000000-0000-4000-8000-000000000001",
  status: "CONFIRMED", payment_method: "CASH_ON_DELIVERY", total: "120.00", currency: "INR",
  customer_name: "Customer", masked_phone_number: "********3210",
  created_at: "2026-08-16T10:00:00+00:00", updated_at: "2026-08-16T10:00:00+00:00", version: 1,
};

test("parses staff order pages and decimal values", () => {
  const parsed = orderPageSchema.parse({ items: [order], next_cursor: null });
  expect(parsed.items[0]?.total).toBe("120.00");
});

test("parses identity with the configured non-versioned tenant UUID", () => {
  const tenantId = "00000000-0000-0000-0000-000000000001";
  const parsed = staffIdentitySchema.parse({
    staff_id: "00000000-0000-4000-8000-000000000001",
    display_name: "Local Admin",
    active_membership: { tenant_id: tenantId, role: "ADMIN" },
    memberships: [{ tenant_id: tenantId, role: "ADMIN" }],
  });

  expect(parsed.active_membership.tenant_id).toBe(tenantId);
});

test("rejects unknown critical order statuses", () => {
  expect(() => orderPageSchema.parse({ items: [{ ...order, status: "NEW_SERVER_STATUS" }], next_cursor: null })).toThrow();
});

test("parses bounded dashboard summary", () => {
  expect(dashboardSummarySchema.parse({ counts: { confirmed: 1, preparing: 2, out_for_delivery: 3 }, oldest_confirmed_orders: [order] }).counts.preparing).toBe(2);
});

test("parses details without requiring backend-internal identifiers", () => {
  const details = orderDetailsSchema.parse({
    order_id: order.order_id, order_reference: order.order_reference, status: order.status,
    payment_method: order.payment_method, customer_name: "Customer", phone_number: "+919999999999",
    delivery_address: "Address", created_at: order.created_at, confirmed_at: order.created_at,
    updated_at: order.updated_at, version: 1, total: "120", currency: "INR", payment_status: null,
    items: [], timeline: [], permitted_actions: [{ target_status: "PREPARING", requires_reason: false }],
  });
  expect(details.permitted_actions).toEqual([{ target_status: "PREPARING", requires_reason: false }]);
});
