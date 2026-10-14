/**
 * Conta de Indexação (IMAP Recepção) — «Remover conta» (Lote 4, Out 2026).
 *
 * Havia como configurar e testar a conta, mas não como a retirar. O botão só existe com uma conta
 * configurada, pede confirmação e apaga os quatro campos do `system_webmail` (a password incluída).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../contexts/AuthContext", () => ({ useAuth: () => ({ token: "tk" }) }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("../../../services/api", () => ({ testCompanyEmailConnection: vi.fn() }));

import { IndexationImapCard } from "../IndexationImapCard";

const CONFIGURADA = {
  config: { system_webmail: { imap_host: "imap.empresa.pt", imap_port: 993, email_user: "indexacao@empresa.pt", app_password: "xxxx" } },
};
const VAZIA = { config: { system_webmail: { imap_host: "", imap_port: 993, email_user: "", app_password: "" } } };

let pedidos;
function servir(config, { remover = { ok: true, json: async () => ({}) } } = {}) {
  pedidos = [];
  globalThis.fetch = vi.fn(async (url, opcoes = {}) => {
    pedidos.push({ url, ...opcoes });
    if (opcoes.method === "PATCH") return remover;
    return { ok: true, json: async () => config };
  });
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}><IndexationImapCard /></QueryClientProvider>,
  );
}

beforeEach(() => { toast.success.mockClear(); toast.error.mockClear(); });
afterEach(() => { delete globalThis.fetch; });

describe("IndexationImapCard — remover", () => {
  it("sem conta configurada não há botão de remover", async () => {
    servir(VAZIA);
    montar();
    await screen.findByTestId("indexation-imap-card");
    expect(screen.queryByTestId("indexation-imap-remove-btn")).not.toBeInTheDocument();
  });

  it("com conta configurada o botão existe e pede confirmação antes de apagar", async () => {
    servir(CONFIGURADA);
    const u = userEvent.setup();
    montar();
    await u.click(await screen.findByTestId("indexation-imap-remove-btn"));

    const dialogo = await screen.findByTestId("indexation-imap-remove-dialog");
    expect(within(dialogo).getByText(/indexacao@empresa\.pt/)).toBeInTheDocument();
    expect(pedidos.filter((p) => p.method === "PATCH")).toHaveLength(0);
  });

  it("cancelar não escreve nada", async () => {
    servir(CONFIGURADA);
    const u = userEvent.setup();
    montar();
    await u.click(await screen.findByTestId("indexation-imap-remove-btn"));
    await u.click(await screen.findByRole("button", { name: /Cancelar/i }));

    expect(pedidos.filter((p) => p.method === "PATCH")).toHaveLength(0);
  });

  it("confirmar apaga os quatro campos (incluindo a password), avisa e esvazia o formulário", async () => {
    servir(CONFIGURADA);
    const u = userEvent.setup();
    montar();
    await u.click(await screen.findByTestId("indexation-imap-remove-btn"));
    await u.click(await screen.findByTestId("indexation-imap-remove-confirm"));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("removida")));
    const patch = pedidos.find((p) => p.method === "PATCH");
    expect(patch.url).toMatch(/\/api\/system-config\/system_webmail$/);
    expect(JSON.parse(patch.body)).toEqual({ imap_host: "", imap_port: 993, email_user: "", app_password: "" });
    expect(screen.getByTestId("indexation-imap-host-input")).toHaveValue("");
    expect(screen.queryByTestId("indexation-imap-remove-btn")).not.toBeInTheDocument();
  });

  it("se o servidor recusa, diz-se e a conta mantém-se no ecrã", async () => {
    servir(CONFIGURADA, { remover: { ok: false, json: async () => ({ detail: "Sem permissão" }) } });
    const u = userEvent.setup();
    montar();
    await u.click(await screen.findByTestId("indexation-imap-remove-btn"));
    await u.click(await screen.findByTestId("indexation-imap-remove-confirm"));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId("indexation-imap-host-input")).toHaveValue("imap.empresa.pt");
  });
});
