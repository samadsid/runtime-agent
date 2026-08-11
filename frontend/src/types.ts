export type MessageRole = "customer" | "assistant";
export type DeliveryStatus = "pending" | "sent" | "failed";

export interface TranscriptMessage {
  id: string;
  role: MessageRole;
  text: string;
  timestamp: string;
  status: DeliveryStatus;
  requestId?: string;
}

export interface ChatResponse {
  conversation_id: string;
  reply: string;
}

export interface FrontendConfig {
  chatApiUrl: string;
  devCustomerHeaderEnabled: boolean;
}
