import type { OrderStatus } from "@/api/contracts";

export type MutationAttempt = {
  orderId: string; targetStatus: OrderStatus; reason: string | null;
  version: number; idempotencyKey: string; ambiguous: boolean;
};

let current: MutationAttempt | null = null;

export const mutationAttempts = {
  getMatching(input: Omit<MutationAttempt, "idempotencyKey" | "ambiguous">) {
    return current && current.orderId === input.orderId && current.targetStatus === input.targetStatus
      && current.reason === input.reason && current.version === input.version ? current : null;
  },
  set(value: MutationAttempt) { current = value; },
  markAmbiguous() { if (current) current = { ...current, ambiguous: true }; },
  clear() { current = null; },
};
