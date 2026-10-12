/**
 * «Repor ao Modelo» — leitura do erro do servidor (puro).
 *
 * É a leitura genérica da confirmação por password (`confirmarComPassword`) com os textos de
 * recuo desta acção. O servidor responde:
 *   403 { detail: "Password incorrecta." }                         → password errada
 *   429 { detail: { message, retry_after_minutes } }               → travão por tentativas
 *   409 { detail: { message, fases_em_uso: [{name, total}] } }     → processos em fases que o modelo não tem
 *   409 { detail: "O modelo de workflow está vazio…" }
 *   404 { detail: "Rede não encontrada" }
 */
import { lerErroDeConfirmacao } from "./confirmarComPassword";

const TEXTOS = {
  recusado: "Não é possível repor ao modelo neste momento.",
  naoEncontrado: "Rede não encontrada.",
  erro: "Não foi possível repor ao modelo. Tente novamente.",
};

export function lerErroDeReposicao(err) {
  return lerErroDeConfirmacao(err, TEXTOS);
}

export default { lerErroDeReposicao };
