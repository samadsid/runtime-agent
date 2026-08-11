import {
  clearConversation,
  CONVERSATION_KEY,
  DEV_CUSTOMER_KEY,
  loadConversationId,
  loadOrCreateDevCustomerId,
  loadTranscript,
  TRANSCRIPT_KEY,
} from "./storage";

describe("browser storage", () => {
  beforeEach(() => localStorage.clear());

  it("recovers from malformed transcript data and preserves valid entries", () => {
    localStorage.setItem(TRANSCRIPT_KEY, "not-json");
    expect(loadTranscript()).toEqual([]);
    localStorage.setItem(
      TRANSCRIPT_KEY,
      JSON.stringify([
        { id: "1", role: "assistant", text: "ok", timestamp: "now", status: "sent" },
        { role: "customer", text: "invalid" },
      ]),
    );
    expect(loadTranscript()).toHaveLength(1);
  });

  it("keeps a stable development customer ID when clearing chat", () => {
    const customerId = loadOrCreateDevCustomerId();
    localStorage.setItem(CONVERSATION_KEY, "conversation");
    localStorage.setItem(TRANSCRIPT_KEY, "[]");
    clearConversation();
    expect(loadConversationId()).toBeNull();
    expect(localStorage.getItem(TRANSCRIPT_KEY)).toBeNull();
    expect(localStorage.getItem(DEV_CUSTOMER_KEY)).toBe(customerId);
    expect(loadOrCreateDevCustomerId()).toBe(customerId);
  });
});
