import { describe, expect, it } from "vitest";
import { quantosEmIndexacao, resumoDosEnvios, textoEmIndexacao } from "./desvioInteligente";

describe("resumoDosEnvios", () => {
  it("conta só os que o SERVIDOR pôs na fila — não decide ele", () => {
    const r = resumoDosEnvios([
      { intake: { fila_ia: true } },
      { intake: { fila_ia: false } },
      { intake: { fila_ia: true } },
    ]);
    expect(r).toEqual({
      enviados: 3,
      naFila: 2,
      mensagem: "2 ficheiros ficaram na pasta Index, à espera da Indexação.",
    });
  });

  it("singular para um só ficheiro", () => {
    expect(resumoDosEnvios([{ intake: { fila_ia: true } }]).mensagem).toBe(
      "O ficheiro ficou na pasta Index, à espera da Indexação.",
    );
  });

  it("processo indexado: nada a dizer", () => {
    expect(resumoDosEnvios([{ intake: { fila_ia: false } }]).mensagem).toBeNull();
  });

  it.each([[undefined], [null], ["x"], [{}], [[null, 3, "a"]]])(
    "uma resposta sem a forma esperada (%j) não rebenta nem inventa aviso",
    (entrada) => {
      expect(resumoDosEnvios(entrada).mensagem).toBeNull();
    },
  );

  it("um servidor antigo (sem `intake`) não gera aviso", () => {
    expect(resumoDosEnvios([{ success: true }]).naFila).toBe(0);
  });
});

describe("quantosEmIndexacao / textoEmIndexacao", () => {
  it.each([
    [{ em_indexacao: 3 }, 3],
    [{ em_indexacao: "2" }, 2],
    [{ em_indexacao: -1 }, 0],
    [{ em_indexacao: "abc" }, 0],
    [{}, 0],
    [null, 0],
  ])("%j → %i", (resposta, esperado) => {
    expect(quantosEmIndexacao(resposta)).toBe(esperado);
  });

  it("sem ficheiros em espera não há frase", () => {
    expect(textoEmIndexacao(0)).toBeNull();
    expect(textoEmIndexacao(NaN)).toBeNull();
  });

  it("singular e plural", () => {
    expect(textoEmIndexacao(1)).toMatch(/^1 ficheiro enviado aguarda/);
    expect(textoEmIndexacao(4)).toMatch(/^4 ficheiros enviados aguardam/);
  });
});
