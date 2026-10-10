/**
 * Texto simples ⇄ HTML do editor rico (Bloco 5, ponto 36).
 *
 * O modelo por omissão da Minuta (e o do RGPD) é TEXTO SIMPLES, com parágrafos
 * separados por linhas vazias e quebras de linha à mão. O `ReactQuill` recebe o
 * valor como HTML: num HTML os `\n` são espaço, pelo que o texto entrava no
 * editor como UM bloco só, a pré-visualização mostrava-o corrido, e o que se
 * guardava era esse bloco único — a quebra de linha perdia-se na primeira
 * edição, antes de o PDF existir.
 *
 * Aqui o texto simples passa a HTML real UMA vez, à entrada. O que já é HTML
 * (tem tags) não se toca: reconvertê-lo duplicaria o escape.
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };

/** True se o texto já tem marcação HTML (uma etiqueta de abertura ou de fecho). */
export function pareceHtml(texto) {
  return typeof texto === 'string' && /<\/?[a-z][a-z0-9]*(\s[^>]*)?\/?>/i.test(texto);
}

function escapar(texto) {
  return texto.replace(/[&<>]/g, (c) => ESCAPES[c]);
}

/**
 * Converte texto simples em HTML de parágrafos: linha vazia separa `<p>`, uma
 * quebra simples vira `<br>`. HTML que já exista fica como está. As variáveis
 * `{{X}}` passam intactas (não têm nenhum carácter escapável).
 *
 * @param {unknown} texto
 * @returns {string}
 */
export function textoSimplesParaHtml(texto) {
  if (typeof texto !== 'string' || texto.trim() === '') return '';
  if (pareceHtml(texto)) return texto;
  return texto
    .replace(/\r\n?/g, '\n')
    .trim()
    .split(/\n\s*\n/)
    .map((paragrafo) => {
      const linhas = paragrafo
        .split('\n')
        .map((linha) => linha.trim())
        .filter(Boolean)
        .map(escapar);
      return linhas.length ? `<p>${linhas.join('<br>')}</p>` : '';
    })
    .filter(Boolean)
    .join('');
}
