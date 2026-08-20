import type { OrderFilters } from "@/api/staff-api";
import type { CatalogFilters } from "@/api/staff-api";

export const queryKeys = {
  dashboard: ["staff", "dashboard"] as const,
  orders: (filters: OrderFilters) => ["staff", "orders", filters] as const,
  order: (orderId: string) => ["staff", "order", orderId] as const,
  inventorySummary: ["staff", "inventory-summary"] as const,
  catalogOptions: ["staff", "catalog-options"] as const,
  products: (filters: CatalogFilters) => ["staff", "products", filters] as const,
  product: (id: string) => ["staff", "product", id] as const,
  movements: (id: string) => ["staff", "movements", id] as const,
  deliveryZones: (status?: string) => ["staff", "delivery-zones", status] as const,
  deliveryZone: (id: string) => ["staff", "delivery-zone", id] as const,
};
