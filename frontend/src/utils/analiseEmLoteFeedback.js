/**
 * analiseEmLoteFeedback — o desfecho da análise em lote, em palavras.
 *
 * "VLM NO ESCURO" (Lote 5, Prioridade 0)
 *   Clicar em "Analisar Documentos" nos detalhes do processo processava
 *   e não devolvia nada à UI: toast verde "Análise completa! 3
 *   documento(s) processado(s)" e o Diálogo de Revisão Humana calado.
 *
 *   A cadeia tinha três pontos a engolir, e nenhum estava errado
 *   sozinho. No backend, o analisador saltava o documento que falhava
 *   (a chave da OpenAI em falta, a quota esgotada) mandando o motivo só
 *   para o log de importação, e a resposta trazia `documents_count` — os
 *   documentos ENVIADOS, não os lidos. No frontend, `{}` é truthy, por
 *   isso `if (result.extracted_data)` deixava passar o resultado vazio;
 *   e `commitAIExtractedData` tinha dois `return` mudos.
 *
 * PORQUE É QUE ISTO É UM MÓDULO PURO
 *   A decisão ("isto é um sucesso, um aviso ou um erro?") vivia dentro
 *   de um componente de 2900 linhas e de outro de 1800 — onde não se
 *   testa e onde se repete. Aqui testa-se, e os dois caminhos (o botão
 *   do `S3FileManager` e o `commitAIExtractedData`) dizem o mesmo.
 *
 * TRÊS DESFECHOS, NUNCA QUATRO
 *   `sucesso` (leu e há o que rever) · `aviso` (correu mas não há nada
 *   para preencher, ou parte falhou) · `erro` (não leu nada). O
 *   silêncio não é um desfecho.
 *
 * @module utils/analiseEmLoteFeedback
 */

/** Quantos nomes de ficheiro cabem numa mensagem antes de cansar. */
const MAX_NOMES = 3;

const nomesDasFalhas = (falhas) =>
  falhas
    .slice(0, MAX_NOMES)
    .map((f) => f?.file_name)
    .filter(Boolean)
    .join(", ");

const motivosDistintos = (falhas) => [
  ...new Set(falhas.map((f) => f?.error).filter(Boolean)),
];

/**
 * Traduz a resposta de `/documents/ai-analyze` numa mensagem para o
 * utilizador.
 *
 * @param {object}  [resposta]
 * @param {number}  [resposta.documentsCount] - Documentos ENVIADOS.
 * @param {number}  [resposta.documentsSucceeded] - Documentos que a IA
 *   leu mesmo. Ausente numa resposta de um deploy anterior: nesse caso
 *   assume-se o comportamento antigo (tudo o que foi enviado foi lido).
 * @param {Array}   [resposta.documentsFailed] - `[{file_name, error}]`.
 * @param {boolean} [resposta.temRevisao] - Se sobrou alguma coisa para o
 *   Diálogo de Revisão Humana mostrar.
 * @returns {{tipo: "sucesso"|"aviso"|"erro", texto: string}}
 */
export function resumirAnaliseEmLote({
  documentsCount,
  documentsSucceeded,
  documentsFailed,
  temRevisao,
} = {}) {
  const enviados = Number(documentsCount) || 0;
  const falhas = Array.isArray(documentsFailed) ? documentsFailed : [];
  // Sem o campo novo, vale o que sempre valeu — não inventar falhas a
  // partir de uma resposta que não as sabe contar.
  const lidos =
    documentsSucceeded === undefined || documentsSucceeded === null
      ? Math.max(enviados - falhas.length, 0)
      : Number(documentsSucceeded) || 0;

  if (enviados > 0 && lidos === 0) {
    const motivos = motivosDistintos(falhas);
    const porque = motivos.length > 0 ? ` ${motivos.join("; ")}` : "";
    return {
      tipo: "erro",
      texto:
        `A IA não conseguiu ler ${enviados} documento(s).${porque}` +
        (porque ? "" : " Verifique a configuração da IA ou tente novamente."),
    };
  }

  if (falhas.length > 0) {
    const nomes = nomesDasFalhas(falhas);
    const resto = falhas.length > MAX_NOMES ? ` e mais ${falhas.length - MAX_NOMES}` : "";
    return {
      tipo: "aviso",
      texto: `${lidos} documento(s) analisado(s). Falharam: ${nomes}${resto}.`,
    };
  }

  if (!temRevisao) {
    // O caso que dava o toast verde e o diálogo calado: a IA correu, não
    // reconheceu nada de útil, e ninguém dizia nada.
    return {
      tipo: "aviso",
      texto:
        enviados > 0
          ? `A IA analisou ${enviados} documento(s) mas não encontrou dados para preencher a ficha.`
          : "A IA não devolveu dados para rever.",
    };
  }

  return {
    tipo: "sucesso",
    texto: `Análise completa: ${lidos || enviados} documento(s). Reveja os dados antes de gravar.`,
  };
}
