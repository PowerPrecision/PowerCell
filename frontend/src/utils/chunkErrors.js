/**
 * Distinguir um erro de CHUNK de um erro da aplicação (Lote 3, ponto 3).
 *
 * PORQUE É QUE ISTO EXISTE
 * O `LazyChunkErrorBoundary` do `App.js` embrulha TODAS as rotas e decidia
 * com uma lista de sub-cadeias que incluía duas entradas largas demais:
 *
 *     error?.message?.includes("Unexpected token") ||
 *     error?.message?.includes("Script error")
 *
 * `JSON.parse("{isto não é json")` levanta
 * `SyntaxError: Unexpected token 'i', ...`. Ou seja: **qualquer falha de
 * `JSON.parse` em qualquer página era classificada como erro de chunk** e
 * desencadeava um `window.location.replace`. Um defeito de dados passava a
 * recarregar a aplicação, e o erro real nunca chegava ao Sentry.
 *
 * O ERRO QUE ESTAVA POR BAIXO — e que produzia o ECRÃ BRANCO
 * Para tudo o que não fosse chunk, o boundary devolvia
 * `{ hasError: false }`. Um boundary que não muda de estado **não trata o
 * erro**: o React volta a renderizar os mesmos filhos, eles levantam
 * outra vez e, sem nenhuma fronteira a assumir a falha, o React
 * **desmonta a árvore inteira**. O resultado é uma página em branco.
 *
 * Como as rotas têm cada uma o seu `ErrorBoundary`, o que chegava aqui era
 * o que acontece FORA delas: o `DashboardLayout`, os contextos, o
 * `ProtectedRoute`, o próprio router — e a navegação para trás do browser,
 * que volta a montar tudo isso de uma vez.
 *
 * TERCEIRO DEFEITO, no próprio recarregamento
 * O cache-busting era:
 *
 *     pathname + search + (search.includes('?') ? '&' : '?') + '_t=' + Date.now()
 *
 * `window.location.search` **já inclui o `?`**. Logo a segunda passagem dá
 * `/x?_t=1&_t=2`, a terceira `/x?_t=1&_t=2&_t=3` — o comentário dizia que
 * era "para evitar ciclo infinito" e o que fazia era deixar o URL crescer.
 * E `location.replace` **substitui a entrada do histórico**, pelo que o
 * Voltar deixa de levar o utilizador ao sítio onde estava.
 *
 * É puro para se poder afirmar a lista de causas sem montar a aplicação.
 */

/**
 * Sinais INEQUÍVOCOS de um chunk que não carregou.
 *
 * Cada entrada aqui tem de ser específica do carregamento de módulos. Uma
 * sub-cadeia que ocorra em erros comuns da aplicação não pertence a esta
 * lista, por muito que apareça em alguns erros de chunk: o custo de um
 * falso positivo é recarregar a aplicação por cima de um defeito e perder
 * o rasto dele.
 */
export const SINAIS_DE_CHUNK = [
  "Failed to fetch dynamically imported module",
  "error loading dynamically imported module",
  "Loading chunk",
  "Loading CSS chunk",
  "Importing a module script failed",
  // O servidor devolveu HTML onde devia vir JavaScript — o caso clássico do
  // `index.html` em cache a responder a um pedido de um chunk que já não
  // existe. É específico: um erro da aplicação não fala de MIME types.
  "Expected a JavaScript module script but the server responded with a MIME type",
];

/** Nomes/códigos de erro que só aparecem neste cenário. */
export const NOMES_DE_CHUNK = ["ChunkLoadError"];
export const CODIGOS_DE_CHUNK = ["MODULE_NOT_FOUND"];

/**
 * Sub-cadeias que ESTAVAM na lista e saíram, com o motivo. Existe para
 * ficar afirmado em teste que não voltam — cada uma delas classificava
 * erros comuns da aplicação como erros de chunk.
 */
export const SINAIS_REJEITADOS = {
  "Unexpected token": "qualquer JSON.parse falhado levanta esta mensagem",
  "Script error": "é o erro opaco de um script de outra origem, não de um chunk",
  "text/html": "aparece em mensagens de API que devolvem HTML numa resposta de dados",
  "MIME type": "demasiado largo; o sinal específico é a frase completa do módulo",
};

export function eErroDeChunk(erro) {
  if (!erro) return false;
  if (NOMES_DE_CHUNK.includes(erro.name)) return true;
  if (CODIGOS_DE_CHUNK.includes(erro.code)) return true;
  const mensagem = typeof erro.message === "string" ? erro.message : "";
  if (!mensagem) return false;
  return SINAIS_DE_CHUNK.some((sinal) =>
    mensagem.toLowerCase().includes(sinal.toLowerCase()),
  );
}

/**
 * O URL a recarregar, com cache-busting que **não acumula**.
 *
 * Substitui um `_t` que já exista em vez de acrescentar outro, e devolve
 * `null` quando já se recarregou por este motivo — recarregar em ciclo é
 * pior do que mostrar o erro, porque o utilizador não consegue sequer ler
 * o que aconteceu.
 */
export function urlDeRecarregamento(location, { agora = Date.now() } = {}) {
  const pathname = location?.pathname || "/";
  const search = location?.search || "";

  const params = new URLSearchParams(search);
  if (params.has("_t")) {
    // Já viemos de um recarregamento: não insistir.
    return null;
  }
  params.set("_t", String(agora));
  return `${pathname}?${params.toString()}`;
}
