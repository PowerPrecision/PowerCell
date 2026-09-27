/**
 * Remover e repor um utilizador numa PÁGINA em cache (Set 2026).
 *
 * Ficheiro novo em vez de acrescentar ao `organizationAdmin.test.js`
 * porque esse importa de `node:test` (traduzido pelo shim) e código novo
 * importa de `vitest` — é a regra do Épico 6.
 *
 * Estes dois helpers existem porque a página em cache é
 * `{utilizadores, total}` e o código antigo tratava-a como um array. Os
 * casos aqui são os que o teste de componente não alcança: idempotência
 * e o chão do total.
 */
import { describe, expect, it } from "vitest";

import {
  removerUtilizadorDaPagina,
  reporUtilizadorNaPagina,
} from "./organizationAdmin";

const ANA = { id: "u1", name: "Ana Alves" };
const BRUNO = { id: "u2", name: "Bruno Brito" };

const PAGINA = { utilizadores: [ANA, BRUNO], total: 2 };

describe("removerUtilizadorDaPagina", () => {
  it("retira a linha e faz o total descer", () => {
    const fora = removerUtilizadorDaPagina(PAGINA, "u1");
    expect(fora.utilizadores).toEqual([BRUNO]);
    expect(fora.total).toBe(1);
  });

  it("devolve o MESMO objecto quando não há nada a retirar", () => {
    // Identidade, não igualdade: é o que evita re-renderizar as páginas
    // que não mudaram.
    expect(removerUtilizadorDaPagina(PAGINA, "desconhecido")).toBe(PAGINA);
  });

  it("não inventa um total negativo", () => {
    // Um total já dessincronizado (ou a mesma remoção duas vezes) dava
    // "-1 utilizadores" no rodapé com uma subtracção cega.
    const incoerente = { utilizadores: [ANA], total: 0 };
    expect(removerUtilizadorDaPagina(incoerente, "u1").total).toBe(0);
  });

  it("aguenta uma página ainda não carregada", () => {
    expect(removerUtilizadorDaPagina(undefined, "u1")).toBe(undefined);
    expect(removerUtilizadorDaPagina({ total: 0 }, "u1")).toEqual({ total: 0 });
  });
});

describe("reporUtilizadorNaPagina", () => {
  it("repõe por ordem alfabética do nome", () => {
    const sem = removerUtilizadorDaPagina(PAGINA, "u1");
    const reposta = reporUtilizadorNaPagina(sem, ANA);
    expect(reposta.utilizadores.map((u) => u.id)).toEqual(["u1", "u2"]);
    expect(reposta.total).toBe(2);
  });

  it("é idempotente — repor duas vezes não duplica nem infla o total", () => {
    // O "Desfazer" e o `restoreUser()` do ramo de erro podem correr
    // ambos para o mesmo utilizador.
    const uma = reporUtilizadorNaPagina(PAGINA, ANA);
    expect(uma).toBe(PAGINA);
    expect(uma.total).toBe(2);
  });

  it("ignora um utilizador sem id", () => {
    expect(reporUtilizadorNaPagina(PAGINA, { name: "Sem Id" })).toBe(PAGINA);
  });
});
