/**
 * PartilhaCard — quem mais vê o processo, e a revogação à mão (D-25).
 * Falseia só a rede. Forma REAL do `partner_companies` e da resposta.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ revokeProcessPartner: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast }));

import PartilhaCard from "../PartilhaCard";

const PROCESSO = {
  id: "p1",
  partner_companies: [
    { company_id: "cmp-domus", company_name: "Domus", network_id: "grupo_domus", added_at: "2026-10-09T10:00:00Z" },
    { company_id: "cmp-x", company_name: "Outra Casa", network_id: "rede_x", added_at: "2026-10-09T11:00:00Z" },
  ],
};

describe("PartilhaCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.revokeProcessPartner.mockResolvedValue({
      data: { success: true, parceiros_restantes: [PROCESSO.partner_companies[1]] },
    });
  });

  it("sem parceiros não desenha nada (um cartão vazio em todos os processos é ruído)", () => {
    const { container } = render(<PartilhaCard process={{ id: "p1" }} podeRevogar />);
    expect(container.firstChild).toBeNull();
  });

  it("lista QUEM tem acesso", () => {
    render(<PartilhaCard process={PROCESSO} podeRevogar />);
    const cartao = screen.getByTestId("cartao-partilha");
    expect(cartao.textContent).toContain("Domus");
    expect(cartao.textContent).toContain("Outra Casa");
  });

  it("quem não pode revogar vê a lista mas NÃO o botão", () => {
    render(<PartilhaCard process={PROCESSO} podeRevogar={false} />);
    expect(screen.getByTestId("cartao-partilha").textContent).toContain("Domus");
    expect(screen.queryByRole("button", { name: /Revogar partilha com/ })).toBeNull();
  });

  it("revogar pergunta ANTES e não chama o servidor enquanto não confirmar", () => {
    render(<PartilhaCard process={PROCESSO} podeRevogar />);

    fireEvent.click(screen.getByRole("button", { name: "Revogar partilha com Domus" }));

    const dialogo = screen.getByTestId("dialogo-revogar-partilha");
    expect(dialogo.textContent).toContain("Domus deixa de ver este processo");
    expect(api.revokeProcessPartner).not.toHaveBeenCalled();
  });

  it("confirmar revoga a empresa CERTA e devolve o que sobra", async () => {
    const onRevoked = vi.fn();
    render(<PartilhaCard process={PROCESSO} podeRevogar onRevoked={onRevoked} />);
    fireEvent.click(screen.getByRole("button", { name: "Revogar partilha com Outra Casa" }));

    fireEvent.click(within(screen.getByTestId("dialogo-revogar-partilha")).getByRole("button", { name: "Revogar partilha" }));

    await waitFor(() => expect(api.revokeProcessPartner).toHaveBeenCalledWith("p1", "cmp-x"));
    await waitFor(() => expect(onRevoked).toHaveBeenCalledWith([PROCESSO.partner_companies[1]]));
    expect(toast.success).toHaveBeenCalled();
  });

  it("cancelar não revoga nada", async () => {
    render(<PartilhaCard process={PROCESSO} podeRevogar />);
    fireEvent.click(screen.getByRole("button", { name: "Revogar partilha com Domus" }));

    fireEvent.click(within(screen.getByTestId("dialogo-revogar-partilha")).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByTestId("dialogo-revogar-partilha")).toBeNull());
    expect(api.revokeProcessPartner).not.toHaveBeenCalled();
  });

  it("a recusa do servidor mostra a MENSAGEM dele e mantém o diálogo aberto", async () => {
    api.revokeProcessPartner.mockRejectedValue({
      response: { data: { detail: "Só a empresa dona do processo pode revogar a partilha." } },
    });
    const onRevoked = vi.fn();
    render(<PartilhaCard process={PROCESSO} podeRevogar onRevoked={onRevoked} />);
    fireEvent.click(screen.getByRole("button", { name: "Revogar partilha com Domus" }));

    fireEvent.click(within(screen.getByTestId("dialogo-revogar-partilha")).getByRole("button", { name: "Revogar partilha" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Só a empresa dona do processo pode revogar a partilha."),
    );
    expect(onRevoked).not.toHaveBeenCalled();
  });

  describe("cadeia de partilhas (Out 2026)", () => {
    const EM_CADEIA = {
      id: "p1",
      partner_companies: [
        { company_id: "cmp-z", company_name: "Empresa Z", network_id: "rede-z" },
        { company_id: "cmp-w", company_name: "Empresa W", network_id: "rede-w" },
      ],
      linhagem: {
        partilhas: [
          { company_id: "cmp-z", nome: "Empresa Z", partilhado_por: "Empresa Y", pode_revogar: false },
          { company_id: "cmp-w", nome: "Empresa W", partilhado_por: "Empresa Z", pode_revogar: true },
        ],
      },
    };

    it("diz de quem veio cada elo", () => {
      render(<PartilhaCard process={EM_CADEIA} podeRevogar />);
      const dizeres = screen.getAllByTestId("partilhado-por").map((el) => el.textContent);
      expect(dizeres).toEqual(["Partilhado por Empresa Y", "Partilhado por Empresa Z"]);
    });

    it("com o papel certo, o botão só aparece nos elos que o servidor diz que posso retirar", () => {
      render(<PartilhaCard process={EM_CADEIA} podeRevogar />);
      expect(screen.queryByRole("button", { name: "Revogar partilha com Empresa Z" })).toBeNull();
      expect(screen.getByRole("button", { name: "Revogar partilha com Empresa W" })).toBeInTheDocument();
    });

    it("sem a informação do servidor o botão depende só do papel (como antes)", () => {
      render(<PartilhaCard process={{ ...EM_CADEIA, linhagem: undefined }} podeRevogar />);
      expect(screen.getAllByRole("button", { name: /^Revogar partilha com/ })).toHaveLength(2);
      expect(screen.queryByTestId("partilhado-por")).toBeNull();
    });

    it("sem o papel nunca há botão, mesmo que o servidor diga que o elo é meu", () => {
      render(<PartilhaCard process={EM_CADEIA} podeRevogar={false} />);
      expect(screen.queryByRole("button", { name: /^Revogar partilha com/ })).toBeNull();
    });
  });
});
