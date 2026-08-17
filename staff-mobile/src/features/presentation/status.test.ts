import { orderStatusSchema } from "@/api/contracts";
import { presentOrderStatus, presentProductStatus, presentStockState } from "./status";

test("every order status has text, icon, and semantic tone", () => {
  for (const status of orderStatusSchema.options) expect(presentOrderStatus(status)).toEqual(expect.objectContaining({ label: expect.any(String), icon: expect.any(String), tone: expect.any(String) }));
});

test("catalog states preserve semantic meaning", () => {
  expect(presentProductStatus("ACTIVE").tone).toBe("success");
  expect(presentProductStatus("INACTIVE").tone).toBe("neutral");
  expect(presentStockState("LOW").tone).toBe("warning");
  expect(presentStockState("OUT").tone).toBe("danger");
});
