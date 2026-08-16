import type { OrderFilters } from "@/api/staff-api";

export const queryKeys = {
  dashboard: ["staff", "dashboard"] as const,
  orders: (filters: OrderFilters) => ["staff", "orders", filters] as const,
  order: (orderId: string) => ["staff", "order", orderId] as const,
};
