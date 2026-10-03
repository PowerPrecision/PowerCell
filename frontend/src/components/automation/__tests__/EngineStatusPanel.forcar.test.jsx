/**
 * «Forçar Execução» no painel «Estado do Motor» (Lote 2, ponto 1).
 *
 * A OBJECÇÃO ORIGINAL ESTAVA CERTA
 * O painel era read-only e dizia porquê: «o motor corre noutro processo
 * (`powercell-worker`) e um disparo a partir da web nunca lá chegaria; um
 * botão que não faz nada é pior do que não existir».
 *
 * A fila persistente é a RESPOSTA a essa objecção, não a sua negação:
 * um job da Aplicação corre no processo que serve o pedido, um job do
 * Processador fica como PEDIDO que o worker reclama no ciclo seguinte.
 *
 * O QUE ESTES TESTES PROTEGEM
 * 1. **A UI distingue «correu» de «pedido entregue».** Dar o segundo pelo
 *    primeiro é o botão a mentir — exactamente o que a objecção queria
 *    evitar. A mensagem vem do SERVIDOR, que é quem sabe em que processo
 *    vive cada job; escrevê-la aqui era uma segunda cópia dessa regra.
 * 2. **Quem pode ser forçado é decisão do servidor** (`pode_forcar`). Uma
 *    lista no frontend divergiria da dele sem dar erro.
 * 3. **Um pedido pendente é o DIAGNÓSTICO**, e tem de aparecer: é o que
 *    transforma «Nunca correu» em "o Processador não está a consumir".
 * 4. **Um botão só desativa o seu próprio job.** Com um booleano em vez da
 *    chave, clicar num job desativava o botão de todos.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  resposta: null,
  respostaDoForcar: null,
  erroDoForcar: null,
  chamadas: [],
}));

vi.mock("../../../services/api", () => ({
  getAutomationsEngineStatus: vi.fn(async () => ({ data: api.resposta })),
  forcarExecucaoDeAutomatismo: vi.fn(async (chave) => {
    api.chamadas.push(chave);
    if (api.erroDoForcar) throw api.erroDoForcar;
    return { data: api.respostaDoForcar };
  }),
}));

const toastSpy = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastSpy }));

import EngineStatusPanel, { descreverPedido } from "../EngineStatusPanel";

const JOB_DO_WORKER = {
  chave: "lead_matching",
  nome: "Cruzamento automático de leads",
  descricao: "Procura imóveis compatíveis.",
  processo: "worker",
  interval_seconds: 1800,
  activo: true,
  estado: "nunca_correu",
  ultima_execucao: null,
  proxima_execucao: null,
  duracao_ms: null,
  erro: null,
  run_count: 0,
  failure_count: 0,
  pode_forcar: true,
  motivo_sem_forcar: "",
  pedido_pendente: null,
};

const JOB_DA_APLICACAO = {
  ...JOB_DO_WORKER,
  chave: "background_job_monitor",
  nome: "Monitor de tarefas bloqueadas",
  processo: "web",
  estado: "saudavel",
};

function responder(jobs) {
  api.resposta = {
    jobs,
    resumo: { total: jobs.length, com_problema: 0, desactivados: 0, saudaveis: jobs.length },
    fila: { pendente: 0, a_processar: 0, concluida: 0, falhada: 0 },
    gerado_em: "2026-10-02T12:00:00+00:00",
  };
}

beforeEach(() => {
  api.chamadas = [];
  api.erroDoForcar = null;
  api.respostaDoForcar = { success: true, modo: "executado_agora", mensagem: "«X» correu agora." };
  responder([JOB_DO_WORKER]);
});

afterEach(() => vi.clearAllMocks());

describe("A frase do pedido", () => {
  it("um pedido PENDENTE explica o que isso significa", () => {
    // É esta frase que transforma «Nunca correu» num diagnóstico.
    const texto = descreverPedido({ estado: "pendente" });
    expect(texto).toMatch(/à espera do Processador/i);
    expect(texto).toMatch(/não está a consumir/i);
  });

  it("um pedido falhado mostra o erro", () => {
    expect(descreverPedido({ estado: "falhada", erro: "IMAP recusou" })).toMatch(/IMAP recusou/);
  });

  it("sem pedido não inventa frase nenhuma", () => {
    // Uma linha de texto sempre presente lê-se como estado permanente.
    expect(descreverPedido(null)).toBe("");
    expect(descreverPedido(undefined)).toBe("");
  });

  it("um estado desconhecido não produz texto a meio", () => {
    expect(descreverPedido({ estado: "qualquer_coisa" })).toBe("");
  });
});

describe("O botão de forçar", () => {
  it("aparece quando o servidor autoriza", async () => {
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    expect(screen.getByRole("button", { name: /forçar execução/i })).toBeTruthy();
  });

  it("chama o endpoint com a chave do job", async () => {
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    await userEvent.click(screen.getByRole("button", { name: /forçar execução/i }));
    await waitFor(() => expect(api.chamadas).toEqual(["lead_matching"]));
  });

  it("mostra a mensagem DO SERVIDOR e não uma escrita aqui", async () => {
    // O servidor é quem sabe se o job correu ou se ficou um pedido; a UI
    // não tem de saber em que processo vive cada job.
    api.respostaDoForcar = {
      success: true,
      modo: "pedido_ao_worker",
      mensagem: "Pedido entregue ao Processador. «Cruzamento» arranca no próximo ciclo.",
    };
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    await userEvent.click(screen.getByRole("button", { name: /forçar execução/i }));
    await waitFor(() =>
      expect(toastSpy.success).toHaveBeenCalledWith(
        expect.stringContaining("Pedido entregue ao Processador"),
      ),
    );
  });

  it("não anuncia «correu» a um pedido que só foi entregue", async () => {
    api.respostaDoForcar = {
      success: true,
      modo: "pedido_ao_worker",
      mensagem: "Pedido entregue ao Processador.",
    };
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    await userEvent.click(screen.getByRole("button", { name: /forçar execução/i }));
    await waitFor(() => expect(toastSpy.success).toHaveBeenCalled());
    const [mensagem] = toastSpy.success.mock.calls[0];
    expect(mensagem).not.toMatch(/correu/i);
  });

  it("recarrega o estado depois de forçar", async () => {
    // Sem isto, o painel continuava a dizer «Nunca correu» a seguir ao
    // clique e o utilizador concluía que o botão não faz nada.
    const { getAutomationsEngineStatus } = await import("../../../services/api");
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    const antes = getAutomationsEngineStatus.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /forçar execução/i }));
    await waitFor(() =>
      expect(getAutomationsEngineStatus.mock.calls.length).toBeGreaterThan(antes),
    );
  });

  it("recarrega mesmo quando o pedido FALHA", async () => {
    // Um pedido registado antes da falha continua a ser informação.
    const { getAutomationsEngineStatus } = await import("../../../services/api");
    api.erroDoForcar = new Error("503");
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    const antes = getAutomationsEngineStatus.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /forçar execução/i }));
    await waitFor(() =>
      expect(getAutomationsEngineStatus.mock.calls.length).toBeGreaterThan(antes),
    );
  });

  it("uma falha não deixa o botão preso a carregar", async () => {
    api.erroDoForcar = new Error("503");
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    const botao = screen.getByRole("button", { name: /forçar execução/i });
    await userEvent.click(botao);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /forçar execução/i }).disabled).toBe(false),
    );
  });
});

describe("Cada botão é só o seu", () => {
  it("clicar num job não desativa o botão do outro", async () => {
    // Com um booleano em vez da chave, clicar num job desativava TODOS.
    responder([JOB_DO_WORKER, JOB_DA_APLICACAO]);
    let resolver;
    const { forcarExecucaoDeAutomatismo } = await import("../../../services/api");
    forcarExecucaoDeAutomatismo.mockImplementationOnce(
      () => new Promise((r) => { resolver = () => r({ data: api.respostaDoForcar }); }),
    );

    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");

    const linhaWorker = screen.getByTestId("engine-job-lead_matching");
    const linhaWeb = screen.getByTestId("engine-job-background_job_monitor");

    await userEvent.click(within(linhaWorker).getByRole("button", { name: /forçar/i }));

    await waitFor(() =>
      expect(within(linhaWorker).getByRole("button", { name: /forçar/i }).disabled).toBe(true),
    );
    expect(within(linhaWeb).getByRole("button", { name: /forçar/i }).disabled).toBe(false);

    // Resolver e esperar que o estado assente: deixar a promessa pendente no
    // fim do teste produz avisos de `act(...)` que mandam procurar no sítio
    // errado no próximo teste que falhe.
    resolver();
    await waitFor(() =>
      expect(within(linhaWorker).getByRole("button", { name: /forçar/i }).disabled).toBe(false),
    );
  });
});

describe("O pedido pendente no ecrã", () => {
  it("é mostrado na linha do job", async () => {
    responder([{ ...JOB_DO_WORKER, pedido_pendente: { estado: "pendente", pedido_em: "2026-10-02T11:00:00+00:00" } }]);
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    const linha = screen.getByTestId("engine-job-lead_matching");
    expect(within(linha).getByTestId("engine-pedido-lead_matching").textContent).toMatch(
      /à espera do Processador/i,
    );
  });

  it("sem pedido não desenha linha nenhuma", async () => {
    render(<EngineStatusPanel />);
    await screen.findByText("Cruzamento automático de leads");
    expect(screen.queryByTestId("engine-pedido-lead_matching")).toBeNull();
  });
});
