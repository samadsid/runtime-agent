import { z } from "zod";

import {
  dashboardSummarySchema, loginResponseSchema, orderDetailsSchema, orderPageSchema,
  staffIdentitySchema, transitionResponseSchema, type OrderStatus,
} from "./contracts";
import type { StaffApiClient } from "./client";

export type OrderFilters = {
  status?: OrderStatus;
  orderReference?: string;
  createdFrom?: string;
  createdTo?: string;
};

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
  };
}

export type StaffApi = ReturnType<typeof createStaffApi>;
