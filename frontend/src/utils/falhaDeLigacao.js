/**
 * Falhas de LIGAÇÃO ao servidor — as que não dizem nada sobre o pedido (Lote 6, ponto 5).
 *
 * Um `502 Bad Gateway`, um `ERR_CONNECTION_CLOSED` ou um tempo esgotado são do servidor ou da
 * rede — um soluço da hospedagem, ou o servidor SMTP de uma empresa que não responde —, não do
 * que o utilizador fez. Duas consequências:
 *
 *  * a mensagem tem de o DIZER (e dizer que se pode tentar outra vez). Um `catch` que mostra
 *    «Erro ao testar a ligação» para tudo manda mexer nas credenciais quando o que falhou foi o
 *    caminho até ao servidor;
 *  * quem faz uma operação que termina num `reload()` não pode recarregar contra um servidor que
 *    não responde — o browser mostra a sua página de erro e a aplicação desaparece.
 *
 * Funções puras: sem I/O, sem React.
 */
import { extractErrorMessage } from "./extractErrorMessage";

/** Estados HTTP em que quem respondeu foi o proxy/hospedagem, não a aplicação. */
const ESTADOS_DE_INDISPONIBILIDADE = new Set([502, 503, 504]);

/**
 * O erro é «o servidor não respondeu» (sem resposta, ou 502/503/504)?
 * Um 4xx ou um 500 da aplicação NÃO são: esses dizem algo sobre o pedido.
 */
export function eFalhaDeLigacao(erro) {
  if (!erro) return false;
  const estado = erro?.response?.status;
  if (estado == null) {
    // Sem resposta: rede cortada, ligação fechada, tempo esgotado. Um erro que nem tem
    // `response` mas também nem é de rede (um `TypeError` nosso) não é uma falha de ligação. O
    // `fetch` do browser falha com `TypeError: Failed to fetch` (Chrome) / `Load failed` (Safari).
    return Boolean(erro.request) || ["ERR_NETWORK", "ECONNABORTED", "ETIMEDOUT"].includes(erro.code)
      || /network error|timeout|failed to fetch|load failed|networkerror/i.test(String(erro.message || ""));
  }
  return ESTADOS_DE_INDISPONIBILIDADE.has(estado);
}

/**
 * A mensagem que se mostra. `padrao` serve a um erro que NÃO é de ligação e não traz `detail`.
 */
export function mensagemDeFalha(erro, padrao) {
  if (eFalhaDeLigacao(erro)) {
    const estado = erro?.response?.status;
    return estado
      ? `O servidor não respondeu (erro ${estado}). Pode ser uma indisponibilidade momentânea — tente novamente dentro de instantes.`
      : "Sem ligação ao servidor. Verifique a ligação à internet e tente novamente.";
  }
  return extractErrorMessage(erro?.response?.data?.detail, padrao);
}

/**
 * O mesmo para quem usa `fetch` (sem excepção para respostas HTTP): `estado` é o `res.status`
 * e `corpo` o JSON já lido (ou `{}` quando o corpo não era JSON — um 502 do proxy traz HTML).
 */
export function mensagemDeResposta(estado, corpo, padrao) {
  return mensagemDeFalha(
    { response: { status: estado, data: corpo || {} } },
    // Os `fetch` do ecrã de configuração usam `detail` ou `message`.
    extractErrorMessage(corpo?.detail ?? corpo?.message, padrao),
  );
}
