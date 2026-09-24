/**
 * Ponto 9 — as regras do formulário stress-free.
 *
 * O teste que mais interessa é o do passo SEM campos obrigatórios (o 2º
 * titular, onde os 10 campos são todos opcionais no `form_config`): se a
 * separação fosse cega, esse passo abria visualmente vazio, com tudo
 * atrás de um botão. Um ecrã vazio assusta mais do que uma lista longa.
 */
import { describe, it, expect } from "vitest";
import {
  separarCamposPorPrioridade,
  estaPreenchido,
  contarProgressoObrigatorios,
  textoDoPainelSecundario,
} from "./formularioPublicoCampos";

const campo = (key, obrigatorio = false) => ({
  field_key: key,
  is_required: obrigatorio,
});

describe("separarCamposPorPrioridade", () => {
  it("põe os obrigatórios à vista e os restantes no painel", () => {
    const { primarios, secundarios } = separarCamposPorPrioridade([
      campo("name", true),
      campo("sexo"),
      campo("email", true),
      campo("altura"),
    ]);
    expect(primarios.map((c) => c.field_key)).toEqual(["name", "email"]);
    expect(secundarios.map((c) => c.field_key)).toEqual(["sexo", "altura"]);
  });

  it("preserva a ordem dentro de cada grupo", () => {
    // A ordem vem do `order` do config e já foi aplicada a montante;
    // baralhá-la aqui mudaria o formulário sem ninguém pedir.
    const { secundarios } = separarCamposPorPrioridade([
      campo("a"), campo("b"), campo("c"),
    ]);
    expect(secundarios.map((c) => c.field_key)).toEqual([]);
  });

  it("mostra TUDO quando o passo não tem campos obrigatórios", () => {
    // O passo do 2º titular: 10 campos, zero obrigatórios. Escondê-los
    // todos deixaria o ecrã em branco.
    const campos = [campo("titular2_name"), campo("titular2_email")];
    const { primarios, secundarios } = separarCamposPorPrioridade(campos);
    expect(primarios.map((c) => c.field_key))
      .toEqual(["titular2_name", "titular2_email"]);
    expect(secundarios).toEqual([]);
  });

  it("não cria painel quando são todos obrigatórios", () => {
    const { primarios, secundarios } = separarCamposPorPrioridade([
      campo("consent_data", true),
      campo("consent_contact", true),
    ]);
    expect(primarios).toHaveLength(2);
    expect(secundarios).toEqual([]);
  });

  it("honra o override do administrador acima do is_required do campo", () => {
    // `isFieldRequired` deixa o admin tornar opcional um campo que o
    // config traz como obrigatório. Ler só `is_required` ignorava-o, e
    // o campo ficava à vista com asterisco enquanto o `validateStep`
    // já não o bloqueava — a divergência outra vez, por outra porta.
    const campos = [campo("nif", true), campo("sexo", false)];
    const { primarios, secundarios } = separarCamposPorPrioridade(
      campos,
      (c) => (c.field_key === "nif" ? false : true),
    );
    expect(primarios.map((c) => c.field_key)).toEqual(["sexo"]);
    expect(secundarios.map((c) => c.field_key)).toEqual(["nif"]);
  });

  it("aguenta entradas nulas, vazias ou mal formadas", () => {
    expect(separarCamposPorPrioridade(null)).toEqual({
      primarios: [], secundarios: [],
    });
    expect(separarCamposPorPrioridade([])).toEqual({
      primarios: [], secundarios: [],
    });
    const { primarios } = separarCamposPorPrioridade([null, campo("a", true)]);
    expect(primarios.map((c) => c.field_key)).toEqual(["a"]);
  });
});

describe("estaPreenchido", () => {
  it("aceita texto com conteúdo", () => {
    expect(estaPreenchido("Ana")).toBe(true);
    expect(estaPreenchido(0)).toBe(true);
  });

  it("recusa vazio, espaços, nulo e indefinido", () => {
    for (const vazio of ["", "   ", null, undefined]) {
      expect(estaPreenchido(vazio)).toBe(false);
    }
  });

  it("um consentimento recusado não conta como respondido", () => {
    // `false` num checkbox de RGPD é "não aceito", e o passo não avança.
    // Contá-lo como preenchido punha a barra a 100% num formulário que
    // não se pode submeter.
    expect(estaPreenchido(false)).toBe(false);
    expect(estaPreenchido(true)).toBe(true);
  });

  it("uma lista vazia não conta", () => {
    expect(estaPreenchido([])).toBe(false);
    expect(estaPreenchido(["CGD"])).toBe(true);
  });
});

describe("contarProgressoObrigatorios", () => {
  it("conta só o que bloqueia mesmo", () => {
    // A barra antiga somava uma lista fixa por passo COM a do config.
    // Aqui só entra o que lhe derem, e quem lho dá é o config.
    const r = contarProgressoObrigatorios(
      ["name", "email", "phone"],
      { name: "Ana", email: "", phone: "912345678", sexo: "F" },
    );
    expect(r).toEqual({ completos: 2, total: 3, percentagem: 67 });
  });

  it("dá zero por cento num formulário em branco", () => {
    expect(contarProgressoObrigatorios(["a", "b"], {}).percentagem).toBe(0);
  });

  it("dá cem por cento quando está tudo lá", () => {
    expect(
      contarProgressoObrigatorios(["a"], { a: "x" }).percentagem,
    ).toBe(100);
  });

  it("sem obrigatórios não inventa uma percentagem", () => {
    // Zero a dividir por zero dava NaN, e a barra desenhava vazia para
    // sempre num passo que já está completo.
    expect(contarProgressoObrigatorios([], { a: "x" }))
      .toEqual({ completos: 0, total: 0, percentagem: 0 });
    expect(contarProgressoObrigatorios(null, null).percentagem).toBe(0);
  });
});

describe("textoDoPainelSecundario", () => {
  it("nunca usa a palavra obrigatório nem linguagem de falha", () => {
    // É o ponto inteiro do Ponto 9: o cliente não pode sentir que vai
    // falhar a submissão.
    const texto = textoDoPainelSecundario(7);
    const tudo = `${texto.titulo} ${texto.resumo} ${texto.ajuda}`.toLowerCase();
    for (const proibida of ["obrigat", "em falta", "tem de", "erro", "falha"]) {
      expect(tudo).not.toContain(proibida);
    }
  });

  it("diz explicitamente que dá para continuar sem preencher", () => {
    expect(textoDoPainelSecundario(3).ajuda).toMatch(/impede.*continuar/i);
  });

  it("concorda em número no singular e no plural", () => {
    expect(textoDoPainelSecundario(1).resumo).toContain("1 campo que");
    expect(textoDoPainelSecundario(4).resumo).toContain("4 campos que");
  });

  it("não devolve painel nenhum sem campos secundários", () => {
    expect(textoDoPainelSecundario(0)).toBeNull();
    expect(textoDoPainelSecundario()).toBeNull();
  });
});
