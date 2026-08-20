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

export const productStatusSchema = z.enum(["ACTIVE", "INACTIVE"]);
export const stockStateSchema = z.enum(["LOW", "OUT", "AVAILABLE"]);
export const movementTypeSchema = z.enum([
  "OPENING_BALANCE", "RECEIPT", "POSITIVE_CORRECTION", "NEGATIVE_CORRECTION",
  "DAMAGE", "WASTAGE", "RESERVATION", "RELEASE", "CONSUMPTION",
]);
export const manualMovementTypeSchema = z.enum([
  "RECEIPT", "POSITIVE_CORRECTION", "NEGATIVE_CORRECTION", "DAMAGE", "WASTAGE",
]);

export const adminProductSchema = z.object({
  id: uuidSchema, tenant_id: uuidSchema, sku: z.string(), name: z.string(),
  category_id: uuidSchema.nullable(), category_name: z.string().nullable(),
  price: decimalSchema, currency: z.string(), unit: z.string(), status: productStatusSchema,
  low_stock_threshold: decimalSchema.nullable(), display_order: z.number().int().nonnegative(),
  version: z.number().int().positive(), created_at: dateSchema, updated_at: dateSchema,
});
export const productWithInventorySchema = z.object({
  product: adminProductSchema, on_hand_quantity: decimalSchema,
  reserved_quantity: decimalSchema, sellable_quantity: decimalSchema,
  inventory_version: z.number().int().positive(), inventory_updated_at: dateSchema,
  stock_states: z.array(stockStateSchema), permitted_actions: z.array(z.string()),
});
export type ProductWithInventory = z.infer<typeof productWithInventorySchema>;
export const adminProductPageSchema = z.object({
  items: z.array(productWithInventorySchema), next_cursor: z.string().nullable(),
});
export const catalogOptionsSchema = z.object({
  categories: z.array(z.object({ id: uuidSchema, name: z.string() })),
  currencies: z.array(z.string()), units: z.array(z.string()),
});
export type CatalogOptions = z.infer<typeof catalogOptionsSchema>;
export const movementSchema = z.object({
  id: uuidSchema, tenant_id: uuidSchema, product_id: uuidSchema,
  movement_type: movementTypeSchema, quantity: decimalSchema,
  on_hand_delta: decimalSchema, reserved_delta: decimalSchema,
  on_hand_before: decimalSchema, on_hand_after: decimalSchema,
  reserved_before: decimalSchema, reserved_after: decimalSchema,
  reference_type: z.string().nullable(), reference_id: uuidSchema.nullable(),
  reason: z.string(), actor_type: z.string(), actor_id: uuidSchema.nullable(), created_at: dateSchema,
});
export const movementPageSchema = z.object({ items: z.array(movementSchema), next_cursor: z.string().nullable() });
export const adjustmentResultSchema = z.object({ balance: productWithInventorySchema, movement: movementSchema, idempotent: z.boolean() });
export const inventorySummarySchema = z.object({
  active_products: z.number().int().nonnegative(), low_stock_products: z.number().int().nonnegative(),
  out_of_stock_products: z.number().int().nonnegative(), inactive_products: z.number().int().nonnegative(),
  oldest_low_stock_products: z.array(productWithInventorySchema),
});
export type InventorySummary = z.infer<typeof inventorySummarySchema>;

export const deliveryZoneStatusSchema = z.enum(["DRAFT", "ACTIVE", "INACTIVE"]);
export const geoJsonBoundarySchema = z.object({
  type: z.enum(["Polygon", "MultiPolygon"]), coordinates: z.array(z.unknown()),
});
export const deliveryZoneSchema = z.object({
  id: uuidSchema, tenant_id: uuidSchema, name: z.string().min(1),
  status: deliveryZoneStatusSchema, priority: z.number().int().nonnegative(),
  version: z.number().int().positive(), created_at: dateSchema, updated_at: dateSchema,
  boundary: geoJsonBoundarySchema.nullable(),
});
export type DeliveryZone = z.infer<typeof deliveryZoneSchema>;
export const deliveryZonePageSchema = z.object({ items: z.array(deliveryZoneSchema), next_cursor: z.string().nullable() });
export const deliveryZonePointResponseSchema = z.object({ serviceable: z.boolean(), zone_name: z.string().nullable(), zone_version: z.number().int().positive().nullable() });
