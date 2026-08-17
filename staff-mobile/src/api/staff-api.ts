import { z } from "zod";

import {
  adjustmentResultSchema, adminProductPageSchema, catalogOptionsSchema,
  dashboardSummarySchema, loginResponseSchema, orderDetailsSchema, orderPageSchema,
  inventorySummarySchema, movementPageSchema, productWithInventorySchema,
  staffIdentitySchema, transitionResponseSchema, type OrderStatus,
} from "./contracts";
import type { StaffApiClient } from "./client";

export type OrderFilters = {
  status?: OrderStatus;
  orderReference?: string;
  createdFrom?: string;
  createdTo?: string;
};
export type CatalogFilters = { status?: "ACTIVE" | "INACTIVE"; categoryId?: string; query?: string; stockState?: "LOW" | "OUT" | "AVAILABLE" };
export type ProductInput = { sku: string; name: string; category_id: string | null; price: string; currency: string; unit: string; status?: "ACTIVE" | "INACTIVE"; low_stock_threshold: string | null; display_order: number };

function queryString(values: Record<string, string | undefined>): string {
  const params = Object.entries(values).filter((entry): entry is [string, string] => Boolean(entry[1]));
  return params.length ? `?${new URLSearchParams(params).toString()}` : "";
}

export function createStaffApi(client: StaffApiClient) {
  return {
    login: (email: string, password: string) => client.request("/api/staff/v1/auth/login", {
      method: "POST", body: { email, password }, schema: loginResponseSchema,
    }),
    me: () => client.request("/api/staff/v1/me", { authenticated: true, schema: staffIdentitySchema }),
    dashboard: (signal?: AbortSignal) => client.request("/api/staff/v1/dashboard/summary", {
      authenticated: true, schema: dashboardSummarySchema, signal,
    }),
    orders: (filters: OrderFilters, cursor?: string, signal?: AbortSignal) => client.request(
      `/api/staff/v1/orders${queryString({
        status: filters.status, order_reference: filters.orderReference,
        created_from: filters.createdFrom, created_to: filters.createdTo,
        limit: "30", cursor,
      })}`,
      { authenticated: true, schema: orderPageSchema, signal },
    ),
    order: (orderId: string, signal?: AbortSignal) => client.request(
      `/api/staff/v1/orders/${encodeURIComponent(orderId)}`,
      { authenticated: true, schema: orderDetailsSchema, signal },
    ),
    transition: (input: {
      orderId: string; targetStatus: OrderStatus; reason: string | null;
      version: number; idempotencyKey: string;
    }) => client.request(`/api/staff/v1/orders/${encodeURIComponent(input.orderId)}/status`, {
      method: "PATCH", authenticated: true, mutation: true,
      headers: { "Idempotency-Key": input.idempotencyKey, "If-Match": `"${input.version}"` },
      body: { target_status: input.targetStatus, reason: input.reason },
      schema: transitionResponseSchema,
    }),
    catalogOptions: (signal?: AbortSignal) => client.request("/api/staff/v1/catalog/options", { authenticated: true, schema: catalogOptionsSchema, signal }),
    products: (filters: CatalogFilters, cursor?: string, signal?: AbortSignal) => client.request(
      `/api/staff/v1/catalog/products${queryString({ status: filters.status, category_id: filters.categoryId, query: filters.query, stock_state: filters.stockState, limit: "30", cursor })}`,
      { authenticated: true, schema: adminProductPageSchema, signal },
    ),
    product: (id: string, signal?: AbortSignal) => client.request(`/api/staff/v1/catalog/products/${encodeURIComponent(id)}`, { authenticated: true, schema: productWithInventorySchema, signal }),
    createProduct: (body: ProductInput, idempotencyKey: string) => client.request("/api/staff/v1/catalog/products", { method: "POST", authenticated: true, mutation: true, headers: { "Idempotency-Key": idempotencyKey }, body, schema: productWithInventorySchema }),
    updateProduct: (id: string, body: Partial<Omit<ProductInput, "status">>, version: number, idempotencyKey: string) => client.request(`/api/staff/v1/catalog/products/${encodeURIComponent(id)}`, { method: "PATCH", authenticated: true, mutation: true, headers: { "Idempotency-Key": idempotencyKey, "If-Match": `"${version}"` }, body, schema: productWithInventorySchema }),
    changeProductStatus: (id: string, status: "ACTIVE" | "INACTIVE", reason: string, version: number, idempotencyKey: string) => client.request(`/api/staff/v1/catalog/products/${encodeURIComponent(id)}/status`, { method: "PATCH", authenticated: true, mutation: true, headers: { "Idempotency-Key": idempotencyKey, "If-Match": `"${version}"` }, body: { status, reason }, schema: productWithInventorySchema }),
    inventorySummary: (signal?: AbortSignal) => client.request("/api/staff/v1/inventory/summary", { authenticated: true, schema: inventorySummarySchema, signal }),
    movements: (id: string, cursor?: string, signal?: AbortSignal) => client.request(`/api/staff/v1/inventory/products/${encodeURIComponent(id)}/movements${queryString({ limit: "30", cursor })}`, { authenticated: true, schema: movementPageSchema, signal }),
    adjustInventory: (id: string, movementType: string, quantity: string, reason: string, version: number, idempotencyKey: string) => client.request(`/api/staff/v1/inventory/products/${encodeURIComponent(id)}/adjustments`, { method: "POST", authenticated: true, mutation: true, headers: { "Idempotency-Key": idempotencyKey, "If-Match": `"${version}"` }, body: { movement_type: movementType, quantity, reason }, schema: adjustmentResultSchema }),
  };
}

export type StaffApi = ReturnType<typeof createStaffApi>;
