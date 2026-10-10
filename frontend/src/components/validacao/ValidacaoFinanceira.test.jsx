/**
 * O selo «Processo Não Validado» e os botões de decisão.
 *
 * Duas coisas que têm de ser verdade ao mesmo tempo: o aviso é inconfundível
 * e os botões só existem para CEO, Diretor e Administrativo — e NADA no
 * ecrã se desactiva por o processo estar por validar.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  decidirValidacaoFinanceira: vi.fn(),
  obterComprovativoDaValidacao: vi.fn(),
}));
vi.mock("@/services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import { toast } from "sonner";
import ValidacaoFinanceira from "./ValidacaoFinanceira";

const POR_VALIDAR = { id: "p-1", validacao_financeira: { estado: "pendente" } };

function montar(props = {}) {
  return render(<ValidacaoFinanceira registo={POR_VALIDAR} papelEfectivo="ceo" {...props} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.decidirValidacaoFinanceira.mockResolvedValue({ success: true });
  api.obterComprovativoDaValidacao.mockResolvedValue({ url: "https://s3.exemplo/get" });
});

describe("o selo", () => {
  it("diz «⚠️ Processo Não Validado» e é um alerta", () => {
    montar();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByTestId("selo-nao-validado")).toHaveTextContent("⚠️ Processo Não Validado");
  });

  it("diz que o processo continua a poder ser trabalhado (nunca bloqueia)", () => {
    montar();
    expect(screen.getByRole("alert")).toHaveTextContent("Continua a poder trabalhar o processo");
  });

  it("um processo rejeitado continua com o selo e mostra o motivo", () => {
    montar({ registo: { id: "p-1", validacao_financeira: { estado: "rejeitado", motivo: "Sem viabilidade" } } });
    expect(screen.getByTestId("selo-nao-validado")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("rejeitada: Sem viabilidade");
  });

  it("validado: sem alarme, só um selo discreto", () => {
    montar({ registo: { id: "p-1", validacao_financeira: { estado: "validado" } } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("selo-nao-validado")).not.toBeInTheDocument();
    expect(screen.getByTestId("validacao-validada")).toHaveTextContent("Validado");
  });

  it.each([
    [{ id: "p" }],
    [{ id: "p", validacao_financeira: null }],
    [{ id: "p", validacao_financeira: {} }],
    [{ id: "p", validacao_financeira: { estado: "inventado" } }],
  ])("um registo que não passa por validação não mostra nada (%j)", (registo) => {
    const { container } = montar({ registo });
    expect(container).toBeEmptyDOMElement();
  });
});

describe("quem vê os botões", () => {
  it.each(["ceo", "diretor", "administrativo"])("%s vê «Validar Processo» e «Rejeitar»", (papel) => {
    montar({ papelEfectivo: papel });
    expect(screen.getByRole("button", { name: /Validar Processo/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rejeitar/ })).toBeInTheDocument();
  });

  it.each(["consultor", "intermediario", "indexacao", "admin", "master", "parceiro", "", undefined])(
    "%s vê o aviso mas NÃO os botões",
    (papel) => {
      montar({ papelEfectivo: papel });
      expect(screen.getByTestId("selo-nao-validado")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Validar Processo/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Rejeitar/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Ver comprovativo/ })).not.toBeInTheDocument();
    }
  );
});

describe("decidir", () => {
  it("validar chama o servidor e avisa quem o montou", async () => {
    const onDecidido = vi.fn();
    montar({ onDecidido });
    await userEvent.click(screen.getByRole("button", { name: /Validar Processo/ }));
    await waitFor(() => expect(api.decidirValidacaoFinanceira).toHaveBeenCalledWith("process", "p-1", { decision: "validate" }));
    expect(onDecidido).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it("rejeitar exige um motivo e só depois envia", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Rejeitar/ }));
    const dialogo = await screen.findByRole("dialog");
    await userEvent.click(within(dialogo).getByTestId("confirmar-rejeicao"));
    expect(within(dialogo).getByRole("alert")).toHaveTextContent("Indique o motivo");
    expect(api.decidirValidacaoFinanceira).not.toHaveBeenCalled();

    await userEvent.type(within(dialogo).getByLabelText("Motivo"), "Comprovativo ilegível");
    await userEvent.click(within(dialogo).getByTestId("confirmar-rejeicao"));
    await waitFor(() => expect(api.decidirValidacaoFinanceira).toHaveBeenCalledWith(
      "process", "p-1", { decision: "reject", reason: "Comprovativo ilegível" },
    ));
  });

  it("uma lead decide-se com o tipo «lead»", async () => {
    montar({ tipo: "lead", compacto: true });
    await userEvent.click(screen.getByRole("button", { name: /Validar Processo/ }));
    await waitFor(() => expect(api.decidirValidacaoFinanceira).toHaveBeenCalledWith("lead", "p-1", { decision: "validate" }));
  });

  it("o erro do servidor aparece e não dá a decisão por tomada", async () => {
    api.decidirValidacaoFinanceira.mockRejectedValue({ response: { data: { detail: "Esta decisão já foi tomada." } } });
    const onDecidido = vi.fn();
    montar({ onDecidido });
    await userEvent.click(screen.getByRole("button", { name: /Validar Processo/ }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Esta decisão já foi tomada."));
    expect(onDecidido).not.toHaveBeenCalled();
  });

  it("«Ver comprovativo» abre o URL sem `opener`", async () => {
    const abrir = vi.spyOn(window, "open").mockImplementation(() => null);
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Ver comprovativo/ }));
    await waitFor(() => expect(abrir).toHaveBeenCalledWith("https://s3.exemplo/get", "_blank", "noopener,noreferrer"));
    abrir.mockRestore();
  });

  it("um processo já rejeitado só se pode validar (não rejeitar outra vez)", () => {
    montar({ registo: { id: "p-1", validacao_financeira: { estado: "rejeitado", motivo: "x" } } });
    expect(screen.getByRole("button", { name: /Validar Processo/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Rejeitar/ })).not.toBeInTheDocument();
  });
});

describe("modo compacto (lista de registos)", () => {
  it("mostra «Não validado» e as acções, sem o texto longo", () => {
    montar({ tipo: "lead", compacto: true });
    expect(screen.getByText("Não validado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Validar Processo/ })).toBeInTheDocument();
    expect(screen.queryByTestId("selo-nao-validado")).not.toBeInTheDocument();
  });
});
