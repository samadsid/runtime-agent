import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { customerSafeError, loadConfig, sendChat } from "./api";
import {
  clearConversation,
  loadConversationId,
  loadOrCreateDevCustomerId,
  loadTranscript,
  saveConversationId,
  saveTranscript,
} from "./storage";
import type { FrontendConfig, TranscriptMessage } from "./types";

const MAX_MESSAGE_LENGTH = 2_000;
const WELCOME = "Hi! How can I help you today?";

function now(): string {
  return new Date().toISOString();
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf())
    ? ""
    : new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

export default function App() {
  const [conversationId, setConversationId] = useState(loadConversationId);
  const [messages, setMessages] = useState<TranscriptMessage[]>(loadTranscript);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingNewChat, setConfirmingNewChat] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const cancelNewChatRef = useRef<HTMLButtonElement>(null);
  const newChatRef = useRef<HTMLButtonElement>(null);

  const { config, configError } = useMemo<{
    config: FrontendConfig;
    configError: string | null;
  }>(() => {
    try {
      return { config: loadConfig(), configError: null };
    } catch {
      return {
        config: { chatApiUrl: "", devCustomerHeaderEnabled: false },
        configError: "Chat configuration is unavailable.",
      };
    }
  }, []);
  const [customerId] = useState(() =>
    config.devCustomerHeaderEnabled ? loadOrCreateDevCustomerId() : null,
  );

  useEffect(() => {
    saveConversationId(conversationId);
  }, [conversationId]);
  useEffect(() => {
    saveTranscript(messages);
  }, [messages]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);
  useEffect(() => {
    if (confirmingNewChat) cancelNewChatRef.current?.focus();
  }, [confirmingNewChat]);

  async function deliver(customerMessage: TranscriptMessage): Promise<void> {
    setBusy(true);
    setError(null);
    setMessages((current) =>
      current.map((item) =>
        item.id === customerMessage.id ? { ...item, status: "pending" } : item,
      ),
    );
    try {
      const response = await sendChat(
        config,
        customerMessage.text,
        conversationId,
        customerMessage.requestId!,
        customerId,
      );
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current.map((item) =>
          item.id === customerMessage.id ? { ...item, status: "sent" as const } : item,
        ),
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.reply,
          timestamp: now(),
          status: "sent",
        },
      ]);
    } catch (cause) {
      setMessages((current) =>
        current.map((item) =>
          item.id === customerMessage.id ? { ...item, status: "failed" } : item,
        ),
      );
      setError(customerSafeError(cause));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => composerRef.current?.focus());
    }
  }

  function submit(event?: FormEvent): void {
    event?.preventDefault();
    const text = input.trim();
    if (!text || text.length > MAX_MESSAGE_LENGTH || busy || configError) return;
    const customerMessage: TranscriptMessage = {
      id: crypto.randomUUID(),
      role: "customer",
      text,
      timestamp: now(),
      status: "pending",
      requestId: crypto.randomUUID(),
    };
    setInput("");
    setMessages((current) => [...current, customerMessage]);
    void deliver(customerMessage);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  function closeNewChat(): void {
    setConfirmingNewChat(false);
    requestAnimationFrame(() => newChatRef.current?.focus());
  }

  function startNewChat(): void {
    clearConversation();
    setConversationId(null);
    setMessages([]);
    setError(null);
    setConfirmingNewChat(false);
    requestAnimationFrame(() => composerRef.current?.focus());
  }

  const remaining = MAX_MESSAGE_LENGTH - input.length;
  const canSend = input.trim().length > 0 && remaining >= 0 && !busy && !configError;

  return (
    <main className="app-shell">
      <section className="chat-card" aria-label="Customer chat">
        <header className="chat-header">
          <div className="brand-block">
            <div className="brand-mark" aria-hidden="true">C</div>
            <div>
              <h1>Commerce Assistant</h1>
              <p className="availability"><span aria-hidden="true" /> Chat ready</p>
            </div>
          </div>
          <div className="header-actions">
            {conversationId && <span className="saved-indicator">Conversation saved</span>}
            <button
              ref={newChatRef}
              className="secondary-button"
              type="button"
              onClick={() => setConfirmingNewChat(true)}
              disabled={busy}
            >
              New chat
            </button>
          </div>
        </header>

        <div className="conversation" role="log" aria-live="polite" aria-relevant="additions">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-icon" aria-hidden="true">✦</div>
              <h2>Welcome</h2>
              <p>{WELCOME}</p>
            </div>
          )}
          {messages.map((message) => (
            <article key={message.id} className={`message-row ${message.role}`}>
              <div className={`message-bubble ${message.status === "failed" ? "failed" : ""}`}>
                <p>{message.text}</p>
                <div className="message-meta">
                  <time dateTime={message.timestamp}>{formatTime(message.timestamp)}</time>
                  {message.status === "failed" && <span>Not sent</span>}
                </div>
                {message.status === "failed" && message.role === "customer" && (
                  <button className="retry-button" type="button" disabled={busy} onClick={() => void deliver(message)}>
                    Retry
                  </button>
                )}
              </div>
            </article>
          ))}
          {busy && (
            <div className="message-row assistant" aria-label="Assistant is typing">
              <div className="typing-indicator" aria-hidden="true"><span /><span /><span /></div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="status-area" aria-live="assertive">
          {(error || configError) && <p className="error-message">{error || configError}</p>}
        </div>

        <form className="composer" onSubmit={submit}>
          <label htmlFor="chat-message" className="sr-only">Message Commerce Assistant</label>
          <textarea
            ref={composerRef}
            id="chat-message"
            value={input}
            maxLength={MAX_MESSAGE_LENGTH}
            rows={1}
            placeholder="Type your message…"
            disabled={busy || Boolean(configError)}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />
          <span className={`character-count ${remaining < 100 ? "near-limit" : ""}`}>{remaining}</span>
          <button className="send-button" type="submit" disabled={!canSend} aria-label="Send message">
            <span aria-hidden="true">➜</span>
          </button>
        </form>
        <p className="composer-hint">Enter to send · Shift + Enter for a new line</p>
      </section>

      {confirmingNewChat && (
        <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeNewChat()}>
          <section
            className="confirmation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-chat-title"
            onKeyDown={(event) => event.key === "Escape" && closeNewChat()}
          >
            <h2 id="new-chat-title">Start a new chat?</h2>
            <p>This clears the conversation shown in this browser. It does not delete backend commerce records.</p>
            <div className="dialog-actions">
              <button ref={cancelNewChatRef} type="button" className="secondary-button" onClick={closeNewChat}>Cancel</button>
              <button type="button" className="danger-button" onClick={startNewChat}>Start new chat</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
