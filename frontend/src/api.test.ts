import { ChatApiError, customerSafeError, sendChat, validateChatResponse } from "./api";
import type { FrontendConfig } from "./types";

const config: FrontendConfig = {
  chatApiUrl: "http://localhost:8000/chat",
  devCustomerHeaderEnabled: true,
};

describe("chat API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("validates the exact response contract", () => {
    expect(validateChatResponse({ conversation_id: "abc", reply: "नमस्ते\nHello" })).toEqual({
      conversation_id: "abc",
      reply: "नमस्ते\nHello",
    });
    for (const invalid of [null, [], {}, { conversation_id: "", reply: "x" }, { conversation_id: "x" }]) {
      expect(() => validateChatResponse(invalid)).toThrow(ChatApiError);
    }
  });

  it("sends continuity and gated identity headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ conversation_id: "conversation-1", reply: "Done" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await sendChat(config, "hello", null, "request-1", "customer-1");
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ message: "hello", conversation_id: null });
    expect(init.headers).toMatchObject({
      "X-Request-Id": "request-1",
      "X-Dev-Customer-Id": "customer-1",
    });
  });

  it("maps failures without exposing response bodies", () => {
    expect(customerSafeError(new ChatApiError("network"))).toContain("could not be reached");
    expect(customerSafeError(new ChatApiError("server"))).toContain("temporarily unavailable");
    expect(customerSafeError(new ChatApiError("invalid"))).toContain("invalid response");
    expect(customerSafeError(new ChatApiError("client"))).toContain("could not be sent");
  });
});
