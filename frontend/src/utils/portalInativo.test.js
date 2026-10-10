import { beforeEach, describe, expect, it } from "vitest";
import {
  CHAVES_DA_SESSAO_DO_PORTAL,
  CODIGO_PORTAL_INATIVO,
  MENSAGEM_PORTAL_INATIVO,
  eBloqueioDoPortal,
  limparSessaoDoPortal,
  mensagemDoBloqueio,
} from "./portalInativo";

const corpo = (detail) => ({ detail });
const BLOQUEIO = corpo({ codigo: CODIGO_PORTAL_INATIVO, mensagem: "Processo concluído." });

describe("eBloqueioDoPortal", () => {
  it("só o 403 com o código do servidor é um bloqueio", () => {
    expect(eBloqueioDoPortal(403, BLOQUEIO)).toBe(true);
  });

  it.each([
    [401, BLOQUEIO],
    [404, BLOQUEIO],
    [429, BLOQUEIO],
    [500, BLOQUEIO],
  ])("o estado %s nunca é bloqueio, mesmo com o código", (status, c) => {
    expect(eBloqueioDoPortal(status, c)).toBe(false);
  });

  it.each([
    ["sem corpo", undefined],
    ["corpo nulo", null],
    ["detail em texto (403 de outra causa)", corpo("Este token não tem permissão para aceder ao portal.")],
    ["detail com outro código", corpo({ codigo: "outra_coisa" })],
    ["detail sem código", corpo({ mensagem: "x" })],
    ["detail nulo", corpo(null)],
    ["corpo em texto", "portal_inativo"],
  ])("um 403 com %s NÃO é bloqueio (o ecrã decide pelo código, não pelo texto)", (_n, c) => {
    expect(eBloqueioDoPortal(403, c)).toBe(false);
  });
});

describe("mensagemDoBloqueio", () => {
  it("usa a mensagem do servidor", () => {
    expect(mensagemDoBloqueio(BLOQUEIO)).toBe("Processo concluído.");
  });

  it.each([undefined, null, {}, corpo("x"), corpo({}), corpo({ mensagem: "   " }), corpo({ mensagem: 5 })])(
    "recua para a mensagem canónica quando o servidor não a traz (%j)",
    (c) => expect(mensagemDoBloqueio(c)).toBe(MENSAGEM_PORTAL_INATIVO),
  );
});

describe("limparSessaoDoPortal", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("apaga todas as chaves da sessão nos dois armazéns", () => {
    CHAVES_DA_SESSAO_DO_PORTAL.forEach((c) => {
      localStorage.setItem(c, "x");
      sessionStorage.setItem(c, "x");
    });
    limparSessaoDoPortal();
    CHAVES_DA_SESSAO_DO_PORTAL.forEach((c) => {
      expect(localStorage.getItem(c)).toBeNull();
      expect(sessionStorage.getItem(c)).toBeNull();
    });
  });

  it("não toca no que não é da sessão do Portal", () => {
    localStorage.setItem("tema", "claro");
    localStorage.setItem("portalToken", "abc");
    limparSessaoDoPortal();
    expect(localStorage.getItem("tema")).toBe("claro");
    expect(localStorage.getItem("portalToken")).toBeNull();
  });

  it("inclui o token que o ecrã lê primeiro (senão o bloqueio voltava ao recarregar)", () => {
    expect(CHAVES_DA_SESSAO_DO_PORTAL).toEqual(
      expect.arrayContaining(["portalToken", "portal_token", "portal_verified"]),
    );
  });
});
