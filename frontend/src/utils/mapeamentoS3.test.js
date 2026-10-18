import { describe, it, expect } from "vitest";
import { opcoesDeMapeamento, temPastaGravada } from "./mapeamentoS3";

const RAIZ = "Documentação Clientes/";
const UUID = "9f1c3a52-1111-4111-8111-aaaaaaaaaaaa";

describe("opcoesDeMapeamento", () => {
  const pastas = [
    { path: `${RAIZ}${UUID}`, name: UUID, display_name: "Ana Costa" },
    { path: `${RAIZ}Joao_Silva`, name: "Joao_Silva", display_name: "Joao_Silva" },
  ];

  it("usa o nome legível e nunca o uuid como rótulo", () => {
    const rotulos = opcoesDeMapeamento(pastas, {}).map((o) => o.label);
    expect(rotulos).toContain("Ana Costa");
    expect(rotulos.join(" ")).not.toContain(UUID);
  });

  it("o valor da opção é o caminho cru (é o que se grava)", () => {
    const op = opcoesDeMapeamento(pastas, {}).find((o) => o.label === "Ana Costa");
    expect(op.value).toBe(`${RAIZ}${UUID}`);
  });

  it("um ponteiro de processo fora das pastas de topo aparece como opção — não cai em «Sem mapeamento»", () => {
    const processo = {
      s3_folder: `${RAIZ}${UUID}/processos/p1`,
      s3_folder_display: "Ana Costa › Processo n.º 7",
    };
    const opcoes = opcoesDeMapeamento(pastas, processo);
    expect(opcoes[0]).toEqual({ value: processo.s3_folder, label: "Ana Costa › Processo n.º 7" });
  });

  it("um ponteiro que já é uma pasta de topo não duplica", () => {
    const opcoes = opcoesDeMapeamento(pastas, { s3_folder: `${RAIZ}${UUID}` });
    expect(opcoes.filter((o) => o.value === `${RAIZ}${UUID}`)).toHaveLength(1);
  });

  it("sem legível no servidor, o ponteiro cru é o último recurso (nunca vazio)", () => {
    const opcoes = opcoesDeMapeamento([], { s3_folder: `${RAIZ}x/y` });
    expect(opcoes).toEqual([{ value: `${RAIZ}x/y`, label: `${RAIZ}x/y` }]);
  });

  it("lista inválida ou ponteiro de outro tipo não rebenta", () => {
    expect(opcoesDeMapeamento(null, { s3_folder: ["x"] })).toEqual([]);
    expect(opcoesDeMapeamento({ a: 1 }, undefined)).toEqual([]);
  });
});

describe("temPastaGravada", () => {
  it.each([[{ s3_folder: "a" }, true], [{ s3_folder: "" }, false], [{ s3_folder: ["a"] }, false], [{}, false]])(
    "%o → %s", (p, esperado) => expect(temPastaGravada(p)).toBe(esperado),
  );
});
