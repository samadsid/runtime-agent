import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

describe("customer chat", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends with Enter, renders Unicode and continues the conversation", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: "conversation-1", reply: "उपलब्ध:\nChicken Breast" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: "conversation-1", reply: "Added" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    const composer = screen.getByLabelText("Message Commerce Assistant");
    await user.type(composer, "Mujhe chicken breast chahiye{Enter}");
    expect(await screen.findByText(/उपलब्ध:/)).toBeInTheDocument();
    expect(screen.getByText(/Chicken Breast/)).toBeInTheDocument();
    await user.type(composer, "5 kg add kar do{Enter}");
    await screen.findByText("Added");

    const firstBody = JSON.parse((fetchMock.mock.calls[0]![1] as RequestInit).body as string);
    const secondBody = JSON.parse((fetchMock.mock.calls[1]![1] as RequestInit).body as string);
    expect(firstBody.conversation_id).toBeNull();
    expect(secondBody.conversation_id).toBe("conversation-1");
  });

  it("inserts a newline with Shift+Enter", async () => {
    const user = userEvent.setup();
    render(<App />);
    const composer = screen.getByLabelText("Message Commerce Assistant");
    await user.type(composer, "line one{Shift>}{Enter}{/Shift}line two");
    expect(composer).toHaveValue("line one\nline two");
  });

  it("retains the request ID for a manual retry", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: "conversation-1", reply: "Recovered" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await user.type(screen.getByLabelText("Message Commerce Assistant"), "hello{Enter}");
    await screen.findByText("Not sent");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("Recovered");
    const firstHeaders = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>;
    const secondHeaders = (fetchMock.mock.calls[1]![1] as RequestInit).headers as Record<string, string>;
    expect(secondHeaders["X-Request-Id"]).toBe(firstHeaders["X-Request-Id"]);
  });

  it("confirms and clears only local conversation presentation", async () => {
    const user = userEvent.setup();
    localStorage.setItem("commerce_conversation_id", "conversation-1");
    localStorage.setItem("commerce_chat_transcript", JSON.stringify([{ id: "1", role: "assistant", text: "Stored reply", timestamp: new Date().toISOString(), status: "sent" }]));
    localStorage.setItem("commerce_dev_customer_id", "customer-1");
    render(<App />);
    expect(screen.getByText("Stored reply")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start new chat" }));
    await waitFor(() => expect(screen.getByText("Welcome")).toBeInTheDocument());
    expect(localStorage.getItem("commerce_conversation_id")).toBeNull();
    expect(localStorage.getItem("commerce_dev_customer_id")).toBe("customer-1");
  });
});
