/**
 * Falha ao enviar um email: o toast «a tentar» NÃO pode ficar para sempre (QA, Out 2026).
 *
 * Quando o envio directo do email de acesso ao Portal falha, o servidor agenda um reenvio e a
 * tarefa fica «Envio directo falhou — retry agendado na fila». O `TasksContext` mostra essa
 * tarefa num toast persistente (`duration: Infinity`) que só sai quando a tarefa termina — e se
 * ninguém processa o reenvio, nunca termina. O pedido que o utilizador fez (Enviar por Email)
 * responde com o erro, mas o toast antigo continuava lá a prometer uma tentativa que não existe.
 *
 * Aqui vive a decisão do que dizer e o registo dos toasts de email, para quem recebe o erro
 * SUBSTITUIR esses toasts por um de erro (mesmo id → o sonner troca, não empilha). Módulo sem
 * estado de React: o `TasksContext` regista os toasts e qualquer chamador de envio troca-os, sem
 * precisar do provider.
 */
import { toast } from "sonner";
import { extractErrorMessage } from "./extractErrorMessage";

export const TITULO_DA_TAREFA_DE_EMAIL_DE_ACESSO = "Email de acesso ao Portal";
export const KIND_DA_TAREFA_DE_EMAIL_DE_ACESSO = "portal_access_email";
export const TITULO_DA_FALHA = "Falha ao enviar e-mail";
export const ID_DO_TOAST_DE_FALHA = "falha-envio-email";
export const MOTIVO_SEM_RESPOSTA = "Sem ligação ao servidor. Verifique a ligação e tente novamente.";
export const MOTIVO_GENERICO = "O servidor não conseguiu enviar o e-mail. Tente novamente dentro de instantes.";

/** Ids dos toasts de email actualmente em curso. */
const emCurso = new Set();
/** Ids que já foram trocados por um erro: o polling não os pode voltar a pôr «a carregar». */
const substituidos = new Set();

export function eTarefaDeEmailDeAcesso(tarefa) {
  return (
    tarefa?.kind === KIND_DA_TAREFA_DE_EMAIL_DE_ACESSO ||
    tarefa?.title === TITULO_DA_TAREFA_DE_EMAIL_DE_ACESSO
  );
}

export function registarToastDeEmail(id) {
  emCurso.add(id);
}

export function toastDeEmailFoiSubstituido(id) {
  return substituidos.has(id);
}

/** A tarefa terminou: deixa de ser nossa. */
export function esquecerToastDeEmail(id) {
  emCurso.delete(id);
  substituidos.delete(id);
}

/** Só para testes. */
export function _reporRegistoDeToastsDeEmail() {
  emCurso.clear();
  substituidos.clear();
}

/**
 * O que dizer ao utilizador. O motivo do servidor vence (400 «sem remetente», 502 «o serviço de
 * email não entregou»…): é a regra que mandou recusar. Sem resposta, é a ligação.
 *
 * @param {*} erro o erro do Axios
 * @returns {{titulo: string, motivo: string}}
 */
export function descreverFalhaDoEnvioDeEmail(erro) {
  const resposta = erro?.response;
  if (!resposta) return { titulo: TITULO_DA_FALHA, motivo: MOTIVO_SEM_RESPOSTA };
  const doServidor = extractErrorMessage(resposta.data?.detail ?? resposta.data?.message, "");
  return { titulo: TITULO_DA_FALHA, motivo: doServidor || MOTIVO_GENERICO };
}

/**
 * Troca os toasts de email «a tentar» por um de erro. Devolve quantos trocou.
 * Com o MESMO id: o sonner substitui o toast em vez de empilhar outro por cima.
 */
export function substituirToastsDeEmailPorErro({ titulo, motivo }) {
  let trocados = 0;
  for (const id of [...emCurso]) {
    toast.error(titulo, { id, description: motivo, duration: Infinity, closeButton: true });
    substituidos.add(id);
    trocados += 1;
  }
  return trocados;
}

/**
 * O ponto de entrada de quem enviou um email e recebeu um erro: limpa o toast «a tentar» e mostra
 * a falha — um só aviso, quer houvesse toast antigo quer não.
 */
export function mostrarFalhaDoEnvioDeEmail(erro) {
  const descricao = descreverFalhaDoEnvioDeEmail(erro);
  if (substituirToastsDeEmailPorErro(descricao) === 0) {
    toast.error(descricao.titulo, {
      id: ID_DO_TOAST_DE_FALHA,
      description: descricao.motivo,
      duration: 8000,
    });
  }
  return descricao;
}
