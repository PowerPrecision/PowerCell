/**
 * «Log da IA» — o separador monta a SÉRIO (query real, TanStack real) sobre a forma REAL do servidor.
 *
 * Os valores do fixture são diferentes das omissões de propósito: um erro de leitura (chave errada,
 * `|| []`) seria indistinguível de uma leitura certa com valores iguais às omissões.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getProcessAiLog: vi.fn(),
  analyzeDocumentForReview: vi.fn(),
}));
vi.mock("../../../../services/api", () => api);

const toastas = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastas }));

import AiLogTab from "../AiLogTab";

const LINHAS = [
  {
    id: "l-1", accao: "categorizar", accao_rotulo: "Documento classificado", estado: "sucesso",
    gatilho: "automatico", origem: "portal", ficheiro: "cartao-cidadao.pdf", documento_id: "d-1",
    motivo: "sem_contexto", motivo_mensagem: "Sem texto extraível: só foi possível usar o nome do ficheiro.",
    categoria: "Identificação", campos: ["nif", "morada"], confianca: 0.87,
    utilizador_nome: null, created_at: "2026-10-21T13:07:00+00:00",
  },
  {
    id: "l-2", accao: "categorizar", accao_rotulo: "Documento classificado", estado: "falha",
    gatilho: "automatico", origem: "parceiro", ficheiro: "irs-2025.pdf", documento_id: null,
    motivo: "ia_nao_configurada", motivo_mensagem: "O serviço de IA não está configurado ou recusou as credenciais.",
    categoria: null, campos: [], confianca: null, utilizador_nome: null, created_at: "2026-10-21T12:00:00+00:00",
  },
  {
    id: "l-3", accao: "analisar", accao_rotulo: "Documento analisado", estado: "saltado",
    gatilho: "manual", origem: null, ficheiro: "recibo.pdf", documento_id: null,
    motivo: "ja_analisado", motivo_mensagem: "Já tinha sido analisado pela IA — não foi chamada outra vez.",
    categoria: null, campos: [], confianca: null, utilizador_nome: "Diana Diretora",
    created_at: "2026-10-20T09:30:00+00:00",
  },
];

const pagina = (extra = {}) => ({
  data: { items: LINHAS, total: 3, page: 1, size: 30, pode_reanalisar: true, ...extra },
});

function montar(props = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onReanalisado = vi.fn();
  const vista = render(
    <QueryClientProvider client={queryClient}>
      <AiLogTab processId="proc-7" effectiveRole="diretor" onReanalisado={onReanalisado} {...props} />
    </QueryClientProvider>,
  );
  return { ...vista, onReanalisado, queryClient };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getProcessAiLog.mockResolvedValue(pagina());
  api.analyzeDocumentForReview.mockResolvedValue({
    data: { success: true, auto_approved: false, confidence_score: 61 },
  });
});

describe("a timeline", () => {
  it("lista as acções com estado, conclusão, campos, quando e quem", async () => {
    montar();
    const linhas = await screen.findAllByTestId("linha-do-log");
    expect(linhas).toHaveLength(3);

    const primeira = within(linhas[0]);
    expect(primeira.getByText("Documento classificado — cartao-cidadao.pdf")).toBeInTheDocument();
    expect(primeira.getByText("Sucesso")).toBeInTheDocument();
    expect(primeira.getByText("Identificação · 87 %")).toBeInTheDocument();
    expect(primeira.getByText(/Campos lidos: nif, morada/)).toBeInTheDocument();
    expect(primeira.getByText(/Sem texto extraível/)).toBeInTheDocument();
    expect(primeira.getByText(/Automático \(Portal do cliente\)/)).toBeInTheDocument();

    expect(within(linhas[2]).getByText(/Manual — Diana Diretora/)).toBeInTheDocument();
    expect(within(linhas[2]).getByText("Não executada")).toBeInTheDocument();
  });

  it("a falha diz o porquê em português e nunca mostra o código interno", async () => {
    montar();
    const falha = (await screen.findAllByTestId("linha-do-log"))[1];
    expect(within(falha).getByText("Falhou")).toBeInTheDocument();
    expect(within(falha).getByText(/não está configurado ou recusou as credenciais/)).toBeInTheDocument();
    expect(screen.queryByText(/ia_nao_configurada/)).not.toBeInTheDocument();
  });

  it("pede o log do processo certo", async () => {
    montar();
    await screen.findAllByTestId("linha-do-log");
    expect(api.getProcessAiLog).toHaveBeenCalledWith("proc-7", { page: 1, size: 30 });
  });

  it("sem acções, explica o que vai aparecer (não é um erro)", async () => {
    api.getProcessAiLog.mockResolvedValue({ data: { items: [], total: 0, page: 1, size: 30, pode_reanalisar: true } });
    montar();
    expect(await screen.findByTestId("log-da-ia-vazio")).toHaveTextContent(/ainda não registou/i);
  });

  it("um erro de leitura NÃO se apresenta como «sem acções» e deixa tentar de novo", async () => {
    api.getProcessAiLog.mockRejectedValueOnce(new Error("rede"));
    const utilizador = userEvent.setup();
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Não foi possível carregar/);
    expect(screen.queryByTestId("log-da-ia-vazio")).not.toBeInTheDocument();

    await utilizador.click(screen.getByRole("button", { name: /Tentar de novo/i }));
    expect(await screen.findAllByTestId("linha-do-log")).toHaveLength(3);
  });

  it("uma resposta fora da forma não rebenta o ecrã", async () => {
    api.getProcessAiLog.mockResolvedValue({ data: { items: { 0: "x" }, total: "muitos" } });
    montar();
    expect(await screen.findByTestId("log-da-ia-vazio")).toBeInTheDocument();
  });
});

describe("filtros e páginas", () => {
  it("filtrar por estado pede ao servidor e volta à página 1", async () => {
    api.getProcessAiLog.mockResolvedValue(pagina({ total: 90 }));
    const utilizador = userEvent.setup();
    montar();
    await screen.findAllByTestId("linha-do-log");

    await utilizador.click(screen.getByRole("button", { name: /Seguinte/i }));
    await waitFor(() => expect(api.getProcessAiLog).toHaveBeenLastCalledWith("proc-7", { page: 2, size: 30 }));

    await utilizador.click(screen.getByRole("button", { name: "Falhas" }));
    await waitFor(() =>
      expect(api.getProcessAiLog).toHaveBeenLastCalledWith("proc-7", { page: 1, size: 30, estado: "falha" }),
    );
    expect(screen.getByRole("button", { name: "Falhas" })).toHaveAttribute("aria-pressed", "true");
  });

  it("filtrar logo da primeira página também pede ao servidor (o filtro faz parte da chave de cache)", async () => {
    // Sem mudar de página antes: uma chave que só levasse a página ficava igual e servia a cache.
    const utilizador = userEvent.setup();
    montar();
    await screen.findAllByTestId("linha-do-log");

    await utilizador.click(screen.getByRole("button", { name: "Falhas" }));

    await waitFor(() =>
      expect(api.getProcessAiLog).toHaveBeenLastCalledWith("proc-7", { page: 1, size: 30, estado: "falha" }),
    );
  });

  it("mostra a página e o total", async () => {
    api.getProcessAiLog.mockResolvedValue(pagina({ total: 61, page: 1 }));
    montar();
    expect(await screen.findByText(/Página 1 de 3 · 61 acções/)).toBeInTheDocument();
  });

  it("com uma só página não há paginação", async () => {
    montar();
    await screen.findAllByTestId("linha-do-log");
    expect(screen.queryByRole("button", { name: /Seguinte/i })).not.toBeInTheDocument();
  });
});

describe("Reanalisar — quem vê o botão", () => {
  const botoes = () => screen.queryAllByRole("button", { name: /^Reanalisar/ });

  it("a gestão vê-o SÓ nas linhas com documento a que se pode voltar", async () => {
    montar();
    await screen.findAllByTestId("linha-do-log");
    // l-1 (categorizar, documento d-1): sim. l-2 (sem documento) e l-3 (análise em lote): não.
    expect(botoes()).toHaveLength(1);
    expect(botoes()[0]).toHaveAccessibleName("Reanalisar cartao-cidadao.pdf com IA");
  });

  it.each(["consultor", "intermediario", "administrativo", "indexacao"])(
    "o perfil %s vê o log mas NÃO o botão, mesmo que o servidor diga que sim",
    async (papel) => {
      montar({ effectiveRole: papel });
      await screen.findAllByTestId("linha-do-log");
      expect(botoes()).toHaveLength(0);
    },
  );

  it("se o servidor diz que não (processo fora do âmbito), não há botão — nem para a gestão", async () => {
    api.getProcessAiLog.mockResolvedValue(pagina({ pode_reanalisar: false }));
    montar();
    await screen.findAllByTestId("linha-do-log");
    expect(botoes()).toHaveLength(0);
  });

  it("um campo em falta NUNCA abre o botão (falha fechado)", async () => {
    api.getProcessAiLog.mockResolvedValue({ data: { items: LINHAS, total: 3, page: 1, size: 30 } });
    montar();
    await screen.findAllByTestId("linha-do-log");
    expect(botoes()).toHaveLength(0);
  });

  it("num processo fechado não há botão", async () => {
    montar({ processoFechado: true });
    await screen.findAllByTestId("linha-do-log");
    expect(botoes()).toHaveLength(0);
  });
});

describe("Reanalisar — a acção", () => {
  it("chama a revisão com o id do documento, avisa e refaz o log e os documentos", async () => {
    const utilizador = userEvent.setup();
    const { onReanalisado } = montar();
    await screen.findAllByTestId("linha-do-log");
    const antes = api.getProcessAiLog.mock.calls.length;

    await utilizador.click(screen.getByRole("button", { name: /^Reanalisar/ }));

    await waitFor(() => expect(api.analyzeDocumentForReview).toHaveBeenCalledWith("d-1"));
    await waitFor(() => expect(toastas.info).toHaveBeenCalledWith(expect.stringContaining("aguardam a sua revisão")));
    expect(onReanalisado).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(api.getProcessAiLog.mock.calls.length).toBeGreaterThan(antes));
  });

  it("se a IA falhar, diz-o e continua a refazer o log (a falha também fica registada)", async () => {
    api.analyzeDocumentForReview.mockResolvedValue({ data: { success: false, error: "Incorrect API key sk-xyz" } });
    const utilizador = userEvent.setup();
    montar();
    await screen.findAllByTestId("linha-do-log");
    const antes = api.getProcessAiLog.mock.calls.length;

    await utilizador.click(screen.getByRole("button", { name: /^Reanalisar/ }));

    await waitFor(() => expect(toastas.error).toHaveBeenCalled());
    expect(toastas.error.mock.calls[0][0]).not.toContain("sk-xyz");
    await waitFor(() => expect(api.getProcessAiLog.mock.calls.length).toBeGreaterThan(antes));
  });

  it("um pedido recusado (403/rede) avisa e não deixa o botão preso", async () => {
    api.analyzeDocumentForReview.mockRejectedValue({ response: { status: 403 } });
    const utilizador = userEvent.setup();
    montar();
    await screen.findAllByTestId("linha-do-log");

    await utilizador.click(screen.getByRole("button", { name: /^Reanalisar/ }));

    await waitFor(() => expect(toastas.error).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: /^Reanalisar/ })).toBeEnabled());
  });
});
