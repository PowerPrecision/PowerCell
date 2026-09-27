/**
 * taskAssignees — quem pode ficar responsável por uma tarefa.
 *
 * Ponto 10 (Lote 5, Secção B). O agrupamento "equipa do processo
 * primeiro, o resto atrás de um separador" já existia dentro do
 * `TasksPanel`, mas só no formulário de CRIAÇÃO. A reatribuição precisa
 * do mesmo, e duplicá-lo daria dois sítios a divergir.
 *
 * A REGRA VEM DO LOTE 4 (ponto 13): quando a equipa do processo não se
 * confirma, isso é DITO. Antes caía-se para todo o staff com um
 * `console.warn` — o utilizador via uma lista enorme sem saber porquê.
 *
 * @module utils/taskAssignees
 */

const id = (valor) => String(valor ?? "");

/**
 * @param {object} [entrada]
 * @param {Array}  [entrada.users] - Staff seleccionável.
 * @param {Array}  [entrada.equipaDoProcesso] - Ids atribuídos ao processo.
 * @param {boolean} [entrada.dentroDeProcesso] - Se a tarefa pertence a um
 *   processo (fora dele não há equipa a separar).
 * @returns {{daEquipa: Array, foraDaEquipa: Array, temGrupos: boolean,
 *   equipaPorConfirmar: boolean}}
 */
export function agruparResponsaveis({
  users,
  equipaDoProcesso,
  dentroDeProcesso = false,
} = {}) {
  const lista = (Array.isArray(users) ? users : []).filter((u) => u && u.id != null);

  if (!dentroDeProcesso) {
    return {
      daEquipa: lista,
      foraDaEquipa: [],
      temGrupos: false,
      // Sem processo não há equipa para confirmar; um aviso aqui seria
      // ruído permanente na lista geral de tarefas.
      equipaPorConfirmar: false,
    };
  }

  const ids = new Set((Array.isArray(equipaDoProcesso) ? equipaDoProcesso : []).map(id));
  if (ids.size === 0) {
    return {
      daEquipa: lista,
      foraDaEquipa: [],
      temGrupos: false,
      equipaPorConfirmar: true,
    };
  }

  const daEquipa = lista.filter((u) => ids.has(id(u.id)));
  const foraDaEquipa = lista.filter((u) => !ids.has(id(u.id)));
  return {
    daEquipa,
    foraDaEquipa,
    temGrupos: foraDaEquipa.length > 0,
    equipaPorConfirmar: false,
  };
}
