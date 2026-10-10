import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAVE_DA_SESSAO,
  EVENTO_SESSAO_EXPIRADA,
  anunciarSessaoExpirada,
  guardarSessao,
  lerSessao,
  lerToken,
  limparSessao,
} from "./partnerSession";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("a sessão do parceiro", () => {
  it("guarda e lê o token, com a data em que expira", () => {
    expect(guardarSessao("tok-1", 3600, 1_000)).toBe(true);
    expect(lerSessao(2_000)).toEqual({ token: "tok-1", expiraEm: 1_000 + 3_600_000 });
  });

  it("lerToken usa o relógio real", () => {
    guardarSessao("tok-2", 3600);
    expect(lerToken()).toBe("tok-2");
  });

  it("vive em sessionStorage e NUNCA em localStorage (morre com o separador)", () => {
    guardarSessao("tok-1", 3600);
    expect(sessionStorage.getItem(CHAVE_DA_SESSAO)).toContain("tok-1");
    expect(localStorage.getItem(CHAVE_DA_SESSAO)).toBeNull();
  });

  it("não usa a chave do token do staff", () => {
    guardarSessao("tok-1", 3600);
    expect(CHAVE_DA_SESSAO).not.toMatch(/^(token|access_token|authToken)$/);
    expect(localStorage.getItem("token")).toBeNull();
    expect(sessionStorage.getItem("token")).toBeNull();
  });

  it("uma sessão já expirada conta como nenhuma — e é apagada", () => {
    guardarSessao("tok-1", 10, 1_000);
    expect(lerSessao(1_000 + 10_000)).toBeNull();
    expect(sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull();
  });

  it("sem tempo de vida conhecido o token vale até ser recusado pelo servidor", () => {
    guardarSessao("tok-1", undefined);
    expect(lerSessao(9e15)).toEqual({ token: "tok-1", expiraEm: null });
  });

  it.each([["não-é-json"], ['{"token":""}'], ['{"token":42}'], ["null"], ["[]"]])(
    "um valor corrompido (%s) lê-se como «sem sessão», nunca como erro",
    (bruto) => {
      sessionStorage.setItem(CHAVE_DA_SESSAO, bruto);
      expect(lerSessao()).toBeNull();
    }
  );

  it("limpar apaga", () => {
    guardarSessao("tok-1", 3600);
    limparSessao();
    expect(lerToken()).toBeNull();
  });

  it("sem token não guarda nada", () => {
    expect(guardarSessao("", 3600)).toBe(false);
    expect(guardarSessao(null, 3600)).toBe(false);
  });

  it("um armazenamento que recusa (modo privado) não rebenta o ecrã: dá «sem sessão»", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("bloqueado", "SecurityError");
    });
    expect(guardarSessao("tok-1", 3600)).toBe(false);
    expect(lerToken()).toBeNull();
    expect(() => limparSessao()).not.toThrow();
  });

  it("a expiração limpa o token e avisa a árvore do parceiro", () => {
    guardarSessao("tok-1", 3600);
    const ouvinte = vi.fn();
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, ouvinte);
    anunciarSessaoExpirada();
    window.removeEventListener(EVENTO_SESSAO_EXPIRADA, ouvinte);
    expect(ouvinte).toHaveBeenCalledTimes(1);
    expect(lerToken()).toBeNull();
  });
});
