/**
 * Processo FECHADO (fase terminal) — a regra do ecrã.
 *
 * O servidor recusa qualquer edição ou upload da equipa num processo em fase
 * terminal (`services/process_closed_guard.py`, 403) e só se altera depois de
 * o REABRIR (`POST /processes/{id}/reopen`). Isto é o espelho no ecrã: o
 * utilizador vê o modo de leitura e o botão "Reabrir" antes de tentar.
 *
 * A autoridade é o MOTOR de fases (`is_active` de cada fase); a lista legada
 * só entra quando a fase do processo não está no motor (fase apagada, API em
 * baixo) — o mesmo critério do servidor. Sem excepção por cargo: o servidor
 * deixou de isentar Master/Admin/CEO, e o ecrã tem de dizer a mesma coisa.
 */
import { FASES_TERMINAIS } from "./inlinePhaseEdit";

/** Quem vê o botão "Reabrir": os perfis que mudam a fase de um processo. */
export { PAPEIS_QUE_MUDAM_FASE as PAPEIS_QUE_REABREM } from "./inlinePhaseEdit";

function normalizar(valor) {
  return typeof valor === "string" ? valor.trim().toLowerCase() : "";
}

/**
 * @param {{status?: string}|null|undefined} processo
 * @param {Array<{name: string, is_active?: boolean|null}>} [fases] — as fases do motor
 * @returns {boolean}
 */
export function processoEstaFechado(processo, fases = []) {
  const estado = processo?.status;
  if (!estado || typeof estado !== "string") return false;

  // `Array.isArray` e não `|| []`: um objecto é truthy e `.find` rebentava.
  const lista = Array.isArray(fases) ? fases : [];
  const fase = lista.find((f) => f && f.name === estado);
  if (fase && typeof fase.is_active === "boolean") return !fase.is_active;

  return FASES_TERMINAIS.includes(normalizar(estado));
}

/**
 * As fases para onde se pode reabrir: as ACTIVAS do motor, por ordem.
 * Uma fase sem a flag conta como activa a não ser que esteja na lista legada
 * (o mesmo fallback do servidor).
 */
export function fasesParaReabrir(fases) {
  const lista = Array.isArray(fases) ? fases : [];
  return lista
    .filter((f) => f && typeof f.name === "string" && f.name)
    .filter((f) => (typeof f.is_active === "boolean"
      ? f.is_active
      : !FASES_TERMINAIS.includes(normalizar(f.name))))
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .map((f) => ({ name: f.name, label: f.label || f.name }));
}
