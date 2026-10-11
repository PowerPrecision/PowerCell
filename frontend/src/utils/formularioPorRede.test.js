import { describe, expect, it } from "vitest";
import { empresaDoLink, linkDeRegistoDaEmpresa } from "./formularioPorRede";

describe("linkDeRegistoDaEmpresa", () => {
  it("leva o identificador da empresa no URL", () => {
    expect(linkDeRegistoDaEmpresa("https://app.exemplo.pt", "cmp-domus")).toBe(
      "https://app.exemplo.pt/registo?empresa=cmp-domus",
    );
  });

  it("não duplica a barra final da origem nem deixa escapar caracteres especiais", () => {
    expect(linkDeRegistoDaEmpresa("https://app.exemplo.pt/", "a b&c")).toBe(
      "https://app.exemplo.pt/registo?empresa=a%20b%26c",
    );
  });

  it("sem origem ou sem empresa não desenha link (um link sem destino é pior do que nenhum)", () => {
    expect(linkDeRegistoDaEmpresa("", "x")).toBe("");
    expect(linkDeRegistoDaEmpresa("https://a.pt", "")).toBe("");
    expect(linkDeRegistoDaEmpresa("https://a.pt", null)).toBe("");
  });
});

describe("empresaDoLink", () => {
  it("lê o identificador de uma pesquisa em texto ou de URLSearchParams", () => {
    expect(empresaDoLink("?empresa=cmp-domus")).toBe("cmp-domus");
    expect(empresaDoLink(new URLSearchParams("empresa=cmp-power"))).toBe("cmp-power");
  });

  it("um link antigo, sem empresa, devolve vazio", () => {
    expect(empresaDoLink("")).toBe("");
    expect(empresaDoLink("?outro=1")).toBe("");
    expect(empresaDoLink(undefined)).toBe("");
  });

  it("é o inverso do que o ecrã de administração monta", () => {
    const link = linkDeRegistoDaEmpresa("https://a.pt", "cmp x/1");
    expect(empresaDoLink(new URL(link).search)).toBe("cmp x/1");
  });
});
