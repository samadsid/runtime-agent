import { z } from "zod";
import { StaffApiClient } from "./client";
import { createStaffApi } from "./staff-api";

const environment = { apiBaseUrl: "https://staff.example.com", appEnvironment: "staging" as const, requestTimeoutMs: 5000 };

afterEach(() => jest.restoreAllMocks());

test("attaches a token only to authenticated requests", async () => {
  const fetchMock = jest.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ ok: true }) } as Response);
  const client = new StaffApiClient(environment); client.setToken("secret-token");
  await client.request("/public", { schema: z.object({ ok: z.boolean() }) });
  await client.request("/protected", { authenticated: true, schema: z.object({ ok: z.boolean() }) });
  expect((fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>).Authorization).toBeUndefined();
  expect((fetchMock.mock.calls[1]?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
});

test("reports mutation transport failures as ambiguous", async () => {
  jest.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));
  const client = new StaffApiClient(environment); client.setToken("token");
  await expect(client.request("/mutation", { authenticated: true, mutation: true, schema: z.any() })).rejects.toMatchObject({ code: "network_error", ambiguous: true });
});

test("sends exact optimistic-version and logical idempotency headers", async () => {
  const fetchMock = jest.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true, json: async () => ({ order_id: "00000000-0000-4000-8000-000000000001", status: "PREPARING", version: 4, transitioned_at: "2026-08-16T10:00:00Z" }),
  } as Response);
  const client = new StaffApiClient(environment); client.setToken("token");
  await createStaffApi(client).transition({
    orderId: "00000000-0000-4000-8000-000000000001", targetStatus: "PREPARING",
    reason: null, version: 3, idempotencyKey: "logical-action-key",
  });
  const request = fetchMock.mock.calls[0]?.[1];
  expect(request?.headers).toMatchObject({ "If-Match": '"3"', "Idempotency-Key": "logical-action-key" });
  expect(request?.body).toBe('{"target_status":"PREPARING","reason":null}');
});
