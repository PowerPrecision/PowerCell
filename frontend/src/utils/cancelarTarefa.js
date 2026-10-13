/**
 * O que dizer a quem tenta cancelar uma tarefa em background e não consegue.
 *
 * O servidor recusa o cancelamento com 400 quando a tarefa já terminou ou falhou
 * («Apenas tarefas pendentes/em execução podem ser canceladas») e com 404 quando já
 * não existe. Ambas são respostas CORRECTAS — e o ecrã ficava com o botão «morto»:
 * o 404 não gera toast nenhum (o interceptor ignora-o de propósito), o 400 saía como
 * um «Erro» genérico que o `catch` do componente ainda cobria com um segundo aviso
 * sem motivo, e o painel do `TasksPanel` engolia a falha por completo
 * (`.catch(() => {})`). Pior: a tarefa continuava na lista, por isso o utilizador
 * voltava a clicar. Dois deveres, então: DIZER o motivo e RESSINCRONIZAR a lista.
 *
 * Puro: devolve a decisão, quem chama desenha o toast.
 */
import { extractErrorMessage } from "./extractErrorMessage";

export const TITULO_RECUSA = "Não foi possível cancelar a tarefa";
export const MOTIVO_TAREFA_TERMINADA =
  "A tarefa já terminou ou falhou, por isso já não pode ser cancelada.";
export const MOTIVO_TAREFA_INEXISTENTE = "A tarefa já não existe — a lista foi actualizada.";
export const MOTIVO_SEM_PERMISSAO = "Não tem permissão para cancelar esta tarefa.";
export const MOTIVO_FALHA_DO_SERVIDOR =
  "O servidor não conseguiu cancelar a tarefa. Tente novamente dentro de instantes.";

/**
 * @param {*} erro o erro do Axios
 * @returns {{mostrar: boolean, titulo: string, motivo: string, ressincronizar: boolean}}
 *   `mostrar` é falso quando não houve resposta do servidor: o interceptor já
 *   avisou «Erro de Conexão» e um segundo toast seria ruído.
 */
export function descreverRecusaDoCancelamento(erro) {
  const resposta = erro?.response;
  if (!resposta) {
    return { mostrar: false, titulo: TITULO_RECUSA, motivo: "", ressincronizar: false };
  }
  const { status, data } = resposta;
  const doServidor = extractErrorMessage(data?.detail ?? data?.message, "");

  if (status === 400) {
    return {
      mostrar: true,
      titulo: TITULO_RECUSA,
      // O motivo do servidor vence: é a regra que mandou recusar.
      motivo: doServidor || MOTIVO_TAREFA_TERMINADA,
      ressincronizar: true,
    };
  }
  if (status === 404) {
    return {
      mostrar: true,
      titulo: TITULO_RECUSA,
      motivo: MOTIVO_TAREFA_INEXISTENTE,
      ressincronizar: true,
    };
  }
  if (status === 403) {
    return {
      mostrar: true,
      titulo: TITULO_RECUSA,
      motivo: doServidor || MOTIVO_SEM_PERMISSAO,
      ressincronizar: false,
    };
  }
  return {
    mostrar: true,
    titulo: TITULO_RECUSA,
    motivo: status >= 500 ? MOTIVO_FALHA_DO_SERVIDOR : (doServidor || MOTIVO_FALHA_DO_SERVIDOR),
    ressincronizar: false,
  };
}
