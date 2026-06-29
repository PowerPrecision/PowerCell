/**
 * workflowStatuses — Constantes e helpers para os estados do workflow de processos.
 *
 * PORQUÊ: O backend usa um enum canónico (backend/models/enums.py → ProcessStatus)
 * com 16 fases, mas a coleção MongoDB `workflow_statuses` é configurável pelo admin
 * e pode conter nomes adicionais (legacy ou custom). Além disso, processos antigos
 * podem ter um `status` que já não existe na coleção actual.
 *
 * Para que a Dropdown de estado nos Detalhes do Processo NUNCA fique em branco,
 * mantemos aqui uma lista estática (KNOWN_PROCESS_STATUSES) com todos os estados
 * conhecidos do backend. Esta lista serve de baseline quando a API
 * (/admin/workflow-statuses) devolve vazio ou falha; e um fallback final injeta o
 * `status` actual do processo caso este não exista em nenhuma das listas.
 *
 * @module utils/workflowStatuses
 */

// ── Lista estática: todos os estados conhecidos do backend ──────────
// Canónicos do enum ProcessStatus (backend/models/enums.py) + legacy de seeds
// antigos (seed.py, seed_database.py). Ordem = ordem do enum/seed; label/color PT-PT.
export const KNOWN_PROCESS_STATUSES = [
  // Fase 0: Pré-Registo (Portal — ainda não é lead qualificada)
  { id: "pre_registo", name: "pre_registo", label: "Pré-Registo", color: "gray", order: 0 },
  // Fase 1-3: Início
  { id: "clientes_espera", name: "clientes_espera", label: "Clientes em Espera", color: "yellow", order: 1 },
  { id: "documentacao", name: "documentacao", label: "Documentação", color: "blue", order: 2 },
  { id: "analise", name: "analise", label: "Análise", color: "blue", order: 3 },
  // Fase 4-7: Aprovação
  { id: "pre_aprovacao", name: "pre_aprovacao", label: "Pré-Aprovação", color: "orange", order: 4 },
  { id: "credito_aprovado", name: "credito_aprovado", label: "Crédito Aprovado", color: "orange", order: 5 },
  { id: "pedido_avaliacao", name: "pedido_avaliacao", label: "Pedido de Avaliação", color: "orange", order: 6 },
  { id: "avaliacao", name: "avaliacao", label: "Avaliação", color: "green", order: 7 },
  // Fase 8-10: Contrato
  { id: "cpcv", name: "cpcv", label: "CPCV", color: "green", order: 8 },
  { id: "minuta", name: "minuta", label: "Minuta", color: "green", order: 9 },
  { id: "escritura", name: "escritura", label: "Escritura", color: "green", order: 10 },
  // Fase 11-14: Conclusão
  { id: "concluido", name: "concluido", label: "Concluído", color: "green", order: 11 },
  { id: "arquivo", name: "arquivo", label: "Arquivo", color: "gray", order: 12 },
  { id: "perdido", name: "perdido", label: "Perdido", color: "red", order: 13 },
  { id: "desistencias", name: "desistencias", label: "Desistências", color: "red", order: 14 },
  // Fila de Espera — sem indexador disponível
  { id: "fila_espera", name: "fila_espera", label: "Fila de Espera", color: "yellow", order: 15 },

  // ── Estados legacy / alternativos (seeds antigos) ──
  { id: "triagem", name: "triagem", label: "Triagem", color: "gray", order: 0.5 },
  { id: "aprovado", name: "aprovado", label: "Aprovado", color: "green", order: 4.5 },
  { id: "recusado", name: "recusado", label: "Recusado", color: "red", order: 13.5 },
  { id: "desistido", name: "desistido", label: "Desistido", color: "gray", order: 14.5 },
  { id: "cancelado", name: "cancelado", label: "Cancelado", color: "gray", order: 14.6 },
  { id: "concluidos", name: "concluidos", label: "Concluídos", color: "green", order: 11.5 },
  { id: "fase_documental", name: "fase_documental", label: "Fase Documental", color: "blue", order: 2.1 },
  { id: "fase_documental_ii", name: "fase_documental_ii", label: "Fase Documental II", color: "blue", order: 2.2 },
  { id: "enviado_bruno", name: "enviado_bruno", label: "Enviado ao Bruno", color: "purple", order: 3.1 },
  { id: "enviado_luis", name: "enviado_luis", label: "Enviado ao Luís", color: "purple", order: 3.2 },
  { id: "enviado_bcp_rui", name: "enviado_bcp_rui", label: "Enviado BCP Rui", color: "purple", order: 3.3 },
  { id: "entradas_precision", name: "entradas_precision", label: "Entradas Precision", color: "orange", order: 6.1 },
  { id: "fase_bancaria", name: "fase_bancaria", label: "Fase Bancária - Pré Aprovação", color: "orange", order: 4.2 },
  { id: "fase_visitas", name: "fase_visitas", label: "Fase de Visitas", color: "blue", order: 5.1 },
  { id: "ch_aprovado", name: "ch_aprovado", label: "CH Aprovado - Avaliação", color: "green", order: 7.1 },
  { id: "fase_escritura", name: "fase_escritura", label: "Fase de Escritura", color: "green", order: 10.1 },
  { id: "escritura_agendada", name: "escritura_agendada", label: "Escritura Agendada", color: "green", order: 10.2 },
];

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
 * Constrói a lista de opções para a Dropdown de estado, garantindo que
 * NUNCA fica em branco quando existe um `currentStatus` definido.
 *
 * Estratégia (resolve o bug da dropdown vazia):
 *   1. Se a lista dinâmica da API (workflowStatuses) tiver itens, usa-a como base
 *      (respeita a configuração do admin — label/color/order dele prevalecem).
 *   2. Se a lista dinâmica estiver vazia (API falhou / coleção não seeded),
 *      recorre ao baseline estático KNOWN_PROCESS_STATUSES (16 canónicos + legacy).
 *   3. Fallback de segurança: se o `currentStatus` (process.status) não existir na
 *      base escolhida, injeta-o como opção extra com label formatada
 *      (underscores → espaços, capitalização) marcada com _isFallback = true.
 *
 * @param {Array}  workflowStatuses - lista dinâmica vinda de /admin/workflow-statuses.
 * @param {string} currentStatus    - status actual do processo (process.status).
 * @returns {Array} opções ordenadas por `order` asc; nunca vazio se currentStatus.
 */
export const buildStatusOptions = (workflowStatuses, currentStatus) => {
  const dynamic = Array.isArray(workflowStatuses)
    ? workflowStatuses.filter((s) => s && s.name)
    : [];

  // Base: dinâmica (admin) se existir; senão, baseline estático canónico.
  const base = dynamic.length > 0
    ? dynamic.map((s) => ({ ...s }))
    : KNOWN_PROCESS_STATUSES.map((s) => ({ ...s }));

  const byName = new Map();
  for (const s of base) byName.set(s.name, { ...s });

  // Fallback final: o status actual tem de aparecer sempre na dropdown.
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

export default KNOWN_PROCESS_STATUSES;
