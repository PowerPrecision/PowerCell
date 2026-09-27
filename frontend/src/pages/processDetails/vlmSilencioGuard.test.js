/**
 * Guarda: a análise em lote nunca acaba em silêncio ("VLM no Escuro").
 *
 * O DEFEITO QUE ISTO FECHA
 *   Clicar em "Analisar Documentos" processava e não devolvia NADA à UI:
 *   toast verde "Análise completa! 3 documento(s) processado(s)" e o
 *   Diálogo de Revisão Humana calado. Sem erro, sem aviso, sem nada para
 *   dizer ao suporte.
 *
 *   Dois sítios, a mesma confusão entre "não há nada a preencher" e "a IA
 *   nem chegou a ler":
 *
 *   1. `S3FileManager`: `if (onAIDataExtracted && result.extracted_data)`.
 *      `{}` é TRUTHY em JavaScript, logo um resultado vazio passava a
 *      porta, seguia para o pai e apanhava o toast verde logo a seguir.
 *   2. `ProcessDetails.commitAIExtractedData`: um `return` mudo à cabeça
 *      e um `if (revisao) { … }` sem `else`.
 *
 * PORQUÊ SOBRE O CÓDIGO-FONTE
 *   O comportamento certo é a AUSÊNCIA de um caminho — um desfecho sem
 *   palavra nenhuma. Um teste de comportamento prova que os três
 *   desfechos falam (isso é `utils/analiseEmLoteFeedback.test.js`); só
 *   uma afirmação sobre o código prova que não sobrou um quarto caminho
 *   calado dentro de um componente de 2900 linhas.
 *
 * CONTRAPROVA
 *   Cada proibição tem ao lado a afirmação de que o sítio certo faz mesmo
 *   a coisa certa — sem ela, apagar a chamada satisfazia o guarda.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));

/**
 * Remove comentários antes de procurar padrões — senão a explicação do
 * defeito (que cita o código antigo) faria o guarda ficar vermelho, e a
 * saída óbvia seria apagar a explicação.
 */
const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const ler = (...partes) => semComentarios(readFileSync(join(AQUI, ...partes), "utf8"));

const S3_FILE_MANAGER = ler("..", "..", "components", "S3FileManager.js");
const PROCESS_DETAILS = ler("..", "ProcessDetails.js");

describe("S3FileManager — o objecto vazio deixou de ser um sinal de dados", () => {
  it("não volta a usar `result.extracted_data` como porta de entrada", () => {
    expect(S3_FILE_MANAGER).not.toMatch(
      /if\s*\(\s*onAIDataExtracted\s*&&\s*result\.extracted_data\s*\)/,
    );
  });

  it("contraprova: a porta existe e é só o callback", () => {
    expect(S3_FILE_MANAGER).toMatch(/if\s*\(\s*onAIDataExtracted\s*\)/);
  });

  it("encaminha o que a IA leu mesmo, e não só o que foi enviado", () => {
    // Sem estes dois campos o pai não consegue distinguir os desfechos,
    // por muito que saiba dizê-los.
    expect(S3_FILE_MANAGER).toContain("documentsSucceeded: result.documents_succeeded");
    expect(S3_FILE_MANAGER).toContain("documentsFailed: result.documents_failed");
  });

  it("deixou de celebrar por conta própria", () => {
    // Duas vozes sobre o mesmo evento davam um verde por cima de um
    // diálogo que nunca abriu. Quem sabe se sobrou algo a rever é o pai.
    expect(S3_FILE_MANAGER).not.toMatch(/toast\.success\(`Análise completa!/);
  });
});

describe("ProcessDetails — todos os desfechos têm palavra", () => {
  const corpo = (() => {
    const inicio = PROCESS_DETAILS.indexOf("const commitAIExtractedData");
    expect(inicio).toBeGreaterThan(-1);
    const fim = PROCESS_DETAILS.indexOf("const handleDocumentDataExtracted", inicio);
    expect(fim).toBeGreaterThan(inicio);
    return PROCESS_DETAILS.slice(inicio, fim);
  })();

  it("o caminho em lote anuncia o desfecho", () => {
    expect(corpo).toContain("resumirAnaliseEmLote");
  });

  it("o ramo sem revisão deixou de ser mudo", () => {
    // `if (revisao) { … }` sem `else` era o segundo silêncio.
    expect(corpo).toMatch(/dizerODesfecho\(\s*!!revisao\s*\)/);
  });

  it("a entrada vazia também fala antes de desistir", () => {
    expect(corpo).toMatch(/dizerODesfecho\(\s*false\s*\)[\s\S]{0,40}return;/);
  });

  it("contraprova: o diálogo de revisão continua a abrir quando há o que rever", () => {
    // Uma guarda que só exigisse mensagens seria satisfeita por um
    // componente que nunca mostrasse nada.
    expect(corpo).toContain("setShowAIReviewDialog(true)");
  });
});
