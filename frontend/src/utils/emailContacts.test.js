import { describe, expect, it } from "vitest";
import {
  enderecosJaEscritos,
  rotuloDoContacto,
  substituirUltimoToken,
  sugestoesParaOCampo,
  ultimoToken,
} from "./emailContacts";

describe("ultimoToken", () => {
  it.each([
    ["ana", "ana"],
    ["ana@x.pt, ru", "ru"],
    ["ana@x.pt; rui@x.pt;  pa ", "pa"],
    ["ana@x.pt, ", ""],
    ["", ""],
    [null, ""],
    [undefined, ""],
    [42, ""],
  ])("%j → %j", (entrada, esperado) => {
    expect(ultimoToken(entrada)).toBe(esperado);
  });
});

describe("substituirUltimoToken", () => {
  it("o primeiro destinatário", () => {
    expect(substituirUltimoToken("an", "ana@x.pt")).toBe("ana@x.pt, ");
  });

  it("não perde os já escritos", () => {
    expect(substituirUltimoToken("ana@x.pt, ru", "rui@x.pt")).toBe("ana@x.pt, rui@x.pt, ");
  });

  it("respeita o ponto e vírgula e normaliza o espaço", () => {
    expect(substituirUltimoToken("ana@x.pt;pa", "paulo@x.pt")).toBe("ana@x.pt; paulo@x.pt, ");
  });

  it("campo vazio ou inválido", () => {
    expect(substituirUltimoToken("", "a@x.pt")).toBe("a@x.pt, ");
    expect(substituirUltimoToken(null, "a@x.pt")).toBe("a@x.pt, ");
  });
});

describe("enderecosJaEscritos", () => {
  it("lê endereços simples e com nome, em minúsculas, sem o último pedaço", () => {
    expect(enderecosJaEscritos("Ana <ANA@x.pt>, rui@x.pt, pa")).toEqual(["ana@x.pt", "rui@x.pt"]);
  });
  it("nada escrito", () => {
    expect(enderecosJaEscritos("ana")).toEqual([]);
    expect(enderecosJaEscritos(undefined)).toEqual([]);
  });
});

describe("sugestoesParaOCampo", () => {
  const A = { address: "ana@x.pt", name: "Ana" };
  const R = { address: "rui@x.pt", name: "" };

  it("não repete quem já está no campo", () => {
    expect(sugestoesParaOCampo([A, R], "Ana <ana@x.pt>, ru")).toEqual([R]);
  });

  it.each([[undefined], [null], [{}], ["x"], [[null, {}, 3]]])(
    "uma lista que não é lista (%j) dá vazio",
    (entrada) => {
      expect(sugestoesParaOCampo(entrada, "a")).toEqual([]);
    },
  );
});

describe("rotulos e pesquisa", () => {
  it("rótulo com e sem nome", () => {
    expect(rotuloDoContacto({ address: "a@x.pt", name: "Ana" })).toBe("Ana <a@x.pt>");
    expect(rotuloDoContacto({ address: "a@x.pt" })).toBe("a@x.pt");
    expect(rotuloDoContacto(null)).toBe("");
  });
});
