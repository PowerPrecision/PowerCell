/**
 * O cartão da origem financeira (Bloco 4, ponto 7).
 *
 * Montado com o `QueryClient` REAL e só o `services/api` falseado. A forma
 * dos dados é a do servidor (`services/origem_financeira.descrever`):
 * `{process_id, definida, tipo, rotulo, angariador: {id, nome, papel}|null,
 *   definido_por, definido_em}` e `{process_id, candidatos: [{id, nome, papel}]}`.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getOrigemFinanceira: vi.fn(),
  getCandidatosOrigemFinanceira: vi.fn(),
  setOrigemFinanceira: vi.fn(),
}));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import OrigemFinanceiraCard from "../OrigemFinanceiraCard";

const SEM_ORIGEM = {
  process_id: "p1", definida: false, tipo: null, rotulo: null,
  angariador: null, definido_por: null, definido_em: null,
};
const ANGARIADA = {
  process_id: "p1", definida: true, tipo: "angariacao",
  rotulo: "Foi angariado por um utilizador específico",
  angariador: { id: "u-dora", nome: "Dora Quintela", papel: "consultor" },
  definido_por: "Ana Diretora", definido_em: "2026-10-09T10:00:00+00:00",
};
const CANDIDATOS = {
  process_id: "p1",
  candidatos: [
    { id: "u-abel", nome: "Abel Moreira", papel: "intermediario" },
    { id: "u-dora", nome: "Dora Quintela", papel: "consultor" },
  ],
};

function montar(props = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <OrigemFinanceiraCard processId="p1" podeGerir {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getOrigemFinanceira.mockResolvedValue({ data: SEM_ORIGEM });
  api.getCandidatosOrigemFinanceira.mockResolvedValue({ data: CANDIDATOS });
});

describe("quem o vê", () => {
  it("quem não gere NÃO vê o cartão e o dado nem sequer é pedido", async () => {
    const { container } = montar({ podeGerir: false });
    expect(container).toBeEmptyDOMElement();
    // Dá tempo a um pedido indevido de acontecer antes de afirmar que não houve.
    await new Promise((r) => setTimeout(r, 30));
    expect(api.getOrigemFinanceira).not.toHaveBeenCalled();
    expect(api.getCandidatosOrigemFinanceira).not.toHaveBeenCalled();
  });

  it("a gestão vê o estado actual", async () => {
    api.getOrigemFinanceira.mockResolvedValue({ data: ANGARIADA });
    montar();
    expect(await screen.findByText("Angariado por Dora Quintela")).toBeInTheDocument();
    expect(screen.getByText(/Definida por Ana Diretora/)).toBeInTheDocument();
  });

  it("sem origem definida diz-o e oferece «Definir»", async () => {
    montar();
    expect(await screen.findByText("Ainda não definida")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Definir" })).toBeInTheDocument();
  });

  it("o motivo do servidor (403/404) aparece tal e qual", async () => {
    api.getOrigemFinanceira.mockRejectedValue({
      response: { data: { detail: "Só a empresa dona do processo pode definir a origem financeira." } },
    });
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Só a empresa dona/);
  });
});

describe("divulgação progressiva", () => {
  it("os candidatos só são pedidos quando se abre o formulário", async () => {
    montar();
    await screen.findByText("Ainda não definida");
    expect(api.getCandidatosOrigemFinanceira).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Definir" }));
    await waitFor(() => expect(api.getCandidatosOrigemFinanceira).toHaveBeenCalledWith("p1"));
  });

  it("o seletor de angariador só aparece com «angariado por»", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Definir" }));

    await userEvent.click(screen.getByRole("radio", { name: /veio diretamente/i }));
    expect(screen.queryByLabelText("Utilizador que angariou o cliente")).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: /angariado por um utilizador/i }));
    expect(await screen.findByLabelText("Utilizador que angariou o cliente")).toBeInTheDocument();
  });

  it("o formulário parte do que está gravado", async () => {
    api.getOrigemFinanceira.mockResolvedValue({ data: ANGARIADA });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Alterar" }));
    expect(screen.getByRole("radio", { name: /angariado por um utilizador/i })).toBeChecked();
  });
});

describe("guardar", () => {
  it("orgânica envia só o tipo", async () => {
    api.setOrigemFinanceira.mockResolvedValue({
      data: { ...SEM_ORIGEM, definida: true, tipo: "organica", definido_por: "Ana" },
    });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Definir" }));
    await userEvent.click(screen.getByRole("radio", { name: /veio diretamente/i }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(api.setOrigemFinanceira).toHaveBeenCalledWith("p1", { tipo: "organica" }));
    expect(await screen.findByText("Veio diretamente à empresa")).toBeInTheDocument();
  });

  it("angariação envia o id do utilizador escolhido", async () => {
    api.setOrigemFinanceira.mockResolvedValue({ data: ANGARIADA });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Definir" }));
    await userEvent.click(screen.getByRole("radio", { name: /angariado por um utilizador/i }));

    await userEvent.click(await screen.findByLabelText("Utilizador que angariou o cliente"));
    await userEvent.click(await screen.findByRole("option", { name: "Dora Quintela" }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() =>
      expect(api.setOrigemFinanceira).toHaveBeenCalledWith("p1", {
        tipo: "angariacao", angariador_id: "u-dora",
      }),
    );
    expect(await screen.findByText("Angariado por Dora Quintela")).toBeInTheDocument();
  });

  it("angariação sem angariador não chega ao servidor e diz o que falta", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Definir" }));
    await userEvent.click(screen.getByRole("radio", { name: /angariado por um utilizador/i }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/utilizador que angariou/i);
    expect(api.setOrigemFinanceira).not.toHaveBeenCalled();
  });

  it("a recusa do servidor (ex.: angariador de outra rede) fica no ecrã", async () => {
    api.getOrigemFinanceira.mockResolvedValue({ data: ANGARIADA });
    api.setOrigemFinanceira.mockRejectedValue({
      response: { data: { detail: "O utilizador que angariou o cliente não existe, está inactivo ou não pertence à sua organização." } },
    });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Alterar" }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/não pertence à sua organização/);
    // O formulário não fecha: o utilizador corrige sem perder o que escolheu.
    expect(screen.getByRole("button", { name: "Guardar" })).toBeInTheDocument();
  });

  it("cancelar volta ao estado sem gravar", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Definir" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByText("Ainda não definida")).toBeInTheDocument();
    expect(api.setOrigemFinanceira).not.toHaveBeenCalled();
  });
});
