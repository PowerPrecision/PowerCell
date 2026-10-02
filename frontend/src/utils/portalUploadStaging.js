/**
 * Lote de ficheiros em envio no Portal do Cliente (Lote 3, ponto 4).
 *
 * O DEFEITO
 * `DocumentUploadItem` recebia a selecção e mandava-a directa para o
 * `uploadFiles`, que mostrava um contador — `2/5` — e nada mais. Quando o
 * lote terminava:
 *
 *     setResult({ success: true, count: successes.length, errorCount: ... })
 *     // e, no caso de falharem todos:
 *     setResult({ error: errors[0].error })
 *
 * Daí saíam duas perdas de informação concretas:
 *   1. **Durante o envio não havia nomes.** Um `2/5` não diz QUAL é o
 *      segundo, e se um ficheiro grande demorar o cliente não sabe se é o
 *      que ele quer que chegue.
 *   2. **No fim, os erros eram anónimos.** `errors[0].error` mostra a
 *      mensagem do PRIMEIRO; o cliente que envia 5 e tem 2 a falhar não
 *      consegue saber quais. E «2 erros no último envio» é a frase que ele
 *      lê — sem um único nome de ficheiro.
 *
 * Isto é puro de propósito: é a lista que o ecrã mostra, e dentro do
 * componente não se conseguia afirmar nada sobre ela.
 */

export const A_ESPERA = "a_espera";
export const A_ENVIAR = "a_enviar";
export const ENVIADO = "enviado";
export const FALHOU = "falhou";

/**
 * O estado inicial de um lote: todos à espera, nenhum em curso.
 *
 * Guarda-se o `name` e o `size` e NUNCA o objecto `File`: o que o ecrã
 * precisa é do nome, e manter a referência ao ficheiro prendia os bytes
 * em memória depois de o envio acabar.
 */
export function criarLote(ficheiros) {
  const lista = Array.from(ficheiros || []);
  return lista.map((f, indice) => ({
    // O nome não é único (dois ficheiros com o mesmo nome em pastas
    // diferentes são uma selecção legítima), logo a chave é a POSIÇÃO.
    id: `${indice}:${f?.name ?? ""}`,
    nome: f?.name || "ficheiro",
    tamanho: typeof f?.size === "number" ? f.size : null,
    estado: A_ESPERA,
    erro: null,
  }));
}

/** Marca um ficheiro do lote (por posição) com um estado novo. */
export function marcar(lote, indice, estado, erro = null) {
  if (!Array.isArray(lote)) return [];
  return lote.map((item, i) => (i === indice ? { ...item, estado, erro } : item));
}

/** Quantos já terminaram (com sucesso ou não). */
export function concluidos(lote) {
  if (!Array.isArray(lote)) return 0;
  return lote.filter((i) => i.estado === ENVIADO || i.estado === FALHOU).length;
}

/** Os que falharam — com NOME, que é o que faltava. */
export function falhados(lote) {
  if (!Array.isArray(lote)) return [];
  return lote.filter((i) => i.estado === FALHOU);
}

export function enviados(lote) {
  if (!Array.isArray(lote)) return [];
  return lote.filter((i) => i.estado === ENVIADO);
}

/** O lote acabou? */
export function terminado(lote) {
  return Array.isArray(lote) && lote.length > 0 && concluidos(lote) === lote.length;
}

/**
 * O resumo em texto do que aconteceu ao lote.
 *
 * Nomeia os ficheiros que falharam em vez de contar erros: «2 erros» manda
 * o cliente adivinhar, e o que ele precisa é de saber o que repetir. Com
 * muitos, nomeia os primeiros e diz quantos mais — uma lista de trinta
 * nomes numa linha não é informação, é ruído.
 */
export function resumirLote(lote, { maximoDeNomes = 3 } = {}) {
  if (!Array.isArray(lote) || lote.length === 0) return null;
  if (!terminado(lote)) return null;

  const ok = enviados(lote);
  const ko = falhados(lote);

  if (ko.length === 0) {
    return {
      tipo: "sucesso",
      texto:
        ok.length === 1
          ? "1 ficheiro enviado."
          : `${ok.length} ficheiros enviados.`,
    };
  }

  const nomes = ko.slice(0, maximoDeNomes).map((i) => i.nome);
  const restantes = ko.length - nomes.length;
  const listaDeNomes = restantes > 0 ? `${nomes.join(", ")} (+${restantes})` : nomes.join(", ");

  if (ok.length === 0) {
    return {
      tipo: "erro",
      texto: `Não foi possível enviar: ${listaDeNomes}.`,
      // A mensagem técnica do primeiro erro, para quem precise dela.
      detalhe: ko[0]?.erro || null,
    };
  }

  return {
    tipo: "parcial",
    texto: `${ok.length} enviado(s). Falhou: ${listaDeNomes}.`,
    detalhe: ko[0]?.erro || null,
  };
}

/** O rótulo de progresso do lote: nomes quando é um, contagem quando são vários. */
export function etiquetaDeProgresso(lote, progressoDoActual) {
  if (!Array.isArray(lote) || lote.length === 0) return "";
  if (lote.length === 1) {
    return typeof progressoDoActual === "number" ? `${progressoDoActual}%` : "";
  }
  return `${Math.min(concluidos(lote) + 1, lote.length)}/${lote.length}`;
}

/**
 * Junta os ficheiros já no servidor com o lote em curso, para a UI mostrar
 * UMA lista.
 *
 * Duas listas lado a lado (os anexados e os em envio) fazem o mesmo
 * ficheiro aparecer duas vezes no instante em que termina — primeiro como
 * "enviado" no lote, depois outra vez quando o refetch o trouxer. A chave
 * da desduplicação é o NOME, que é o que o cliente reconhece.
 */
export function listaUnificada(anexados, lote) {
  const jaNoServidor = (Array.isArray(anexados) ? anexados : []).map((f) => ({
    id: f.file_id || f.s3_path || f.filename,
    nome: f.filename || f.original_filename || "ficheiro",
    tamanho: typeof f.file_size === "number" ? f.file_size : null,
    estado: ENVIADO,
    erro: null,
    noServidor: true,
    s3_path: f.s3_path,
  }));

  const nomesNoServidor = new Set(jaNoServidor.map((f) => String(f.nome).toLowerCase()));
  const emCurso = (Array.isArray(lote) ? lote : []).filter(
    (i) => !(i.estado === ENVIADO && nomesNoServidor.has(String(i.nome).toLowerCase())),
  );

  return [...jaNoServidor, ...emCurso.map((i) => ({ ...i, noServidor: false }))];
}
