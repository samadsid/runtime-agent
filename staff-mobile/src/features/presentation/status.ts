import type { OrderStatus } from "@/api/contracts";

export type PresentationTone = "brand" | "success" | "warning" | "info" | "danger" | "neutral";

const orderStatuses: Record<OrderStatus, { label: string; tone: PresentationTone; icon: "time-outline" | "alert-circle-outline" | "checkmark-circle-outline" | "cube-outline" | "car-outline" | "close-circle-outline" }> = {
  AWAITING_PAYMENT: { label: "Awaiting payment", tone: "warning", icon: "time-outline" },
  PAYMENT_FAILED: { label: "Payment failed", tone: "danger", icon: "alert-circle-outline" },
  PAYMENT_EXPIRED: { label: "Payment expired", tone: "neutral", icon: "time-outline" },
  CONFIRMED: { label: "Confirmed", tone: "brand", icon: "checkmark-circle-outline" },
  PREPARING: { label: "Preparing", tone: "info", icon: "cube-outline" },
  OUT_FOR_DELIVERY: { label: "Out for delivery", tone: "info", icon: "car-outline" },
  DELIVERED: { label: "Delivered", tone: "success", icon: "checkmark-circle-outline" },
  CANCELLED: { label: "Cancelled", tone: "danger", icon: "close-circle-outline" },
};

export function presentOrderStatus(status: OrderStatus) { return orderStatuses[status]; }

export function presentProductStatus(status: "ACTIVE" | "INACTIVE") {
  return status === "ACTIVE" ? { label: "Active", tone: "success" as const, icon: "checkmark-circle-outline" as const }
    : { label: "Inactive", tone: "neutral" as const, icon: "pause-circle-outline" as const };
}

export function presentStockState(state: "LOW" | "OUT" | "AVAILABLE") {
  if (state === "LOW") return { label: "Low stock", tone: "warning" as const, icon: "warning-outline" as const };
  if (state === "OUT") return { label: "Out of stock", tone: "danger" as const, icon: "alert-circle-outline" as const };
  return { label: "Available", tone: "success" as const, icon: "checkmark-circle-outline" as const };
}
