export type Coordinate = { latitude: number; longitude: number };

export function closeRing(points: Coordinate[]): number[][] {
  if (points.length < 3) throw new Error("At least three vertices are required.");
  return [...points, points[0]!].map((point) => [point.longitude, point.latitude]);
}

export function polygonBoundary(points: Coordinate[]) {
  return { type: "Polygon" as const, coordinates: [closeRing(points)] };
}

export function circlePolygon(center: Coordinate, radiusMeters: number, vertices = 64): Coordinate[] {
  if (!Number.isFinite(radiusMeters) || radiusMeters <= 0) throw new Error("Radius must be positive.");
  const angular = radiusMeters / 6_371_008.8;
  const latitude = center.latitude * Math.PI / 180;
  const longitude = center.longitude * Math.PI / 180;
  return Array.from({ length: vertices }, (_, index) => {
    const bearing = 2 * Math.PI * index / vertices;
    const targetLatitude = Math.asin(Math.sin(latitude) * Math.cos(angular) + Math.cos(latitude) * Math.sin(angular) * Math.cos(bearing));
    const targetLongitude = longitude + Math.atan2(Math.sin(bearing) * Math.sin(angular) * Math.cos(latitude), Math.cos(angular) - Math.sin(latitude) * Math.sin(targetLatitude));
    return { latitude: targetLatitude * 180 / Math.PI, longitude: ((targetLongitude * 180 / Math.PI + 540) % 360) - 180 };
  });
}

export function boundaryPoints(boundary: { type: string; coordinates: unknown[] }): Coordinate[] {
  const ring = boundary.type === "Polygon" ? boundary.coordinates[0] : (boundary.coordinates[0] as unknown[])[0];
  if (!Array.isArray(ring)) return [];
  return ring.slice(0, -1).flatMap((value) => Array.isArray(value) && value.length === 2 ? [{ longitude: Number(value[0]), latitude: Number(value[1]) }] : []);
}
