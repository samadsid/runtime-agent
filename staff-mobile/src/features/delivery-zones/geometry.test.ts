import { circlePolygon, closeRing, polygonBoundary } from "./geometry";

test("GeoJSON is longitude-first and closed", () => {
  expect(closeRing([{ latitude: 1, longitude: 2 }, { latitude: 3, longitude: 4 }, { latitude: 5, longitude: 6 }])).toEqual([[2, 1], [4, 3], [6, 5], [2, 1]]);
});

test("circle editor produces a bounded canonical polygon", () => {
  const points = circlePolygon({ latitude: 28.6, longitude: 77.2 }, 1000);
  expect(points).toHaveLength(64);
  expect(polygonBoundary(points).coordinates[0]).toHaveLength(65);
});
