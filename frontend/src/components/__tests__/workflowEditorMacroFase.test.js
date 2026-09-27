/**
 * Guarda: o grupo do funil é uma lista FECHADA na UI.
 *
 * ÉPICO 10, PARTE 2.
 *   O administrador classifica cada fase do workflow num dos cinco
 *   grupos do funil. Se o campo fosse texto livre, um `aprovdo` criava
 *   um grupo novo de um só processo, com ar de categoria legítima, e o
 *   funil partia-se sem erro nenhum — a lição do Campo de Rede (Lote 5,
 *   ponto 2).
 *
 *   O backend recusa ao gravar (enum `MacroFase` no Pydantic). A UI tem
 *   de recusar ANTES, senão o utilizador só descobre no submit.
 *
 * Este ficheiro afirma sobre o CÓDIGO-FONTE de propósito: o que
 * interessa é que não existe um caminho de texto livre, e um teste de
 * render só prova o caminho que ele próprio exercita.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { MACRO_FASES } from "../../utils/funilDeFases";

const AQUI = dirname(fileURLToPath(import.meta.url));

const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const EDITOR = semComentarios(
  readFileSync(join(AQUI, "..", "WorkflowEditor.js"), "utf8"),
);

const AS_CINCO = ["novo", "analise", "aprovado", "concluido", "perdido"];

const opcoesDoEditor = () => {
  const bloco = EDITOR.match(/const macroFaseOptions = \[([\s\S]*?)\];/);
  expect(bloco, "`macroFaseOptions` mudou de forma").toBeTruthy();
  return [...bloco[1].matchAll(/value:\s*"([^"]+)"/g)].map((m) => m[1]);
};

describe("O grupo do funil é uma lista fechada", () => {
  it("o editor oferece exactamente as cinco macro-fases", () => {
    expect(opcoesDoEditor()).toEqual(AS_CINCO);
  });

  it("os grupos do funil são os mesmos do editor", () => {
    // Duas listas nos dois lados do mesmo ecrã: divergirem significa
    // classificar numa fase e o funil não a reconhecer.
    expect(MACRO_FASES.map((g) => g.key)).toEqual(AS_CINCO);
  });

  it("o campo é um Select, não um Input de texto", () => {
    const campo = EDITOR.slice(
      EDITOR.indexOf("const renderMacroFaseField"),
      EDITOR.indexOf("const renderAutomationTriggersSection"),
    );
    expect(campo).toContain("<Select");
    expect(campo).not.toMatch(/<Input/);
    expect(campo).not.toMatch(/<Textarea/);
  });

  it("existe a opção de não classificar", () => {
    // `null` é uma resposta: a fase cai em «Outras fases», com o nome à
    // vista. Obrigar a escolher seria obrigar a inventar.
    expect(EDITOR).toContain("SEM_MACRO_FASE");
    expect(EDITOR).toMatch(/Sem grupo/);
  });

  it("não classificar envia vazio, não a chave interna", () => {
    // `__sem_grupo__` é um detalhe do Radix (que não aceita `value=""`).
    // Se escapasse para o payload, o backend recusava-o pelo enum.
    const campo = EDITOR.slice(
      EDITOR.indexOf("const renderMacroFaseField"),
      EDITOR.indexOf("const renderAutomationTriggersSection"),
    );
    expect(campo).toContain('value === SEM_MACRO_FASE ? "" : value');
  });
});

describe("Contraprova: o campo chega mesmo ao servidor", () => {
  it("vai nos dois payloads, criar e actualizar", () => {
    expect(EDITOR).toContain("macro_fase: formData.macro_fase || undefined");
    expect(EDITOR).toContain("macro_fase: formData.macro_fase || null");
  });

  it("a edição hidrata o campo a partir da fase carregada", () => {
    // Sem isto, abrir uma fase classificada mostrava "Sem grupo" e
    // gravar apagava a classificação.
    expect(EDITOR).toContain('macro_fase: status.macro_fase || ""');
  });

  it("o formulário limpo parte sem grupo", () => {
    const ocorrencias = EDITOR.match(/macro_fase: ""/g) || [];
    expect(ocorrencias.length).toBeGreaterThanOrEqual(2);
  });
});
