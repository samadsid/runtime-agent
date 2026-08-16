import { buildDateRange } from "./date-range";

test("builds a bounded UTC date range", () => {
  expect(buildDateRange("2026-08-01", "2026-08-16")).toEqual({
    createdFrom: "2026-08-01T00:00:00.000Z", createdTo: "2026-08-16T23:59:59.999Z",
  });
});

test("rejects invalid and overlong ranges", () => {
  expect(buildDateRange("2026-08-16", "2026-08-01").error).toBeDefined();
  expect(buildDateRange("2026-01-01", "2026-08-01").error).toBeDefined();
});
