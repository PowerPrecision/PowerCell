/**
 * Que grupos do menu lateral estão abertos (QA Index, Out 2026).
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  CHAVE_DE_ARMAZENAMENTO,
  abrirSeccoes,
  gravarSeccoesAbertas,
  lerSeccoesAbertas,
  seccoesComRotaActiva,
} from "./seccoesDoMenu";

const GRUPOS = [
  { id: "meu-negocio", items: [{ href: "/index" }, { href: "/kanban" }, { href: "/validades" }] },
  { id: "visao-global", items: [{ href: "/clientes" }, { href: "/lista-processos" }] },
  { id: "comunicacoes", items: [{ href: "/ficheiros" }] },
];

describe("seccoesComRotaActiva", () => {
  it("o grupo que contém a ligação da rota abre-se", () => {
    expect(seccoesComRotaActiva(GRUPOS, "/index")).toEqual(["meu-negocio"]);
    expect(seccoesComRotaActiva(GRUPOS, "/ficheiros")).toEqual(["comunicacoes"]);
  });

  it("as rotas do Index (/index, /validades) já não ficam de fora — era o defeito", () => {
    expect(seccoesComRotaActiva(GRUPOS, "/validades")).toEqual(["meu-negocio"]);
  });

  it("uma rota filha abre o grupo do pai (/index/:processo)", () => {
    expect(seccoesComRotaActiva(GRUPOS, "/index/p-123")).toEqual(["meu-negocio"]);
    expect(seccoesComRotaActiva(GRUPOS, "/clientes/c-1")).toEqual(["visao-global"]);
  });

  it("o prefixo de TEXTO não conta: /indexacao-x não é filha de /index", () => {
    expect(seccoesComRotaActiva(GRUPOS, "/indexacao-x")).toEqual([]);
    expect(seccoesComRotaActiva(GRUPOS, "/clientes-antigos")).toEqual([]);
  });

  it("uma rota fora do menu não abre nada", () => {
    expect(seccoesComRotaActiva(GRUPOS, "/perfil")).toEqual([]);
  });

  it.each([undefined, null, "x", 3, {}])("dados que não são uma lista (%s) não rebentam", (g) => {
    expect(seccoesComRotaActiva(g, "/index")).toEqual([]);
  });

  it("grupos e itens mal formados são ignorados", () => {
    const sujo = [null, { id: "a" }, { items: [{ href: "/index" }] }, { id: "b", items: [null, {}, { href: "/index" }] }];
    expect(seccoesComRotaActiva(sujo, "/index")).toEqual(["b"]);
  });

  it("pathname que não é texto não rebenta", () => {
    expect(seccoesComRotaActiva(GRUPOS, undefined)).toEqual([]);
  });
});

describe("armazenamento", () => {
  beforeEach(() => sessionStorage.clear());

  it("o que se gravou lê-se", () => {
    gravarSeccoesAbertas({ "meu-negocio": true, comunicacoes: false });
    expect(lerSeccoesAbertas()).toEqual({ "meu-negocio": true, comunicacoes: false });
  });

  it("sem nada gravado é um objecto vazio", () => {
    expect(lerSeccoesAbertas()).toEqual({});
  });

  it.each(["{ não é json", "[1,2]", "null", '"texto"', "42"])("lixo (%s) vale como nada", (bruto) => {
    sessionStorage.setItem(CHAVE_DE_ARMAZENAMENTO, bruto);
    expect(lerSeccoesAbertas()).toEqual({});
  });

  it("só valores booleanos sobrevivem", () => {
    sessionStorage.setItem(CHAVE_DE_ARMAZENAMENTO, JSON.stringify({ a: true, b: "sim", c: 1, d: false }));
    expect(lerSeccoesAbertas()).toEqual({ a: true, d: false });
  });

  it("um armazenamento que falha nunca rebenta (janela privada)", () => {
    const quebrado = {
      getItem() {
        throw new Error("bloqueado");
      },
      setItem() {
        throw new Error("bloqueado");
      },
    };
    expect(lerSeccoesAbertas(quebrado)).toEqual({});
    expect(() => gravarSeccoesAbertas({ a: true }, quebrado)).not.toThrow();
  });
});

describe("abrirSeccoes", () => {
  it("junta os grupos a abrir sem tocar nos outros", () => {
    expect(abrirSeccoes({ a: false, b: true }, ["a", "c"])).toEqual({ a: true, b: true, c: true });
  });

  it("devolve o MESMO objecto quando nada mudou (sem re-render)", () => {
    const antes = { a: true };
    expect(abrirSeccoes(antes, ["a"])).toBe(antes);
    expect(abrirSeccoes(antes, [])).toBe(antes);
  });

  it("nunca fecha: o que a pessoa abriu fica", () => {
    expect(abrirSeccoes({ a: true }, ["b"]).a).toBe(true);
  });
});

describe("seccoesComRotaActiva — rotas que pertencem a uma ligação (`tambem`)", () => {
  const grupos = [
    { id: "trabalho", items: [{ href: "/processos", tambem: ["/index"] }, { href: "/kanban" }] },
    { id: "outro", items: [{ href: "/clientes" }] },
  ];

  it("a bancada do Index (/index/:id) abre o grupo de «Os Meus Processos»", () => {
    expect(seccoesComRotaActiva(grupos, "/index/abc")).toEqual(["trabalho"]);
    expect(seccoesComRotaActiva(grupos, "/index")).toEqual(["trabalho"]);
  });

  it("sem `tambem` a rota não pertence a nenhum grupo (contraprova)", () => {
    expect(seccoesComRotaActiva([{ id: "g", items: [{ href: "/processos" }] }], "/index/abc")).toEqual([]);
  });

  it("um prefixo parecido não conta (/indexar não é /index)", () => {
    expect(seccoesComRotaActiva(grupos, "/indexar")).toEqual([]);
  });

  it("`tambem` mal formado é ignorado", () => {
    expect(seccoesComRotaActiva([{ id: "g", items: [{ href: "/a", tambem: "/index" }] }], "/index")).toEqual([]);
  });
});
