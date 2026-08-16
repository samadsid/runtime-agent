import { z } from "zod";

export const staffRoleSchema = z.enum(["ADMIN", "FULFILMENT_STAFF"]);
export type StaffRole = z.infer<typeof staffRoleSchema>;

export const orderStatusSchema = z.enum([
  "AWAITING_PAYMENT",
  "PAYMENT_FAILED",
  "PAYMENT_EXPIRED",
  "CONFIRMED",
  "PREPARING",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "CANCELLED",
]);
export type OrderStatus = z.infer<typeof orderStatusSchema>;

// PostgreSQL's UUID type permits UUID-shaped values without RFC version/variant
// bits (including the configured default tenant ID). Zod 4's uuid() validator
// intentionally rejects those values, so mirror the API/database contract here.
const uuidSchema = z.string().regex(
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  "Invalid UUID",
);
const dateSchema = z.string().datetime({ offset: true });
const decimalSchema = z.union([z.string(), z.number()]).transform(String);

export const loginResponseSchema = z.object({
  access_token: z.string().min(1), token_type: z.literal("Bearer"), expires_in: z.number().int().positive(),
});

export const membershipSchema = z.object({ tenant_id: uuidSchema, role: staffRoleSchema });
export const staffIdentitySchema = z.object({
  staff_id: uuidSchema,
  display_name: z.string().min(1),
  active_membership: membershipSchema,
  memberships: z.array(membershipSchema),
});
export type StaffIdentity = z.infer<typeof staffIdentitySchema>;

export const orderListItemSchema = z.object({
  order_id: uuidSchema,
  order_reference: z.string().min(1),
  status: orderStatusSchema,
  payment_method: z.string().min(1),
  total: decimalSchema,
  currency: z.string().min(3).max(3),
  customer_name: z.string(),
  masked_phone_number: z.string(),
  created_at: dateSchema,
  updated_at: dateSchema,
  version: z.number().int().positive(),
});
export type OrderListItem = z.infer<typeof orderListItemSchema>;

export const orderPageSchema = z.object({
  items: z.array(orderListItemSchema), next_cursor: z.string().nullable(),
});
export type OrderPage = z.infer<typeof orderPageSchema>;

export const permittedActionSchema = z.object({
  target_status: orderStatusSchema, requires_reason: z.boolean(),
});
export type PermittedOrderAction = z.infer<typeof permittedActionSchema>;

export const orderDetailsSchema = z.object({
  order_id: uuidSchema,
  order_reference: z.string().min(1),
  status: orderStatusSchema,
  payment_method: z.string(),
  customer_name: z.string(),
  phone_number: z.string(),
  delivery_address: z.string(),
  created_at: dateSchema,
  confirmed_at: dateSchema.nullable(),
  updated_at: dateSchema.nullable(),
  version: z.number().int().positive(),
  items: z.array(z.object({
    product_name: z.string(), unit: z.string(), unit_price: decimalSchema,
    currency: z.string(), quantity: decimalSchema, line_total: decimalSchema,
  })),
  timeline: z.array(z.object({
    from_status: orderStatusSchema.nullable(), to_status: orderStatusSchema,
    actor_type: z.enum(["CUSTOMER", "STAFF", "SYSTEM"]), reason: z.string().nullable(),
    created_at: dateSchema,
  })),
  total: decimalSchema,
  currency: z.string(),
  payment_status: z.string().nullable(),
  permitted_actions: z.array(permittedActionSchema),
});
export type OrderDetails = z.infer<typeof orderDetailsSchema>;

export const transitionResponseSchema = z.object({
  order_id: uuidSchema, status: orderStatusSchema, version: z.number().int().positive(),
  transitioned_at: dateSchema,
});

export const dashboardSummarySchema = z.object({
  counts: z.object({
    confirmed: z.number().int().nonnegative(), preparing: z.number().int().nonnegative(),
    out_for_delivery: z.number().int().nonnegative(),
  }),
  oldest_confirmed_orders: z.array(orderListItemSchema).max(5),
});
export type DashboardSummary = z.infer<typeof dashboardSummarySchema>;

export const apiErrorSchema = z.object({
  error: z.object({ code: z.string(), message: z.string(), request_id: z.string() }),
});
