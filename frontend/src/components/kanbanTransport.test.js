/**
 * Guarda: o Kanban fala pelo cliente Axios, nunca por `fetch` cru.
 *
 * QUINTA INSTÂNCIA DO INCIDENTE DE 2026-09-21
 *   O interceptor que injecta `X-Company-Id` e `X-Active-Role` vive no
 *   cliente Axios (`services/api.js`). Um `fetch` cru só leva o que lhe
 *   escreverem à mão — e estes três levavam `Authorization` e mais nada.
 *
 * O SINTOMA REPORTADO: utilizadores multi-perfil trocavam de cargo no
 * ContextSwitcher e o quadro não acompanhava. Sem `X-Active-Role` o
 * backend não tinha o que ler; e do outro lado `get_kanban_board` era o
 * único endpoint de listagem a usar `user["role"]` em vez de
 * `get_effective_role`. Duas causas independentes: corrigir só uma não
 * resolvia nada.
 *
 * PORQUÊ SOBRE O CÓDIGO-FONTE
 *   O defeito é a AUSÊNCIA de dois headers num pedido de rede. Um teste
 *   de comportamento teria de falsear o `fetch` e o Axios ao mesmo tempo
 *   e afirmar sobre o que NÃO foi enviado; esta afirmação falha no
 *   instante em que alguém reintroduz o `fetch`.
 *
 * CONTRAPROVA ao lado de cada proibição — sem ela, apagar a chamada
 * satisfazia o guarda.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));

const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const ler = (...partes) => semComentarios(readFileSync(join(AQUI, ...partes), "utf8"));

const FICHEIROS = {
  "useKanbanQuery.js": ler("..", "hooks", "queries", "useKanbanQuery.js"),
  "useKanbanCompletedQuery.js": ler("..", "hooks", "queries", "useKanbanCompletedQuery.js"),
  "KanbanPage.js": ler("..", "pages", "KanbanPage.js"),
};

describe("transporte do Kanban", () => {
  for (const [nome, fonte] of Object.entries(FICHEIROS)) {
    it(`${nome} não chama /processes/kanban por fetch cru`, () => {
      const chamadas = fonte.match(/fetch\([^)]*processes\/kanban[^)]*\)/g) || [];
      expect(chamadas).toEqual([]);
    });

    it(`${nome} escreve headers de contexto à mão em vez de deixar o interceptor`, () => {
      // `X-Company-Id` / `X-Active-Role` escritos à mão são o sinal de
      // que a chamada saiu do Axios — foi assim nas quatro instâncias
      // anteriores deste incidente.
      expect(fonte).not.toMatch(/["']X-Company-Id["']\s*:/);
      expect(fonte).not.toMatch(/["']X-Active-Role["']\s*:/);
    });
  }

  it("contraprova: os três passam mesmo pelo cliente Axios", () => {
    // Sem isto, apagar as chamadas todas satisfazia os testes acima.
    for (const [nome, fonte] of Object.entries(FICHEIROS)) {
      expect(fonte, `${nome} deixou de chamar o Kanban`).toMatch(
        /getKanbanBoard|services\/api/,
      );
    }
  });

  it("contraprova: a função da API existe e aponta ao endpoint certo", () => {
    const api = ler("..", "services", "api.js");
    expect(api).toMatch(/getKanbanBoard[\s\S]{0,200}processes\/kanban/);
  });
});
