/**
 * Ponto 16 — Edição Inline de Fases na Listagem (regras puras).
 *
 * PORQUÊ um módulo próprio: a célula da fase na tabela passa a ser
 * editável, e mudar a fase de um processo não é uma alteração cosmética
 * — dispara `process_trigger("process_status_changed")`, escreve no
 * histórico, no audit trail e envia um email ao cliente. As regras de
 * quem pode e de quando não pode ficam aqui, puras e testadas, em vez
 * de dispersas por condições dentro do JSX da listagem.
 *
 * REGRA DE OURO desta funcionalidade: a gravação usa o endpoint oficial
 * `PUT /processes/{id}` (o mesmo dos Detalhes). Não há atalho por
 * `update_one` nem endpoint novo — seria uma porta das traseiras à
 * auditoria, ao motor de automações e às regras de silêncio do perfil
 * de Indexação.
 */

/**
 * Papéis que podem mudar o estado de um processo.
 *
 * Espelha `build_role_update_permissions(role)["can_update_status"]` em
 * `backend/services/process_update.py`. Mostrar o dropdown a quem o
 * servidor vai recusar com 403 é prometer uma acção que não existe.
 */
export const PAPEIS_QUE_MUDAM_FASE = [
  "admin",
  "ceo",
  "consultor",
  "intermediario",
  "diretor",
  "administrativo",
];

/**
 * Estados terminais — `INACTIVE_STATUSES` em `services/process_status.py`,
 * usados por `assert_process_editable_for_role` para devolver 403.
 */
export const FASES_TERMINAIS = [
  "eliminado",
  "eliminados",
  "concluido",
  "concluidos",
  "desistencia",
  "desistencias",
  "desistido",
  "cancelado",
  "perdido",
  "arquivo",
];

/** Só estes dois passam por cima do bloqueio de estado terminal. */
export const PAPEIS_ACIMA_DO_BLOQUEIO = ["admin", "ceo"];

function normalizar(valor) {
  return typeof valor === "string" ? valor.trim().toLowerCase() : "";
}

/**
 * A célula da fase desta linha é editável?
 *
 * UM papel só: o perfil ACTIVO (`effectiveRole`). Durante um curto
 * período esta função exigiu também o papel base do JWT, porque o
 * `run_update_process` resolvia `can_update_status` por `user["role"]`
 * e os dois divergiam. Essa brecha foi fechada no backend — o PUT segue
 * agora `get_effective_role`, como o resto do produto — e manter aqui a
 * dupla condição deixou de ser prudência: passou a ESCONDER uma acção
 * legítima a quem é, por exemplo, indexador numa empresa e consultor
 * noutra. Uma permissão espelha-se num sítio só, e esse sítio é o
 * perfil activo.
 *
 * @param {object} args
 * @param {string} args.role — papel efectivo (perfil activo)
 * @param {string} args.status — estado actual do processo
 * @param {boolean} [args.isDeleted] — soft-delete (`is_deleted`)
 * @returns {boolean}
 */
export function podeEditarFase({ role, status, isDeleted } = {}) {
  const papel = normalizar(role);
  if (!papel || !PAPEIS_QUE_MUDAM_FASE.includes(papel)) return false;

  // Um processo eliminado tem caminho próprio (Restaurar). Mudar-lhe a
  // fase a partir da listagem ressuscitava-o sem restauro nem rasto.
  if (isDeleted) return false;

  const estado = normalizar(status);
  if (FASES_TERMINAIS.includes(estado)) {
    // `assert_process_editable_for_role` lê o mesmo perfil activo.
    return PAPEIS_ACIMA_DO_BLOQUEIO.includes(papel);
  }
  return true;
}

/**
 * Opções do dropdown de fase.
 *
 * O estado actual entra SEMPRE na lista, mesmo que o motor já não o
 * conheça (fase legada ou apagada pelo administrador): sem ele o Select
 * abriria sem valor seleccionado e a célula ficava visualmente vazia
 * sobre um processo que tem fase.
 *
 * @param {Array<{name: string, label?: string}>} workflowStatuses
 * @param {string} estadoActual
 * @returns {Array<{name: string, label: string, foraDoMotor: boolean}>}
 */
export function opcoesDeFase(workflowStatuses, estadoActual) {
  const opcoes = [];
  const vistos = new Set();

  for (const fase of Array.isArray(workflowStatuses) ? workflowStatuses : []) {
    const nome = typeof fase?.name === "string" ? fase.name.trim() : "";
    if (!nome || vistos.has(nome)) continue;
    vistos.add(nome);
    opcoes.push({
      name: nome,
      label: (fase.label || "").trim() || nome.replace(/_/g, " "),
      foraDoMotor: false,
    });
  }

  const actual = typeof estadoActual === "string" ? estadoActual.trim() : "";
  if (actual && !vistos.has(actual)) {
    opcoes.push({
      name: actual,
      label: actual.replace(/_/g, " "),
      foraDoMotor: true,
    });
  }

  return opcoes;
}

/**
 * Vale a pena gravar esta escolha de fase?
 *
 * Um PUT com a fase que já lá está não é inócuo: escreve no histórico,
 * no audit trail e manda um email ao cliente a anunciar uma alteração
 * que não houve. O Radix não dispara `onValueChange` para o item já
 * seleccionado, mas essa é uma garantia da BIBLIOTECA e não uma regra
 * do produto — a regra vive aqui, onde é testável de frente.
 *
 * @param {string} actual — fase gravada no processo
 * @param {string} nova — fase escolhida no dropdown
 * @returns {boolean}
 */
export function deveGravarNovaFase(actual, nova) {
  const escolhida = typeof nova === "string" ? nova.trim() : "";
  if (!escolhida) return false;
  const anterior = typeof actual === "string" ? actual.trim() : "";
  return escolhida !== anterior;
}

/**
 * Depois de mudar a fase, a listagem tem de voltar ao servidor?
 *
 * A actualização optimista chega quase sempre: o utilizador acabou de
 * escolher a fase e quer vê-la na linha. Mas há dois casos em que a
 * linha deixa de PERTENCER à listagem que está aberta, e mantê-la
 * visível seria mentir sobre o filtro activo:
 *
 *  - há um filtro de estado e a fase nova não é a filtrada;
 *  - a vista mostra só activos e a fase nova é terminal.
 *
 * Em tudo o resto não se recarrega nada — zero pedidos por edição.
 *
 * @param {object} args
 * @param {string} args.novaFase
 * @param {string} [args.statusFilter] — filtro de estado activo no URL
 * @param {string} [args.viewMode] — active_only | all | deleted
 * @returns {boolean}
 */
export function precisaDeRecarregar({ novaFase, statusFilter, viewMode } = {}) {
  const fase = normalizar(novaFase);
  if (!fase) return false;

  const filtro = normalizar(statusFilter);
  if (filtro && filtro !== fase) return true;

  const vista = normalizar(viewMode) || "active_only";
  if (vista === "active_only" && FASES_TERMINAIS.includes(fase)) return true;

  return false;
}
