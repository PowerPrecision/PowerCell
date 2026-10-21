/**
 * Pré-visualização de ficheiros na gaveta de detalhes da lead — regras PURAS.
 *
 * O servidor é a autoridade: a lista de ficheiros traz `previsualizavel` (tem `file_id` e um tipo que
 * sabe servir) e o `Content-Type` sai SEMPRE da extensão do lado dele, não do bucket. Esta tabela só
 * diz ao ecrã COMO desenhar (`<img>` ou `<iframe>`) e é mantida igual à do servidor — há um teste que
 * lê a tabela do Python e compara (duas listas de extensões divergem sem dar erro).
 */

/** Extensão → tipo e forma de desenho. Igual a `TIPOS_COM_PREVISUALIZACAO` do servidor. */
export const TIPOS_COM_PREVISUALIZACAO = {
  ".pdf": { mime: "application/pdf", forma: "pdf" },
  ".png": { mime: "image/png", forma: "imagem" },
  ".jpg": { mime: "image/jpeg", forma: "imagem" },
  ".jpeg": { mime: "image/jpeg", forma: "imagem" },
  ".webp": { mime: "image/webp", forma: "imagem" },
  ".gif": { mime: "image/gif", forma: "imagem" },
};

/** `{mime, forma}` para um nome de ficheiro, ou `null` se não há pré-visualização. */
export function tipoDaPrevisualizacao(nome) {
  const texto = typeof nome === "string" ? nome.toLowerCase() : "";
  const extensao = Object.keys(TIPOS_COM_PREVISUALIZACAO).find((e) => texto.endsWith(e));
  return extensao ? TIPOS_COM_PREVISUALIZACAO[extensao] : null;
}

/**
 * O ficheiro tem botão «Visualizar»? Manda o servidor (`previsualizavel`); só um servidor anterior,
 * que não envia o campo, cai na extensão — e mesmo assim exige `file_id` (sem ele não há como pedir).
 */
export function podePrevisualizar(ficheiro) {
  if (!ficheiro || typeof ficheiro !== "object" || !ficheiro.file_id) return false;
  if (typeof ficheiro.previsualizavel === "boolean") return ficheiro.previsualizavel && tipoDaPrevisualizacao(ficheiro.filename) !== null;
  return tipoDaPrevisualizacao(ficheiro.filename) !== null;
}

/** O que dizer quando o servidor recusa: o motivo dele quando existe, senão um por código. */
export function mensagemDaFalhaDePrevisualizacao(estado, detail) {
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (estado === 413) return "O ficheiro é demasiado grande para pré-visualizar.";
  if (estado === 415) return "Este tipo de ficheiro não tem pré-visualização.";
  if (estado === 404) return "O ficheiro já não está disponível.";
  if (estado === 403) return "Sem permissão para ver este ficheiro.";
  return "Não foi possível carregar a pré-visualização.";
}
