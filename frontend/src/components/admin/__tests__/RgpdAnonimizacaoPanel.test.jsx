/**
 * O painel de anonimização RGPD. O servidor valida a password (e o âmbito); aqui prova-se o ecrã:
 * nenhum pedido destrutivo sai sem passar pelo diálogo, o lote é do Master e vem depois de uma
 * simulação, e cada recusa se diz no sítio.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getGdprStatistics: vi.fn(),
  getGdprEligible: vi.fn(),
  anonymizeData: vi.fn(),
  runGdprBatch: vi.fn(),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("sonner", () => ({ toast }));

import RgpdAnonimizacaoPanel, { tamanhoDoLoteValido } from "../RgpdAnonimizacaoPanel";
import * as api from "../../../services/api";

// Valores DIFERENTES das omissões (zero/«—»), senão um erro de leitura passava despercebido.
const STATS = { total_processes: 321, anonymized_processes: 17, eligible_for_anonymization: 9, retention_period_days: 1825 };
const PROCESSOS = [
  { id: "p1", client_name: "Ana Martins", status: "concluido", updated_at: "2019-03-04T10:00:00Z" },
  { id: "p2", client_name: "Rui Pereira", status: "cancelado", updated_at: "2018-11-30T09:00:00Z" },
];
const erro = (status, detail) => Object.assign(new Error("x"), { response: { status, data: { detail } } });

function montar(props = { isMaster: true }, processos = PROCESSOS) {
  api.getGdprStatistics.mockResolvedValue({ data: { success: true, data: STATS } });
  api.getGdprEligible.mockResolvedValue({ data: { success: true, count: processos.length, processes: processos } });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <RgpdAnonimizacaoPanel {...props} />
    </QueryClientProvider>,
  );
}

const campoPassword = () => screen.findByLabelText(/a sua password actual/i);

describe("RgpdAnonimizacaoPanel — leitura", () => {
  beforeEach(() => vi.clearAllMocks());

  it("mostra as estatísticas e a lista de elegíveis", async () => {
    montar();
    const stats = await screen.findByTestId("rgpd-estatisticas");
    await waitFor(() => expect(stats).toHaveTextContent("321"));
    expect(stats).toHaveTextContent("17");
    expect(stats).toHaveTextContent("1825");
    expect(await screen.findByText("Ana Martins")).toBeTruthy();
    expect(screen.getByText("Rui Pereira")).toBeTruthy();
  });

  it("sem elegíveis di-lo, em vez de uma tabela vazia", async () => {
    montar({ isMaster: true }, []);
    expect(await screen.findByTestId("rgpd-sem-elegiveis")).toBeTruthy();
  });

  it("uma lista que não é lista (forma errada do servidor) não rebenta o ecrã", async () => {
    api.getGdprStatistics.mockResolvedValue({ data: { data: STATS } });
    api.getGdprEligible.mockResolvedValue({ data: { processes: { a: 1 } } });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><RgpdAnonimizacaoPanel isMaster /></QueryClientProvider>);
    expect(await screen.findByTestId("rgpd-sem-elegiveis")).toBeTruthy();
  });

  it("um erro de leitura diz-se (e não parece «não há nada»)", async () => {
    api.getGdprStatistics.mockRejectedValue(erro(500));
    api.getGdprEligible.mockRejectedValue(erro(500));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><RgpdAnonimizacaoPanel isMaster /></QueryClientProvider>);
    expect(await screen.findByTestId("rgpd-elegiveis-erro")).toBeTruthy();
    expect(screen.getByTestId("rgpd-estatisticas-erro")).toBeTruthy();
    expect(screen.queryByTestId("rgpd-sem-elegiveis")).toBeNull();
  });

  it("só o Master vê o lote", async () => {
    const { unmount } = montar({ isMaster: true });
    expect(await screen.findByTestId("rgpd-lote")).toBeTruthy();
    unmount();
    montar({ isMaster: false });
    await screen.findByText("Ana Martins");
    expect(screen.queryByTestId("rgpd-lote")).toBeNull();
    expect(screen.queryByTestId("rgpd-anonimizar-lote")).toBeNull();
  });
});

describe("RgpdAnonimizacaoPanel — anonimizar UM processo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.anonymizeData.mockResolvedValue({ data: { success: true } });
  });

  it("clicar não envia nada: abre o diálogo e o pedido só sai com a password", async () => {
    const user = userEvent.setup();
    montar({ isMaster: false });
    await user.click(await screen.findByTestId("rgpd-anonimizar-p1"));

    expect(await screen.findByTestId("anonimizar-processo-dialog")).toHaveTextContent("Ana Martins");
    expect(api.anonymizeData).not.toHaveBeenCalled();

    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("anonimizar-processo-confirmar"));

    await waitFor(() => expect(api.anonymizeData).toHaveBeenCalledTimes(1));
    expect(api.anonymizeData).toHaveBeenCalledWith({ process_id: "p1", dry_run: false, password: "Segredo-1!" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Processo anonimizado."));
    await waitFor(() => expect(screen.queryByTestId("anonimizar-processo-dialog")).toBeNull());
  });

  it("depois de anonimizar a lista e as estatísticas voltam a ser pedidas", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("rgpd-anonimizar-p2"));
    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("anonimizar-processo-confirmar"));
    await waitFor(() => expect(api.getGdprEligible.mock.calls.length).toBeGreaterThan(1));
    expect(api.getGdprStatistics.mock.calls.length).toBeGreaterThan(1);
  });

  it("password errada: o erro diz-se no diálogo, nada fecha e nada é anunciado como feito", async () => {
    const user = userEvent.setup();
    api.anonymizeData.mockRejectedValue(erro(403, "Password incorrecta."));
    montar();
    await user.click(await screen.findByTestId("rgpd-anonimizar-p1"));
    await user.type(await campoPassword(), "errada");
    await user.click(screen.getByTestId("anonimizar-processo-confirmar"));

    const alerta = await screen.findByTestId("anonimizar-processo-erro");
    expect(alerta).toHaveAttribute("data-tipo", "password_errada");
    expect(screen.getByTestId("anonimizar-processo-dialog")).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("processo fora da rede (404) diz-o com o texto desta acção", async () => {
    const user = userEvent.setup();
    api.anonymizeData.mockRejectedValue(erro(404, undefined));
    montar();
    await user.click(await screen.findByTestId("rgpd-anonimizar-p1"));
    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("anonimizar-processo-confirmar"));
    expect(await screen.findByTestId("anonimizar-processo-erro")).toHaveTextContent(/já não existe ou não pertence/i);
  });

  it("cancelar não envia nada", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("rgpd-anonimizar-p1"));
    const dialogo = await screen.findByTestId("anonimizar-processo-dialog");
    await user.click(within(dialogo).getByRole("button", { name: /cancelar/i }));
    expect(api.anonymizeData).not.toHaveBeenCalled();
  });
});

describe("RgpdAnonimizacaoPanel — o lote (Master)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.runGdprBatch.mockResolvedValue({ data: { success: true, processed: 12, succeeded: 11 } });
  });

  it("o botão do lote está desligado até haver uma simulação", async () => {
    montar();
    expect(await screen.findByTestId("rgpd-anonimizar-lote")).toBeDisabled();
  });

  it("a simulação não pede password, não altera nada e mostra os números", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("rgpd-simular-lote"));

    expect(api.runGdprBatch).toHaveBeenCalledTimes(1);
    expect(api.runGdprBatch).toHaveBeenCalledWith({ dry_run: true, batch_size: 100 });
    const texto = await screen.findByTestId("rgpd-simulacao");
    expect(texto).toHaveTextContent("12");
    expect(texto).toHaveTextContent("11");
    expect(texto).toHaveTextContent(/nada foi alterado/i);
    expect(screen.queryByTestId("anonimizar-lote-dialog")).toBeNull();
    expect(screen.getByTestId("rgpd-anonimizar-lote")).toBeEnabled();
  });

  it("alterar o tamanho invalida a simulação (o lote tem de ser o simulado)", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("rgpd-simular-lote"));
    await screen.findByTestId("rgpd-simulacao");

    const campo = screen.getByTestId("rgpd-tamanho-do-lote");
    await user.clear(campo);
    await user.type(campo, "250");
    expect(screen.queryByTestId("rgpd-simulacao")).toBeNull();
    expect(screen.getByTestId("rgpd-anonimizar-lote")).toBeDisabled();
  });

  it("um tamanho inválido desliga a simulação e o lote", async () => {
    const user = userEvent.setup();
    montar();
    const campo = await screen.findByTestId("rgpd-tamanho-do-lote");
    await user.clear(campo);
    await user.type(campo, "0");
    expect(screen.getByTestId("rgpd-simular-lote")).toBeDisabled();
    expect(screen.getByTestId("rgpd-anonimizar-lote")).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/entre 1 e 500/);
  });

  it("anonimizar em lote: só o diálogo envia, com a password e o tamanho SIMULADO", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("rgpd-simular-lote"));
    await screen.findByTestId("rgpd-simulacao");
    api.runGdprBatch.mockClear();

    await user.click(screen.getByTestId("rgpd-anonimizar-lote"));
    expect(await screen.findByTestId("anonimizar-lote-dialog")).toHaveTextContent("100");
    expect(api.runGdprBatch).not.toHaveBeenCalled();

    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("anonimizar-lote-confirmar"));

    await waitFor(() => expect(api.runGdprBatch).toHaveBeenCalledTimes(1));
    expect(api.runGdprBatch).toHaveBeenCalledWith({ dry_run: false, batch_size: 100, password: "Segredo-1!" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("11")));
    // Depois de executar a simulação já não vale: obriga a simular outra vez.
    await waitFor(() => expect(screen.getByTestId("rgpd-anonimizar-lote")).toBeDisabled());
  });

  it("um tamanho diferente do omisso viaja na simulação E no lote (o simulado é o executado)", async () => {
    const user = userEvent.setup();
    montar();
    const campo = await screen.findByTestId("rgpd-tamanho-do-lote");
    await user.clear(campo);
    await user.type(campo, "250");
    await user.click(screen.getByTestId("rgpd-simular-lote"));
    await screen.findByTestId("rgpd-simulacao");
    expect(api.runGdprBatch).toHaveBeenLastCalledWith({ dry_run: true, batch_size: 250 });

    await user.click(screen.getByTestId("rgpd-anonimizar-lote"));
    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("anonimizar-lote-confirmar"));
    await waitFor(() => expect(api.runGdprBatch).toHaveBeenLastCalledWith({ dry_run: false, batch_size: 250, password: "Segredo-1!" }));
  });

  it("password errada no lote: erro no diálogo, nada anunciado", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("rgpd-simular-lote"));
    await screen.findByTestId("rgpd-simulacao");
    api.runGdprBatch.mockRejectedValueOnce(erro(403, "Password incorrecta."));

    await user.click(screen.getByTestId("rgpd-anonimizar-lote"));
    await user.type(await campoPassword(), "errada");
    await user.click(screen.getByTestId("anonimizar-lote-confirmar"));

    expect(await screen.findByTestId("anonimizar-lote-erro")).toHaveAttribute("data-tipo", "password_errada");
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("falha na simulação diz-se num toast e não deixa números", async () => {
    const user = userEvent.setup();
    api.runGdprBatch.mockRejectedValue(erro(500, "boom"));
    montar();
    await user.click(await screen.findByTestId("rgpd-simular-lote"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByTestId("rgpd-simulacao")).toBeNull();
  });
});

describe("tamanhoDoLoteValido", () => {
  it.each([["1", 1], ["100", 100], ["500", 500], [" 25 ", 25]])("%j → %j", (entrada, esperado) => {
    expect(tamanhoDoLoteValido(entrada)).toBe(esperado);
  });
  it.each(["", "0", "-3", "501", "abc", null, undefined, "1e3", "12abc", "1.5"])("%j → null", (entrada) => {
    expect(tamanhoDoLoteValido(entrada)).toBeNull();
  });
});
