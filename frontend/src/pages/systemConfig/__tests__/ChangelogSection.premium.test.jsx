/**
 * O Mural de Atualizações (administração): a marca Premium é do Master.
 *
 * O servidor recusa a qualquer outro perfil (403) — aqui prova-se que o ecrã
 * nem a oferece, e que o que o Master faz chega ao pedido.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const papel = vi.hoisted(() => ({ valor: "master" }));
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => ({ effectiveRole: papel.valor, user: { id: "u1", role: papel.valor } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const api = vi.hoisted(() => ({
  getSystemChangelogs: vi.fn(),
  generateChangelogAI: vi.fn(),
  diagnoseChangelog: vi.fn(),
  createAnnouncement: vi.fn(),
  setChangelogPremium: vi.fn(),
}));
vi.mock("../../../services/api", () => api);

import { toast } from "sonner";
import ChangelogSection from "../ChangelogSection";

const ENTRADAS = [
  { id: "e-premium", version: "2026-10-01", published_at: "2026-10-01T10:00:00+00:00", generated_by: "ai", content_markdown: "módulo", is_premium: true },
  { id: "e-normal", version: "2026-09-01", published_at: "2026-09-01T10:00:00+00:00", generated_by: "ai", content_markdown: "nota", is_premium: false },
];

beforeEach(() => {
  vi.clearAllMocks();
  papel.valor = "master";
  api.getSystemChangelogs.mockResolvedValue({ data: structuredClone(ENTRADAS) });
  api.generateChangelogAI.mockResolvedValue({ data: { changelog: { id: "novo", version: "v", content_markdown: "x", generated_by: "ai", is_premium: false } } });
  api.setChangelogPremium.mockResolvedValue({ data: {} });
});

describe("ChangelogSection — marca Premium", () => {
  it("mostra o selo nas entradas Premium e só nelas", async () => {
    render(<ChangelogSection />);
    await screen.findByText(/v2026-10-01/);
    expect(screen.getAllByTestId("badge-premium")).toHaveLength(1);
  });

  it("o Master vê os controlos e a caixa na geração", async () => {
    render(<ChangelogSection />);
    expect(await screen.findByTestId("alternar-premium-e-premium")).toHaveTextContent("Remover Premium");
    expect(screen.getByTestId("alternar-premium-e-normal")).toHaveTextContent("Marcar como Premium");
    expect(screen.getByRole("checkbox", { name: "Marcar como Premium" })).not.toBeChecked();
  });

  it.each(["admin", "ceo", "diretor", "consultor"])("%s não vê nenhum controlo de Premium", async (outro) => {
    papel.valor = outro;
    render(<ChangelogSection />);
    await screen.findByText(/v2026-10-01/);
    expect(screen.queryByTestId("alternar-premium-e-normal")).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "Marcar como Premium" })).toBeNull();
    // O selo (informação) continua visível; o controlo (decisão) não.
    expect(screen.getAllByTestId("badge-premium")).toHaveLength(1);
  });

  it("marcar chama o servidor, actualiza a entrada e o botão muda", async () => {
    render(<ChangelogSection />);
    await userEvent.click(await screen.findByTestId("alternar-premium-e-normal"));
    await waitFor(() => expect(api.setChangelogPremium).toHaveBeenCalledWith("e-normal", true));
    await waitFor(() => expect(screen.getAllByTestId("badge-premium")).toHaveLength(2));
    expect(screen.getByTestId("alternar-premium-e-normal")).toHaveTextContent("Remover Premium");
    expect(toast.success).toHaveBeenCalled();
  });

  it("remover chama o servidor com false", async () => {
    render(<ChangelogSection />);
    await userEvent.click(await screen.findByTestId("alternar-premium-e-premium"));
    await waitFor(() => expect(api.setChangelogPremium).toHaveBeenCalledWith("e-premium", false));
    await waitFor(() => expect(screen.queryByTestId("badge-premium")).toBeNull());
  });

  it("uma recusa do servidor não muda o ecrã e diz porquê", async () => {
    api.setChangelogPremium.mockRejectedValue({ response: { data: { detail: "Só o Master pode marcar uma novidade como Premium." } } });
    render(<ChangelogSection />);
    await userEvent.click(await screen.findByTestId("alternar-premium-e-normal"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Só o Master pode marcar uma novidade como Premium."));
    expect(screen.getAllByTestId("badge-premium")).toHaveLength(1);
  });

  it("a geração por omissão NÃO pede Premium", async () => {
    render(<ChangelogSection />);
    await userEvent.click(await screen.findByRole("button", { name: /Gerar Notas de Atualização/ }));
    await waitFor(() => expect(api.generateChangelogAI).toHaveBeenCalled());
    expect(api.generateChangelogAI.mock.calls[0][0]).toEqual({ source_type: "worklog" });
  });

  it("com a caixa marcada, o Master gera já como Premium", async () => {
    render(<ChangelogSection />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Marcar como Premium" }));
    await userEvent.click(screen.getByRole("button", { name: /Gerar Notas de Atualização/ }));
    await waitFor(() => expect(api.generateChangelogAI).toHaveBeenCalledWith({ source_type: "worklog", is_premium: true }));
  });

  it("quem não é Master nunca envia is_premium", async () => {
    papel.valor = "admin";
    render(<ChangelogSection />);
    await userEvent.click(await screen.findByRole("button", { name: /Gerar Notas de Atualização/ }));
    await waitFor(() => expect(api.generateChangelogAI).toHaveBeenCalled());
    expect(api.generateChangelogAI.mock.calls[0][0]).not.toHaveProperty("is_premium");
  });
});
