import type { TranscriptMessage } from "./types";

export const CONVERSATION_KEY = "commerce_conversation_id";
export const TRANSCRIPT_KEY = "commerce_chat_transcript";
export const DEV_CUSTOMER_KEY = "commerce_dev_customer_id";

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function isMessage(value: unknown): value is TranscriptMessage {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    (candidate.role === "customer" || candidate.role === "assistant") &&
    typeof candidate.text === "string" &&
    typeof candidate.timestamp === "string" &&
    (candidate.status === "pending" ||
      candidate.status === "sent" ||
      candidate.status === "failed") &&
    (candidate.requestId === undefined || typeof candidate.requestId === "string")
  );
}

export function loadConversationId(): string | null {
  try {
    const value = storage()?.getItem(CONVERSATION_KEY)?.trim();
    return value || null;
  } catch {
    return null;
  }
}

export function saveConversationId(value: string | null): void {
  try {
    const target = storage();
    if (value) target?.setItem(CONVERSATION_KEY, value);
    else target?.removeItem(CONVERSATION_KEY);
  } catch {
    // Storage is optional presentation continuity.
  }
}

export function loadTranscript(): TranscriptMessage[] {
  try {
    const raw = storage()?.getItem(TRANSCRIPT_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isMessage) : [];
  } catch {
    return [];
  }
}

export function saveTranscript(messages: TranscriptMessage[]): void {
  try {
    storage()?.setItem(TRANSCRIPT_KEY, JSON.stringify(messages));
  } catch {
    // The live UI continues if storage is unavailable or full.
  }
}

export function clearConversation(): void {
  try {
    const target = storage();
    target?.removeItem(CONVERSATION_KEY);
    target?.removeItem(TRANSCRIPT_KEY);
  } catch {
    // The live UI state is still cleared by the caller.
  }
}

export function loadOrCreateDevCustomerId(): string {
  try {
    const target = storage();
    const existing = target?.getItem(DEV_CUSTOMER_KEY)?.trim();
    if (existing) return existing;
    const created = crypto.randomUUID();
    target?.setItem(DEV_CUSTOMER_KEY, created);
    return created;
  } catch {
    return crypto.randomUUID();
  }
}
