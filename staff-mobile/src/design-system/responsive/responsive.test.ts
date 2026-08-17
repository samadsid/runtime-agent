import { getGridColumns, getLayoutTier } from "./use-responsive-layout";

test.each([[360, "compact"], [599, "compact"], [600, "medium"], [768, "medium"], [899, "medium"], [900, "expanded"], [1280, "expanded"]] as const)("width %s resolves to %s", (width, tier) => {
  expect(getLayoutTier(width)).toBe(tier);
});

test("grid columns honor usable content width and item minimums", () => {
  expect(getGridColumns(360, 260, 12)).toBe(1);
  expect(getGridColumns(600, 260, 12)).toBe(2);
  expect(getGridColumns(1280, 260, 12)).toBe(3);
});
