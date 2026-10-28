/**
 * Chat interno:
 * - Shift+Enter muda de linha e Enter envia a mensagem com as quebras de linha;
 * - o lápis abre a caixa de edição (antes comparava o objecto com o id e nunca abria);
 * - toda a comunicação passa pelo Axios (`services/api.js`), nunca `fetch` cru.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ token: "t", user: { id: "u1", name: "Eu" } }),
}));

vi.mock("../../services/api", () => ({
  getChatConversations: vi.fn(),
  getChatUnreadCount: vi.fn(),
  getChatGroups: vi.fn(),
  getChatMessages: vi.fn(),
  getChatUsers: vi.fn(),
  sendChatTyping: vi.fn(),
  sendChatMessage: vi.fn(),
  uploadChatAttachment: vi.fn(),
  reactToChatMessage: vi.fn(),
  editChatMessage: vi.fn(),
  deleteChatMessage: vi.fn(),
  createChatGroup: vi.fn(),
  searchChatMessages: vi.fn(),
}));

import * as api from "../../services/api";
import ChatPanel from "../ChatPanel";

const AQUI = path.dirname(fileURLToPath(import.meta.url));

const ok = (data) => Promise.resolve({ data });

async function abrirConversaComRita(mensagens = []) {
  render(<ChatPanel open onOpenChange={() => {}} />);
  fireEvent.click(await screen.findByText("Rita Silva"));
  return mensagens;
}

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getChatConversations.mockImplementation(() =>
      ok({ conversations: [{ user_id: "u2", user_name: "Rita Silva", is_group: false }] })
    );
    api.getChatUnreadCount.mockImplementation(() => ok({}));
    api.getChatGroups.mockImplementation(() => ok({ groups: [] }));
    api.getChatUsers.mockImplementation(() => ok({ users: [] }));
    api.sendChatTyping.mockImplementation(() => ok({}));
    api.getChatMessages.mockImplementation(() =>
      ok({
        messages: [{ id: "m0", sender_id: "u1", content: "texto antigo", created_at: "2026-10-28T10:00:00Z" }],
        other_user: { id: "u2", name: "Rita Silva" },
      })
    );
    api.sendChatMessage.mockImplementation((body) =>
      ok({ message: { id: "m1", sender_id: "u1", content: body.content } })
    );
    api.editChatMessage.mockImplementation(() => ok({ success: true }));
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("Shift+Enter não envia; Enter envia o texto com a quebra de linha", async () => {
    await abrirConversaComRita();
    const caixa = await screen.findByPlaceholderText("Escrever mensagem...");

    fireEvent.change(caixa, { target: { value: "linha 1\nlinha 2" } });
    fireEvent.keyDown(caixa, { key: "Enter", shiftKey: true });
    expect(api.sendChatMessage).not.toHaveBeenCalled();

    fireEvent.keyDown(caixa, { key: "Enter" });
    await waitFor(() =>
      expect(api.sendChatMessage).toHaveBeenCalledWith(
        expect.objectContaining({ receiver_id: "u2", content: "linha 1\nlinha 2" })
      )
    );
  });

  it("o lápis abre a caixa de edição e guarda o texto novo", async () => {
    await abrirConversaComRita();
    fireEvent.click(await screen.findByRole("button", { name: "Editar mensagem" }));

    const caixa = await screen.findByDisplayValue("texto antigo");
    fireEvent.change(caixa, { target: { value: "texto novo\ncom duas linhas" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar edição" }));

    await waitFor(() =>
      expect(api.editChatMessage).toHaveBeenCalledWith("m0", "texto novo\ncom duas linhas")
    );
    await waitFor(() =>
      expect(screen.queryByDisplayValue("texto novo\ncom duas linhas")).not.toBeInTheDocument()
    );
  });

  it("não usa fetch cru", () => {
    const src = fs.readFileSync(path.resolve(AQUI, "../ChatPanel.jsx"), "utf8");
    expect(src).not.toMatch(/\bfetch\(/);
    const layout = fs.readFileSync(path.resolve(AQUI, "../../layouts/DashboardLayout.js"), "utf8");
    expect(layout).not.toMatch(/fetch\([^)]*\/chat\//);
  });
});
