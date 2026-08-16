import type { OrderStatus } from "@/api/contracts";

export function formatMoney(amount: string, currency: string): string {
  const numeric = Number(amount);
  return Number.isFinite(numeric) ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(numeric) : `${amount} ${currency}`;
}
export function formatDateTime(value: string | null): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
export function statusActionLabel(status: OrderStatus): string {
  const labels: Partial<Record<OrderStatus, string>> = {
    PREPARING: "Mark as preparing", OUT_FOR_DELIVERY: "Mark as out for delivery",
    DELIVERED: "Mark as delivered", CANCELLED: "Cancel order",
  };
  return labels[status] ?? `Mark as ${status.toLowerCase().replaceAll("_", " ")}`;
}
