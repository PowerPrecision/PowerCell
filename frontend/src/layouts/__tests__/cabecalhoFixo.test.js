/**
 * Guarda: o cabeçalho do CRM está ligado à regra do sticky (Lote 4, ponto 4).
 *
 * PORQUÊ SOBRE O CÓDIGO-FONTE
 * O `DashboardLayout` tem 940 linhas, exige `AuthContext`, WebSocket,
 * React Query e um router para montar — e, ainda que o montássemos, o
 * jsdom **não calcula posicionamento**: um `sticky` que cola e um que não
 * cola renderizam exactamente o mesmo. Não há teste de comportamento
 * capaz de distinguir o defeito. O que se pode afirmar é a LIGAÇÃO: que
 * o cabeçalho deriva as classes do ponto único, cuja regra tem testes
 * próprios em `utils/stickyHeader.test.js`.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { classesDoCabecalhoFixo } from "../../utils/stickyHeader";

const AQUI = dirname(fileURLToPath(import.meta.url));
const FONTE = readFileSync(join(AQUI, "..", "DashboardLayout.js"), "utf8");

/** Sem comentários: senão a explicação do defeito faz o guarda vermelho. */
const CODIGO = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(
  /(^|[^:])\/\/.*$/gm,
  "$1",
);

describe("O cabeçalho fixo do CRM", () => {
  it("deriva as classes do ponto único", () => {
    assert.ok(
      CODIGO.includes("classesDoCabecalhoFixo({ isImpersonating })"),
      "o <header> tem de chamar classesDoCabecalhoFixo — uma lista de " +
        "classes escrita à mão aqui é como o `top` se perdeu.",
    );
  });

  it("não volta a escrever as classes de posição à mão", () => {
    // A string exacta do defeito: `sticky` sem `top` ao lado.
    assert.ok(
      !/className="[^"]*\bsticky\b[^"]*"/.test(CODIGO),
      "há um `sticky` numa lista de classes literal dentro do layout; " +
        "as classes de posição do cabeçalho vivem em utils/stickyHeader.js.",
    );
  });

  it("não tem um `top` em linha para o cabeçalho", () => {
    // Era o `style={{ top: '48px' }}` que fazia a impersonação ser o
    // único caminho em que o cabeçalho colava — e, sendo o caso raro,
    // foi provavelmente o único em que alguém o viu a funcionar.
    assert.ok(
      !CODIGO.includes("headerStyle"),
      "o `headerStyle` em linha voltou; o deslocamento da faixa de " +
        "impersonação é agora uma classe do ponto único.",
    );
  });

  it("CONTRAPROVA: o ponto único devolve mesmo um `top`", () => {
    // Sem esta, apagar o `top` dentro do helper satisfazia os três
    // testes acima — o layout continuaria a chamar uma função correcta
    // no nome e vazia no efeito.
    for (const isImpersonating of [false, true]) {
      const classes = classesDoCabecalhoFixo({ isImpersonating }).split(/\s+/);
      assert.ok(
        classes.some((c) => /^top-/.test(c)),
        `classesDoCabecalhoFixo({isImpersonating: ${isImpersonating}}) não tem top-*`,
      );
      assert.ok(classes.includes("sticky"));
    }
  });

  it("a gaveta lateral continua a ter o seu próprio deslocamento", () => {
    // O cabeçalho e a gaveta descem os mesmos 48px na impersonação, por
    // caminhos diferentes (classe vs style). Se um dia um deles mudar, o
    // outro não vem atrás — fica afirmado que a gaveta ainda o declara.
    assert.ok(CODIGO.includes("impersonateOffset"));
  });
});
