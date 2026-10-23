/**
 * Descarregar um ficheiro que o servidor serve com `Content-Disposition: attachment` — regras PURAS + um
 * pequeno invólucro do DOM (`guardarBlob`).
 *
 * O pedido leva o token (Axios), logo não pode ser uma ligação `<a href>` para a API: os bytes vêm como `Blob`
 * e o ecrã entrega-os ao browser com um `<a download>`. O nome é decidido AQUI quando o browser não deixa ler o
 * `Content-Disposition` do servidor (cabeçalho não exposto no CORS): sai do rótulo do resultado — que nunca
 * leva o nome do cliente — e da extensão do tipo que chegou.
 */

const EXTENSAO_DO_TIPO = Object.freeze({
  "application/pdf": ".pdf",
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
  "image/gif": ".gif",
  "application/msword": ".doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "application/vnd.ms-excel": ".xls",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
  "text/plain": ".txt",
});

const TECTO_DO_NOME = 120;

/** A extensão (`.pdf`) do `Content-Type`, ou `""` quando não se sabe. */
export function extensaoDoTipo(contentType) {
  const mime = typeof contentType === "string" ? contentType.split(";")[0].trim().toLowerCase() : "";
  return EXTENSAO_DO_TIPO[mime] || "";
}

/** Tira o que um sistema de ficheiros não aceita (ou que muda o caminho) e põe um tecto ao comprimento. */
export function sanearNomeDeFicheiro(texto) {
  const limpo = String(texto ?? "")
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f\\/:*?"<>|]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\.+/, "");
  return limpo.slice(0, TECTO_DO_NOME).trim();
}

/**
 * O nome que o servidor deu (`filename*=UTF-8''…` ou `filename="…"`), ou `null`. Só se lê quando o browser
 * expõe o cabeçalho; sem ele `null` e vale o nome gerado.
 */
export function nomeDoCabecalho(disposicao) {
  if (typeof disposicao !== "string" || !disposicao) return null;
  const utf8 = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(disposicao);
  if (utf8) {
    try {
      const nome = sanearNomeDeFicheiro(decodeURIComponent(utf8[1].trim()));
      if (nome) return nome;
    } catch {
      /* percent-encoding inválido: cai no `filename=` */
    }
  }
  const simples = /filename\s*=\s*"([^"]*)"|filename\s*=\s*([^;]+)/i.exec(disposicao);
  const nome = sanearNomeDeFicheiro(simples ? simples[1] ?? simples[2] ?? "" : "");
  return nome || null;
}

/**
 * O nome com que o ficheiro se guarda: o do servidor quando legível, senão o do rótulo — sempre com extensão
 * quando o tipo a dá (um nome sem extensão num PDF obriga o utilizador a adivinhar o programa).
 */
export function nomeDaDescarga({ rotulo, contentType, disposicao } = {}) {
  const doServidor = nomeDoCabecalho(disposicao);
  const extensao = extensaoDoTipo(contentType);
  const base = doServidor || sanearNomeDeFicheiro(rotulo) || "documento";
  if (!extensao || /\.[a-z0-9]{2,5}$/i.test(base)) return base;
  return `${base}${extensao}`;
}

/** Entrega um `Blob` ao browser como descarga. Devolve o nome usado. */
export function guardarBlob(blob, nome, { atrasoParaLibertar = 4000 } = {}) {
  const url = URL.createObjectURL(blob);
  const ligacao = document.createElement("a");
  ligacao.href = url;
  ligacao.download = nome;
  ligacao.rel = "noopener";
  ligacao.style.display = "none";
  document.body.appendChild(ligacao);
  ligacao.click();
  document.body.removeChild(ligacao);
  // libertar logo cancelaria a descarga em alguns browsers (Safari): dá-se tempo, mas liberta-se sempre
  setTimeout(() => URL.revokeObjectURL(url), atrasoParaLibertar);
  return nome;
}

/** O que dizer quando o servidor recusa a descarga: o motivo dele quando existe, senão um por código. */
export function mensagemDaFalhaDeDescarga(estado, detail) {
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (estado === 413) return "O ficheiro é demasiado grande para descarregar por aqui.";
  if (estado === 404) return "O ficheiro já não está disponível.";
  if (estado === 403) return "Sem permissão para descarregar este ficheiro.";
  if (estado === 429) return "Demasiados pedidos. Aguarde um momento e tente de novo.";
  return "Não foi possível descarregar o ficheiro.";
}
