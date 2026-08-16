import { formatMoney, statusActionLabel } from "./presentation";

test("formats authoritative currency and action labels", () => {
  expect(formatMoney("125.50", "INR")).toContain("125.50");
  expect(statusActionLabel("OUT_FOR_DELIVERY")).toBe("Mark as out for delivery");
});
