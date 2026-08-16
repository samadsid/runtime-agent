import { mutationAttempts } from "./mutation-attempts";

afterEach(() => mutationAttempts.clear());

test("retains a key only for the same logical mutation", () => {
  const input = { orderId: "order-1", targetStatus: "PREPARING" as const, reason: null, version: 2 };
  mutationAttempts.set({ ...input, idempotencyKey: "key-12345678", ambiguous: false });
  mutationAttempts.markAmbiguous();
  expect(mutationAttempts.getMatching(input)).toMatchObject({ idempotencyKey: "key-12345678", ambiguous: true });
  expect(mutationAttempts.getMatching({ ...input, version: 3 })).toBeNull();
});
