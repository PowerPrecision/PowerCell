/**
 * Contactos sugeridos ao escrever o destinatário (Bloco 2, Lote 12).
 *
 * Os campos Para/CC/BCC são TEXTO LIVRE com vários endereços separados por
 * vírgula ou ponto e vírgula. A sugestão incide sobre o ÚLTIMO pedaço — o que
 * a pessoa está a escrever agora — e escolher um contacto substitui só esse
 * pedaço, nunca o campo inteiro.
 *
 * Puro de propósito: sem estado, sem rede. O servidor decide o que é um
 * contacto (e de que empresa); aqui só se mexe em texto.
 */

const SEPARADORES = /[,;]/;

/** O pedaço que está a ser escrito (depois do último separador), aparado. */
export const ultimoToken = (valor) => {
  const texto = typeof valor === "string" ? valor : "";
  const partes = texto.split(SEPARADORES);
  return (partes[partes.length - 1] || "").trim();
};

/** Os endereços JÁ escritos (tudo menos o último pedaço), em minúsculas. */
export const enderecosJaEscritos = (valor) => {
  const texto = typeof valor === "string" ? valor : "";
  const partes = texto.split(SEPARADORES);
  partes.pop();
  return partes
    .map((p) => {
      const m = p.match(/<([^>]+)>/);
      return (m ? m[1] : p).trim().toLowerCase();
    })
    .filter(Boolean);
};

/** Substitui o último pedaço pelo endereço escolhido e deixa pronto para o seguinte. */
export const substituirUltimoToken = (valor, endereco) => {
  const texto = typeof valor === "string" ? valor : "";
  const fim = Math.max(texto.lastIndexOf(","), texto.lastIndexOf(";"));
  const antes = fim >= 0 ? texto.slice(0, fim + 1).trimEnd() : "";
  return `${antes ? `${antes} ` : ""}${endereco}, `;
};

/** Sugestões válidas: uma lista (nunca `|| []`), sem as que já estão no campo. */
export const sugestoesParaOCampo = (contactos, valor) => {
  const lista = Array.isArray(contactos) ? contactos.filter((c) => c && c.address) : [];
  const ja = new Set(enderecosJaEscritos(valor));
  return lista.filter((c) => !ja.has(String(c.address).toLowerCase()));
};

/** «Ana Costa <ana@x.pt>» ou só o endereço, para mostrar. */
export const rotuloDoContacto = (contacto) =>
  contacto?.name ? `${contacto.name} <${contacto.address}>` : String(contacto?.address || "");
