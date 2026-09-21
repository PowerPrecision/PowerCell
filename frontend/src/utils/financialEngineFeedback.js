/**
 * financialEngineFeedback — feedback de UX do Motor de Simulação Financeira.
 *
 * PORQUÊ: quando a Indexação é validada num processo de Crédito Habitação
 * com documentos financeiros (IRS, recibos de vencimento), o backend dispara
 * em background a extracção dos rendimentos, o cálculo do DSTI e a geração
 * da proposta com 3 cenários (`services/financial_engine.py`). A resposta do
 * `mark-indexed` / `set-indexed` traz um bloco `financial_engine` a dizer se
 * o motor arrancou.
 *
 * O utilizador já vê o toast de sucesso da indexação; este helper produz o
 * toast INFORMATIVO secundário ("Motor financeiro a processar cenários...")
 * para que ninguém fique à espera de um PDF que não sabe que está a ser
 * gerado. O acompanhamento até ao fim fica a cargo do `TasksContext` /
 * `TasksPanel`, que seguem a tarefa de background criada pelo motor.
 *
 * Helper puro (sem React, sem sonner) para ser testável com `node --test` e
 * reutilizado pelos três sítios que validam indexação: ProcessDetails,
 * ProcessesPage e o modal do Kanban.
 */

/** Id estável do toast — evita duplicados entre ecrãs/re-renders. */
export const FINANCIAL_ENGINE_TOAST_ID = "financial-engine-processing";

/** Mensagem principal do toast informativo. */
export const FINANCIAL_ENGINE_MESSAGE = "Motor financeiro a processar cenários...";

/**
 * Lê o bloco `financial_engine` de uma resposta de indexação.
 *
 * @param {object|null|undefined} responseData — corpo da resposta da API.
 * @returns {{triggered: boolean, taskId: string|null, documents: number}}
 */
export function readFinancialEngineResult(responseData) {
  const engine = responseData?.financial_engine;
  if (!engine || typeof engine !== "object") {
    return { triggered: false, taskId: null, documents: 0 };
  }
  const documents = Number(engine.documents);
  return {
    triggered: engine.triggered === true,
    taskId: engine.task_id || null,
    documents: Number.isFinite(documents) && documents > 0 ? documents : 0,
  };
}

/**
 * Constrói o toast informativo secundário, ou `null` se o motor não arrancou.
 *
 * @param {object|null|undefined} responseData — corpo da resposta da API.
 * @returns {{id: string, message: string, description: string}|null}
 */
export function buildFinancialEngineToast(responseData) {
  const { triggered, documents } = readFinancialEngineResult(responseData);
  if (!triggered) return null;

  const origem =
    documents > 0
      ? `${documents} documento${documents === 1 ? "" : "s"} financeiro${
          documents === 1 ? "" : "s"
        }`
      : "os documentos financeiros indexados";

  return {
    id: FINANCIAL_ENGINE_TOAST_ID,
    message: FINANCIAL_ENGINE_MESSAGE,
    description:
      `A analisar ${origem}. A proposta com 3 cenários de crédito ficará ` +
      "no separador Documentos quando estiver pronta — acompanhe em Tarefas.",
  };
}

/**
 * Dispara o toast informativo, se aplicável.
 *
 * @param {object|null|undefined} responseData — corpo da resposta da API.
 * @param {(message: string, options?: object) => void} notify — `toast.info`.
 * @returns {boolean} `true` se o toast foi mostrado.
 */
export function notifyFinancialEngine(responseData, notify) {
  const payload = buildFinancialEngineToast(responseData);
  if (!payload || typeof notify !== "function") return false;
  notify(payload.message, { id: payload.id, description: payload.description });
  return true;
}
