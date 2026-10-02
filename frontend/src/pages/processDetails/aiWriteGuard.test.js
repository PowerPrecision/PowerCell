/**
 * Guarda: a IA nunca escreve na ficha sem o consultor confirmar.
 *
 * A REGRA
 *   "A IA nunca escreve na base de dados (dados pessoais/financeiros) sem
 *   a confirmação do utilizador."
 *
 * O DEFEITO QUE ISTO FECHA
 *   `commitAIExtractedData` (análise em LOTE) abria o diálogo de revisão
 *   quando havia conflitos e, quando não havia, chamava directamente
 *   `persistAISuggestions` → `POST /ai-apply-suggestions`. Uma escrita,
 *   sem diálogo nenhum.
 *
 *   E "sem conflitos" não é o caso benigno: um conflito só existe quando a
 *   ficha JÁ TEM outro valor. Ficha vazia = zero conflitos = tudo o que a
 *   IA leu entrava de uma vez, sem ninguém ver.
 *
 * PORQUÊ SOBRE O CÓDIGO-FONTE
 *   O caminho perigoso é um `else` dentro de um componente de 2900 linhas.
 *   Um teste de comportamento que o exercitasse teria de montar a página,
 *   simular a análise e adivinhar o estado; esta afirmação é directa e
 *   falha no instante em que alguém reintroduz a escrita.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));
const FONTE = readFileSync(join(AQUI, "..", "ProcessDetails.js"), "utf8");

/**
 * Remove comentários antes de procurar padrões.
 *
 * Sem isto, a explicação de porque a escrita directa saiu daqui fazia o
 * próprio guarda ficar vermelho — e a saída óbvia seria apagar a
 * explicação, que é a parte que impede a regressão de voltar.
 */
const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const CODIGO = semComentarios(FONTE);

/** Linhas que INVOCAM `persistAISuggestions` (a definição não conta). */
const invocacoes = CODIGO.split("\n")
  .map((linha, i) => ({ linha: linha.trim(), numero: i + 1 }))
  .filter(
    ({ linha }) =>
      linha.includes("persistAISuggestions(") &&
      !linha.includes("const persistAISuggestions"),
  );

describe("A escrita da IA na ficha", () => {
  it("é chamada a partir de um único sítio", () => {
    assert.equal(
      invocacoes.length,
      1,
      `persistAISuggestions é invocado em ${invocacoes.length} sítios ` +
        `(linhas ${invocacoes.map((i) => i.numero).join(", ")}). ` +
        "A escrita só pode partir da confirmação do consultor.",
    );
  });

  it("esse sítio é o handler de confirmação do diálogo", () => {
    const [invocacao] = invocacoes;
    assert.ok(invocacao, "nenhuma invocação encontrada");

    // Procurar, para trás, qual a última declaração de função antes da
    // invocação: é o handler dentro do qual ela vive.
    const antes = CODIGO.split("\n").slice(0, invocacao.numero);
    const declaracoes = antes
      .join("\n")
      .match(/const\s+(\w+)\s*=\s*(?:useCallback\()?\s*(?:async\s*)?\(/g);
    const ultima = declaracoes?.[declaracoes.length - 1] || "";

    assert.match(
      ultima,
      /handleConfirmAIReview/,
      `A escrita vive em "${ultima.trim()}" e não em handleConfirmAIReview. ` +
        "Só a confirmação explícita do consultor pode gravar.",
    );
  });

  it("a análise em lote não tem um ramo que grave sem revisão", () => {
    // A forma exacta do defeito: `if (conflitos) abrir diálogo; else gravar`.
    const commit = CODIGO.slice(
      CODIGO.indexOf("const commitAIExtractedData"),
      CODIGO.indexOf("const handleDocumentDataExtracted"),
    );
    assert.ok(commit.length > 0, "commitAIExtractedData não encontrado");
    assert.ok(
      !commit.includes("persistAISuggestions("),
      "commitAIExtractedData volta a gravar directamente na ficha.",
    );
  });

  it("a revisão é sempre levantada em qualquer extracção em lote", () => {
    // LEGADO ACTUALIZADO (Lote 3, ponto 1): a revisão deixou de ser um
    // diálogo sobreposto e passou a ser PREENCHIMENTO EM LINHA. O que este
    // teste afirmava — «setShowAIReviewDialog(true)» — era o mecanismo, não
    // a propriedade. A propriedade é a mesma e continua afirmada: QUALQUER
    // extracção levanta revisão, com ou sem conflitos.
    const commit = CODIGO.slice(
      CODIGO.indexOf("const commitAIExtractedData"),
      CODIGO.indexOf("const handleDocumentDataExtracted"),
    );
    assert.ok(
      commit.includes("setSugestoesIA(criarSugestoes(revisao))"),
      "a extracção em lote não levanta sugestões para revisão",
    );

    // A afirmação que interessa é a AUSÊNCIA do ramo: a versão original
    // deste teste procurava só a abertura do diálogo — que JÁ existia dentro
    // do `if (conflicts.length > 0)`. Passava com o defeito presente, e um
    // teste assim é pior do que não existir.
    assert.ok(
      !/conflicts\s*&&\s*conflicts\.length\s*>\s*0/.test(commit),
      "A revisão voltou a depender de haver conflitos. " +
        "Sem conflitos é justamente o caso em que a ficha está vazia e " +
        "tudo o que a IA leu vai entrar.",
    );
  });

  it("um campo PENDENTE não entra no que se grava", () => {
    // A regra de ouro no mecanismo novo: o input já desenha o valor
    // sugerido, e é `valoresAprovados` que decide o que vai no payload.
    // Se a gravação passasse a usar `extractedData` outra vez, a interface
    // ficava igual e a regra desaparecia sem deixar rasto.
    const confirmar = CODIGO.slice(
      CODIGO.indexOf("const handleConfirmAIReview"),
      CODIGO.indexOf("const decidirSugestao"),
    );
    assert.ok(confirmar.length > 0, "handleConfirmAIReview não encontrado");
    assert.ok(
      confirmar.includes("valoresAprovados("),
      "a gravação deixou de partir das sugestões APROVADAS",
    );
    assert.ok(
      !/persistAISuggestions\(\s*extractedData/.test(confirmar),
      "a gravação voltou a enviar tudo o que a IA leu, e não só o aprovado",
    );
  });

  it("aprovar/rejeitar não grava — só muda o estado da sugestão", () => {
    const decidir = CODIGO.slice(
      CODIGO.indexOf("const decidirSugestao"),
      CODIGO.indexOf("const handleAprovarSugestao"),
    );
    assert.ok(decidir.length > 0, "decidirSugestao não encontrado");
    assert.ok(
      !decidir.includes("persistAISuggestions("),
      "a decisão por campo passou a gravar directamente",
    );
  });

  it("os dados só são aplicados ao formulário na confirmação", () => {
    // Pré-preencher antes da revisão não grava na BD, mas mostra ao
    // consultor uma ficha já alterada por baixo do diálogo que ele ainda
    // não aceitou — e basta carregar em Guardar para a tornar real.
    const commit = CODIGO.slice(
      CODIGO.indexOf("const commitAIExtractedData"),
      CODIGO.indexOf("const handleDocumentDataExtracted"),
    );
    assert.ok(
      !commit.includes("applyPersonalAndFinancialToTitular("),
      "Dados pessoais/financeiros aplicados ao formulário antes da revisão.",
    );
  });
});
