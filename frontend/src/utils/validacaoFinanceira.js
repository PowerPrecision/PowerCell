/**
 * Validação financeira de uma lead de parceiro — regras PURAS do ecrã.
 *
 * É um AVISO, nunca um travão: o selo vermelho diz à equipa que está a
 * trabalhar sem viabilidade confirmada, e mais nada. Nenhum botão do sistema
 * se desactiva por causa disto (há um teste de fonte a afirmá-lo).
 */

/** Quem vê os botões «Validar Processo» e «Rejeitar» (perfil EFECTIVO). */
export const PAPEIS_QUE_VALIDAM = ["ceo", "diretor", "administrativo"];

export const ESTADO_PENDENTE = "pendente";
export const ESTADO_VALIDADO = "validado";
export const ESTADO_REJEITADO = "rejeitado";

export const MOTIVO_MINIMO = 3;
export const MOTIVO_MAXIMO = 500;

/** O texto do selo. Uma só vez: o ecrã e os testes leem daqui. */
export const TEXTO_DO_SELO = "⚠️ Processo Não Validado";

export function podeDecidir(papelEfectivo) {
  return PAPEIS_QUE_VALIDAM.includes(String(papelEfectivo || "").toLowerCase());
}

/** O estado da validação, ou `null` quando o registo não passa por validação. */
export function estadoDaValidacao(registo) {
  const v = registo?.validacao_financeira;
  const estado = v && typeof v === "object" ? v.estado : typeof v === "string" ? v : null;
  return [ESTADO_PENDENTE, ESTADO_VALIDADO, ESTADO_REJEITADO].includes(estado) ? estado : null;
}

/** Acende o selo: tem validação e ainda não foi validada («rejeitado» também). */
export function estaPorValidar(registo) {
  const estado = estadoDaValidacao(registo);
  return estado !== null && estado !== ESTADO_VALIDADO;
}

export function motivoDaRejeicao(registo) {
  const v = registo?.validacao_financeira;
  return v && typeof v === "object" && typeof v.motivo === "string" ? v.motivo.trim() : "";
}

/** Erro por campo do motivo; vazio = pode enviar. A validação real é a do servidor. */
export function validarMotivo(motivo) {
  const texto = String(motivo || "").trim();
  if (texto.length < MOTIVO_MINIMO) return "Indique o motivo (é enviado ao parceiro).";
  if (texto.length > MOTIVO_MAXIMO) return `O motivo não pode ter mais de ${MOTIVO_MAXIMO} caracteres.`;
  return "";
}
