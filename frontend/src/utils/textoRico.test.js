import { describe, it, expect } from 'vitest';
import { pareceHtml, textoSimplesParaHtml } from './textoRico';

describe('pareceHtml', () => {
  it.each([
    ['<p>x</p>', true],
    ['texto<br>mais', true],
    ['<strong>x</strong>', true],
    ['<br/>', true],
    ['sem etiquetas', false],
    ['a < b e c > d', false],
    ['1 <2 e 3> 1', false],
    ['{{NOME}}', false],
    ['', false],
    [null, false],
    [undefined, false],
    [42, false],
  ])('%j → %s', (entrada, esperado) => {
    expect(pareceHtml(entrada)).toBe(esperado);
  });
});

describe('textoSimplesParaHtml', () => {
  it('linha vazia separa parágrafos', () => {
    expect(textoSimplesParaHtml('Um.\n\nDois.')).toBe('<p>Um.</p><p>Dois.</p>');
  });

  it('quebra simples dentro do parágrafo vira <br>', () => {
    expect(textoSimplesParaHtml('Linha a\nLinha b')).toBe('<p>Linha a<br>Linha b</p>');
  });

  it('o modelo por omissão da minuta mantém o título separado do corpo', () => {
    const modelo = 'MINUTA DE EXCLUSIVIDADE\n\nEu, {{NOME}}, venho por este meio.';
    expect(textoSimplesParaHtml(modelo)).toBe('<p>MINUTA DE EXCLUSIVIDADE</p><p>Eu, {{NOME}}, venho por este meio.</p>');
  });

  it('CRLF e várias linhas vazias seguidas contam como um separador', () => {
    expect(textoSimplesParaHtml('A\r\n\r\n\r\n\r\nB')).toBe('<p>A</p><p>B</p>');
  });

  it('escapa o que for marcação sem querer', () => {
    expect(textoSimplesParaHtml('Silva & Filhos, a>b e 1<2')).toBe('<p>Silva &amp; Filhos, a&gt;b e 1&lt;2</p>');
  });

  it('limite assumido: algo com forma de etiqueta (<Lda>) conta como HTML e não se mexe', () => {
    expect(textoSimplesParaHtml('Silva <Lda>')).toBe('Silva <Lda>');
  });

  it('as variáveis passam intactas', () => {
    expect(textoSimplesParaHtml('{{NOME}} e {{NOME_EMPRESA}}')).toBe('<p>{{NOME}} e {{NOME_EMPRESA}}</p>');
  });

  it('HTML que já existe NÃO é tocado nem reescapado', () => {
    const html = '<p>Eu, <strong>{{NOME}}</strong> &amp; outro.</p>';
    expect(textoSimplesParaHtml(html)).toBe(html);
  });

  it('é idempotente', () => {
    const uma = textoSimplesParaHtml('A\nB\n\nC');
    expect(textoSimplesParaHtml(uma)).toBe(uma);
  });

  it.each([[''], ['   \n \n '], [null], [undefined], [7]])('%j → vazio', (entrada) => {
    expect(textoSimplesParaHtml(entrada)).toBe('');
  });
});
