/**
 * workflowStatuses — helpers para os estados do workflow de processos.
 *
 * PACOTE 11 (Eixo 1 — Strict No-Hardcoding): a lista estática
 * KNOWN_PROCESS_STATUSES (~40 fases cravadas em código) foi REMOVIDA.
 * As fases do Kanban e das dropdowns são geradas 100% DINAMICAMENTE a
 * partir da API /admin/workflow-statuses (colecção `workflow_statuses`,
 * configurável pelo admin) — a mesma fonte de verdade do board.
 *
 * Garantia de UX: a dropdown nunca fica em branco quando existe um
 * `status` actual — se o valor não vier na lista dinâmica (API falhou
 * ou coleção sem seed), o `currentStatus` é injectado como opção extra
 * com label formatada. Não há fallback hardcoded de fases.
 *
 * @module utils/workflowStatuses
 */

/**
 * Formata um nome técnico de status numa label legível.
 * Ex: "clientes_espera" → "Clientes Espera", "pre_registo" → "Pre Registo".
 *
 * @param {string} statusName - nome técnico do status (ex: "clientes_espera").
 * @returns {string} label legível ou "—" se vazio.
 */
export const formatStatusLabel = (statusName) => {
  if (!statusName || typeof statusName !== "string") return "—";
  return statusName
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * Constrói a lista de opções para a Dropdown de estado a partir da lista
 * DINÂMICA da API (/admin/workflow-statuses).
 *
 * Estratégia (PACOTE 11):
 *   1. Base: lista dinâmica da API — respeita a configuração do admin
 *      (label/color/order dele prevalecem). Sem fallback estático.
 *   2. Fallback de segurança: se o `currentStatus` (process.status) não
 *      existir na lista dinâmica (API falhou / fase removida do admin /
 *      coleção sem seed), injecta-o como opção extra com label formatada
 *      (underscores → espaços, capitalização) marcada com _isFallback.
 *
 * @param {Array}  workflowStatuses - lista dinâmica vinda de /admin/workflow-statuses.
 * @param {string} currentStatus    - status actual do processo (process.status).
 * @returns {Array} opções ordenadas por `order` asc; nunca vazio se currentStatus.
 */
export const buildStatusOptions = (workflowStatuses, currentStatus) => {
  const dynamic = Array.isArray(workflowStatuses)
    ? workflowStatuses.filter((s) => s && s.name)
    : [];

  const byName = new Map();
  for (const s of dynamic) byName.set(s.name, { ...s });

  // Fallback final: o status actual tem de aparecer sempre na dropdown
  // (mesmo quando a lista dinâmica falhou — mas SEM inventar fases).
  if (currentStatus && !byName.has(currentStatus)) {
    byName.set(currentStatus, {
      id: `__fallback_${currentStatus}`,
      name: currentStatus,
      label: formatStatusLabel(currentStatus),
      color: "blue",
      order: 9999,
      _isFallback: true,
    });
  }

  return Array.from(byName.values()).sort(
    (a, b) => (a.order ?? 9999) - (b.order ?? 9999)
  );
};
