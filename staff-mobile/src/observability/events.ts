type EventName =
  | "app_started" | "login_succeeded" | "login_failed_category"
  | "orders_loaded" | "orders_load_failed_category"
  | "order_transition_succeeded" | "order_transition_failed_category"
  | "stale_order_detected" | "session_expired";

export function recordEvent(name: EventName, fields: Record<string, string> = {}): void {
  if (__DEV__) console.info("mobile_event", name, fields);
}
