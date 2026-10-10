/**
 * Desvio inteligente (Bloco 2, Lote 12): o que dizer ao utilizador sobre
 * ficheiros que entram na pasta `Index`.
 *
 * Num processo por indexar TUDO o que se envia vai para a `Index` e entra na
 * fila da IA; só quem gere a Indexação vê essa pasta. Um consultor que
 * acabou de enviar um documento e não o vê em lado nenhum conclui que o
 * envio falhou — daí estas duas frases: uma no momento do envio, outra
 * permanente enquanto houver ficheiros à espera.
 *
 * Puro de propósito: a decisão (fila ou não) é do servidor (`intake` na
 * resposta); o ecrã só a diz. Não reimplementa a regra «indexado?».
 */

const ehObjecto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/**
 * Resume as respostas de uma série de envios.
 * @param {Array<object>} respostas — o `data` de cada upload com sucesso.
 * @returns {{enviados: number, naFila: number, mensagem: string|null}}
 */
export const resumoDosEnvios = (respostas) => {
  const lista = Array.isArray(respostas) ? respostas.filter(ehObjecto) : [];
  const naFila = lista.filter((r) => r.intake?.fila_ia === true).length;
  return {
    enviados: lista.length,
    naFila,
    mensagem:
      naFila === 0
        ? null
        : naFila === 1
          ? "O ficheiro ficou na pasta Index, à espera da Indexação."
          : `${naFila} ficheiros ficaram na pasta Index, à espera da Indexação.`,
  };
};

/** Quantos ficheiros esperam a Indexação, sem os mostrar. Nunca negativo. */
export const quantosEmIndexacao = (resposta) => {
  const n = Number(resposta?.em_indexacao);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
};

/** A frase permanente do cartão. `null` quando não há nada a dizer. */
export const textoEmIndexacao = (n) => {
  const total = Number.isFinite(n) ? Math.floor(n) : 0;
  if (total <= 0) return null;
  return total === 1
    ? "1 ficheiro enviado aguarda a Indexação e ainda não aparece nas pastas."
    : `${total} ficheiros enviados aguardam a Indexação e ainda não aparecem nas pastas.`;
};
