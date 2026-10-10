/**
 * «Serviço do parceiro» — o cartão da equipa interna (o parceiro nunca o vê).
 * As respostas são as FIXTURES geradas pelo servidor, com valores diferentes
 * das omissões (nota com quebra de linha, «Ana», data fixa).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import servicoPago from "@/test/fixtures/parceiro/servico_pago.json";
import servicoPorPagar from "@/test/fixtures/parceiro/servico_por_pagar.json";

const api = vi.hoisted(() => ({ getServicoDoParceiro: vi.fn(), setServicoDoParceiro: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast }));

import ServicoDoParceiroCard from "../ServicoDoParceiroCard";

const montar = (props = {}) => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ServicoDoParceiroCard processId="a-novo" podeVer {...props} />
    </QueryClientProvider>
  );
};

const caixa = () => screen.findByRole("checkbox", { name: "Serviço pago pelo parceiro" });

describe("ServicoDoParceiroCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getServicoDoParceiro.mockResolvedValue({ data: servicoPorPagar });
    api.setServicoDoParceiro.mockResolvedValue({ data: servicoPago });
  });

  it("quem não vê não desenha nada E não pede nada ao servidor", async () => {
    const { container } = montar({ podeVer: false });
    expect(container.firstChild).toBeNull();
    await new Promise((r) => setTimeout(r, 20));
    expect(api.getServicoDoParceiro).not.toHaveBeenCalled();
  });

  it("mostra o estado gravado: caixa, observações, parceiro e quem marcou", async () => {
    api.getServicoDoParceiro.mockResolvedValue({ data: servicoPago });
    montar();
    expect(await caixa()).toBeChecked();
    expect(screen.getByLabelText("Observações")).toHaveValue("Transferência de 14/10\nRef. 8841");
    expect(screen.getByText(/Parceiro: Rui/)).toBeInTheDocument();
    expect(screen.getByText(/Marcado em/)).toBeInTheDocument();
    expect(api.getServicoDoParceiro).toHaveBeenCalledWith("a-novo");
  });

  it("sem parceiro (`aplicavel: false`) o cartão desaparece", async () => {
    api.getServicoDoParceiro.mockResolvedValue({ data: { ...servicoPorPagar, aplicavel: false } });
    montar();
    await waitFor(() => expect(screen.queryByTestId("cartao-servico-do-parceiro")).toBeNull());
  });

  it("marcar a caixa envia SÓ `pago`, mostra o resultado e avisa", async () => {
    montar();
    await userEvent.click(await caixa());
    await waitFor(() => expect(api.setServicoDoParceiro).toHaveBeenCalledWith("a-novo", { pago: true }));
    expect(await screen.findByRole("checkbox", { name: "Serviço pago pelo parceiro" })).toBeChecked();
    expect(toast.success).toHaveBeenCalled();
  });

  it("as observações só pedem «Guardar» quando mudam, e enviam SÓ `observacoes`", async () => {
    montar();
    await caixa();
    expect(screen.queryByRole("button", { name: "Guardar observações" })).toBeNull();
    await userEvent.type(screen.getByLabelText("Observações"), "Pago por MB");
    await userEvent.click(screen.getByRole("button", { name: "Guardar observações" }));
    await waitFor(() => expect(api.setServicoDoParceiro).toHaveBeenCalledWith("a-novo", { observacoes: "Pago por MB" }));
  });

  it("quem vê mas não altera tem os controlos desactivados e sem «Guardar»", async () => {
    api.getServicoDoParceiro.mockResolvedValue({ data: { ...servicoPago, pode_alterar: false } });
    montar();
    expect(await caixa()).toBeDisabled();
    expect(screen.getByLabelText("Observações")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Guardar observações" })).toBeNull();
  });

  it("um erro do servidor ao guardar aparece no cartão e a caixa não muda", async () => {
    api.setServicoDoParceiro.mockRejectedValue({ response: { data: { detail: "Sem permissão para alterar." } } });
    montar();
    await userEvent.click(await caixa());
    expect(await screen.findByRole("alert")).toHaveTextContent("Sem permissão para alterar.");
    expect(screen.getByRole("checkbox", { name: "Serviço pago pelo parceiro" })).not.toBeChecked();
  });

  it("um erro de LEITURA diz-se (não finge «por pagar»)", async () => {
    api.getServicoDoParceiro.mockRejectedValue({ response: { data: { detail: "Processo não encontrado." } } });
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent("Processo não encontrado.");
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("não há valores nem comissões: é uma caixa e um texto", async () => {
    montar();
    await caixa();
    expect(screen.getByTestId("cartao-servico-do-parceiro").textContent).not.toMatch(/comiss|€|eur\b|valor/i);
    expect(screen.getByText(/O parceiro não vê este cartão/)).toBeInTheDocument();
  });
});
