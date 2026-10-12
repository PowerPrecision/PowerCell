import { describe, expect, it } from "vitest";

import { lerErroDeReposicao } from "./reporAoModelo";

const erro = (status, detail) => ({ response: { status, data: { detail } } });

describe("lerErroDeReposicao", () => {
  it("403 é password errada (e usa a mensagem do servidor)", () => {
    expect(lerErroDeReposicao(erro(403, "Password incorrecta."))).toEqual({
      tipo: "password_errada", mensagem: "Password incorrecta.", fases: [],
    });
  });

  it("403 sem mensagem usa uma por omissão", () => {
    expect(lerErroDeReposicao(erro(403, undefined)).mensagem).toBe("Password incorrecta.");
  });

  it("429 é bloqueio por tentativas, com a mensagem do objecto", () => {
    const lido = lerErroDeReposicao(erro(429, { message: "Muitas tentativas falhadas. Tente novamente em 10 minutos." }));
    expect(lido.tipo).toBe("bloqueado");
    expect(lido.mensagem).toMatch(/10 minutos/);
  });

  it("409 com fases em uso devolve a lista", () => {
    const lido = lerErroDeReposicao(erro(409, {
      message: "Há processos em fases que o modelo não tem.",
      fases_em_uso: [{ name: "fase_custom", total: 2 }],
    }));
    expect(lido.tipo).toBe("fases_em_uso");
    expect(lido.fases).toEqual([{ name: "fase_custom", total: 2 }]);
  });

  it("409 sem lista (modelo vazio) é recusado", () => {
    const lido = lerErroDeReposicao(erro(409, "O modelo de workflow está vazio."));
    expect(lido.tipo).toBe("recusado");
    expect(lido.fases).toEqual([]);
  });

  it("uma lista que não é lista nunca rebenta (Array.isArray, não || [])", () => {
    expect(lerErroDeReposicao(erro(409, { message: "x", fases_em_uso: { a: 1 } })).fases).toEqual([]);
  });

  it("404 e erros desconhecidos têm mensagem própria", () => {
    expect(lerErroDeReposicao(erro(404, "Rede não encontrada")).tipo).toBe("recusado");
    expect(lerErroDeReposicao(new Error("rede")).tipo).toBe("erro");
    expect(lerErroDeReposicao(null).tipo).toBe("erro");
  });
});
