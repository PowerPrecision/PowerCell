/**
 * Chat interno: Shift+Enter muda de linha e Enter envia a mensagem
 * com as quebras de linha (antes era uma caixa de uma só linha).
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ token: "t", user: { id: "u1", name: "Eu" } }),
}));

import ChatPanel from "../ChatPanel";

const resposta = (data) => Promise.resolve({ ok: true, json: () => Promise.resolve(data) });

describe("ChatPanel — quebras de linha", () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, opts) => {
      if (url.endsWith("/api/chat/conversations")) {
        return resposta({ conversations: [{ user_id: "u2", user_name: "Rita Silva", is_group: false }] });
      }
      if (url.includes("/api/chat/messages") && opts?.method === "POST") {
        return resposta({ message: { id: "m1", content: JSON.parse(opts.body).content, sender_id: "u1" } });
      }
      if (url.includes("/api/chat/messages")) return resposta({ messages: [], other_user: { id: "u2", name: "Rita Silva" } });
      return resposta({});
    });
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("Shift+Enter não envia; Enter envia o texto com a quebra de linha", async () => {
    render(<ChatPanel open onOpenChange={() => {}} />);
    fireEvent.click(await screen.findByText("Rita Silva"));
    const caixa = await screen.findByPlaceholderText("Escrever mensagem...");

    fireEvent.change(caixa, { target: { value: "linha 1\nlinha 2" } });
    fireEvent.keyDown(caixa, { key: "Enter", shiftKey: true });
    expect(global.fetch.mock.calls.some(([, o]) => o?.method === "POST" && o.body?.includes("linha 1"))).toBe(false);

    fireEvent.keyDown(caixa, { key: "Enter" });
    await waitFor(() => {
      const envio = global.fetch.mock.calls.find(([u, o]) => u.endsWith("/api/chat/messages") && o?.method === "POST");
      expect(JSON.parse(envio[1].body).content).toBe("linha 1\nlinha 2");
    });
  });
});
