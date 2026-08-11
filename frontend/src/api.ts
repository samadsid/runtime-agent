import type { ChatResponse, FrontendConfig } from "./types";

export type ChatErrorKind = "network" | "client" | "server" | "invalid";

export class ChatApiError extends Error {
  constructor(readonly kind: ChatErrorKind) {
    super(kind);
  }
}

export function loadConfig(
  env: ImportMetaEnv = import.meta.env,
  production = import.meta.env.PROD,
): FrontendConfig {
  const configured = env.VITE_CHAT_API_URL ?? "http://localhost:8000/chat";
  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    throw new Error("VITE_CHAT_API_URL must be an absolute URL.");
  }
  if (production && url.protocol !== "https:") {
    throw new Error("Production chat API URL must use HTTPS.");
  }
  return {
    chatApiUrl: url.toString(),
    devCustomerHeaderEnabled:
      !production && env.VITE_ENABLE_DEV_CUSTOMER_HEADER === "true",
  };
}

export function validateChatResponse(payload: unknown): ChatResponse {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new ChatApiError("invalid");
  }
  const value = payload as Record<string, unknown>;
  if (
    typeof value.conversation_id !== "string" ||
    value.conversation_id.trim() === "" ||
    typeof value.reply !== "string"
  ) {
    throw new ChatApiError("invalid");
  }
  return { conversation_id: value.conversation_id, reply: value.reply };
}

export async function sendChat(
  config: FrontendConfig,
  message: string,
  conversationId: string | null,
  requestId: string,
  customerId: string | null,
): Promise<ChatResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Request-Id": requestId,
  };
  if (config.devCustomerHeaderEnabled && customerId) {
    headers["X-Dev-Customer-Id"] = customerId;
  }
  let response: Response;
  try {
    response = await fetch(config.chatApiUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
  } catch {
    throw new ChatApiError("network");
  }
  if (!response.ok) {
    throw new ChatApiError(response.status >= 500 ? "server" : "client");
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ChatApiError("invalid");
  }
  return validateChatResponse(payload);
}

export function customerSafeError(error: unknown): string {
  if (error instanceof ChatApiError) {
    if (error.kind === "network") return "The chat service could not be reached.";
    if (error.kind === "server") return "The chat service is temporarily unavailable.";
    if (error.kind === "invalid") return "The chat service returned an invalid response.";
  }
  return "Your message could not be sent.";
}
