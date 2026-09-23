/**
 * Monitor de Sinais Vitais do motor (Lote 4, ponto 14).
 *
 * O painel é READ-ONLY: o motor corre noutro processo (`powercell-worker`)
 * e um disparo a partir da web nunca lá chegaria. Um botão que não faz
 * nada é pior do que não existir.
 *
 * A asserção mais importante deste ficheiro é a que distingue
 * DESACTIVADO de EM BAIXO. Em dev quase tudo está desligado de propósito
 * (kill switches por RAM), e um painel a gritar vermelho em dev ensina
 * toda a gente a ignorá-lo — o que o tornaria inútil no dia em que
 * alguma coisa parta mesmo.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ resposta: null, erro: null }));

vi.mock("../../../services/api", () => ({
  getAutomationsEngineStatus: vi.fn(async () => {
    if (api.erro) throw api.erro;
    return { data: api.resposta };
  }),
}));

import EngineStatusPanel from "../EngineStatusPanel";

const JOB_SAUDAVEL = {
  chave: "email_auto_sync",
  nome: "Sincronização de e-mail (IMAP)",
  descricao: "Traz o correio novo das caixas configuradas.",
  processo: "web",
  interval_seconds: 60,
  activo: true,
  estado: "saudavel",
  ultima_execucao: "2026-09-23T11:59:30+00:00",
  proxima_execucao: "2026-09-23T12:00:30+00:00",
  duracao_ms: 1234,
  erro: null,
  run_count: 120,
  failure_count: 0,
  host: "web-a",
  pid: 7,
};

beforeEach(() => {
  api.erro = null;
  api.resposta = {
    jobs: [JOB_SAUDAVEL],
    resumo: { total: 1, com_problema: 0, desactivados: 0, saudaveis: 1 },
    gerado_em: "2026-09-23T12:00:00+00:00",
  };
});

afterEach(() => vi.clearAllMocks());

describe("O eletrocardiograma", () => {
  it("mostra cada job com o seu estado", async () => {
    render(<EngineStatusPanel />);
    expect(await screen.findByText("Sincronização de e-mail (IMAP)")).toBeTruthy();
    expect(screen.getByText(/saudável/i)).toBeTruthy();
  });

  it("diz em que processo o job corre", async () => {
    // Com dois processos, "está vivo?" sem dizer ONDE é meia resposta.
    render(<EngineStatusPanel />);
    await screen.findByText("Sincronização de e-mail (IMAP)");
    expect(screen.getByText(/aplicação/i)).toBeTruthy();
  });

  it("mostra a última e a próxima execução", async () => {
    render(<EngineStatusPanel />);
    await screen.findByText("Sincronização de e-mail (IMAP)");
    const linha = screen.getByTestId("engine-job-email_auto_sync");
    expect(within(linha).getByTestId("engine-last-run").textContent).toBeTruthy();
    expect(within(linha).getByTestId("engine-next-run").textContent).toBeTruthy();
  });

  it("um job desactivado NÃO aparece como avaria", async () => {
    api.resposta = {
      jobs: [{ ...JOB_SAUDAVEL, activo: false, estado: "desactivado",
               ultima_execucao: null, proxima_execucao: null }],
      resumo: { total: 1, com_problema: 0, desactivados: 1, saudaveis: 0 },
      gerado_em: "2026-09-23T12:00:00+00:00",
    };
    render(<EngineStatusPanel />);
    await screen.findByText("Sincronização de e-mail (IMAP)");
    // Na LINHA do job, não no resumo do cabeçalho — que também conta os
    // desativados e fazia a consulta encontrar dois elementos.
    const linha = screen.getByTestId("engine-job-email_auto_sync");
    expect(within(linha).getByText(/desativado/i)).toBeTruthy();
    expect(within(linha).queryByText(/falhou/i)).toBeNull();
  });

  it("um job falhado mostra o erro", async () => {
    // Sem a mensagem, o painel diz que está mau e obriga a ir aos logs —
    // que é exactamente o trabalho que ele existe para poupar.
    api.resposta = {
      jobs: [{ ...JOB_SAUDAVEL, estado: "falhou", erro: "IMAP recusou a ligação" }],
      resumo: { total: 1, com_problema: 1, desactivados: 0, saudaveis: 0 },
      gerado_em: "2026-09-23T12:00:00+00:00",
    };
    render(<EngineStatusPanel />);
    expect(await screen.findByText(/IMAP recusou a ligação/)).toBeTruthy();
  });

  it("um job que nunca correu aparece na lista", async () => {
    // O job mais avariado de todos é o que nunca arrancou; se a lista
    // viesse só dos batimentos, era o único invisível.
    api.resposta = {
      jobs: [{ ...JOB_SAUDAVEL, estado: "nunca_correu",
               ultima_execucao: null, proxima_execucao: null, run_count: 0 }],
      resumo: { total: 1, com_problema: 1, desactivados: 0, saudaveis: 0 },
      gerado_em: "2026-09-23T12:00:00+00:00",
    };
    render(<EngineStatusPanel />);
    await screen.findByText("Sincronização de e-mail (IMAP)");
    expect(screen.getByText(/nunca correu/i)).toBeTruthy();
  });

  it("sem última execução não inventa uma data", async () => {
    api.resposta = {
      jobs: [{ ...JOB_SAUDAVEL, estado: "nunca_correu",
               ultima_execucao: null, proxima_execucao: null }],
      resumo: { total: 1, com_problema: 1, desactivados: 0, saudaveis: 0 },
      gerado_em: "2026-09-23T12:00:00+00:00",
    };
    render(<EngineStatusPanel />);
    await screen.findByText("Sincronização de e-mail (IMAP)");
    const linha = screen.getByTestId("engine-job-email_auto_sync");
    expect(within(linha).getByTestId("engine-last-run").textContent).toMatch(/—|nunca/i);
  });

  it("não oferece nenhuma acção sobre o motor", async () => {
    // Read-only: o disparo teria de atravessar a fronteira de processos.
    render(<EngineStatusPanel />);
    await screen.findByText("Sincronização de e-mail (IMAP)");
    expect(screen.queryByRole("button", { name: /correr|executar|forçar/i })).toBeNull();
  });

  it("uma falha a ler o estado não deixa o painel em branco", async () => {
    api.erro = new Error("500");
    render(<EngineStatusPanel />);
    expect(await screen.findByText(/não foi possível/i)).toBeTruthy();
  });

  it("o cabeçalho resume quantos precisam de atenção", async () => {
    api.resposta = {
      jobs: [JOB_SAUDAVEL, { ...JOB_SAUDAVEL, chave: "scheduled_tasks",
                             nome: "Alertas e limpezas", estado: "atrasado" }],
      resumo: { total: 2, com_problema: 1, desactivados: 0, saudaveis: 1 },
      gerado_em: "2026-09-23T12:00:00+00:00",
    };
    render(<EngineStatusPanel />);
    await waitFor(() => expect(screen.getByTestId("engine-summary")).toBeTruthy());
    expect(screen.getByTestId("engine-summary").textContent).toMatch(/1/);
  });
});
