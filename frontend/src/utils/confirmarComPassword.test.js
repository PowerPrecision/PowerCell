import { describe, expect, it } from "vitest";

import { lerErroDeConfirmacao } from "./confirmarComPassword";

const erro = (status, detail) => ({ response: { status, data: { detail } } });

describe("lerErroDeConfirmacao", () => {
  it("403 é password errada (nunca 401: o interceptor deslogaria)", () => {
    expect(lerErroDeConfirmacao(erro(403, "Password incorrecta."))).toEqual({
      tipo: "password_errada", mensagem: "Password incorrecta.", fases: [],
    });
    expect(lerErroDeConfirmacao(erro(403, undefined)).mensagem).toBe("Password incorrecta.");
  });

  it("a personificação é um 403 com a sua própria mensagem", () => {
    const lido = lerErroDeConfirmacao(erro(403, "Esta acção não pode ser confirmada durante uma personificação."));
    expect(lido.tipo).toBe("password_errada");
    expect(lido.mensagem).toMatch(/personificação/);
  });

  it("429 é bloqueio por tentativas, com a mensagem do servidor", () => {
    const lido = lerErroDeConfirmacao(erro(429, { message: "Muitas tentativas. Tente em 10 minutos." }));
    expect(lido).toEqual({ tipo: "bloqueado", mensagem: "Muitas tentativas. Tente em 10 minutos.", fases: [] });
  });

  it("400 (falta a password) e 404 são recusas, com texto de recuo configurável", () => {
    expect(lerErroDeConfirmacao(erro(400, "Indique a sua password para confirmar esta acção.")).tipo).toBe("recusado");
    expect(lerErroDeConfirmacao(erro(404, undefined), { naoEncontrado: "A empresa já não existe." }).mensagem)
      .toBe("A empresa já não existe.");
    expect(lerErroDeConfirmacao(erro(400, undefined), { recusado: "Não." }).mensagem).toBe("Não.");
  });

  it("409 com fases em uso lista-as; sem fases é uma recusa simples", () => {
    const lido = lerErroDeConfirmacao(erro(409, { message: "Há processos", fases_em_uso: [{ name: "x", total: 2 }] }));
    expect(lido.tipo).toBe("fases_em_uso");
    expect(lido.fases).toEqual([{ name: "x", total: 2 }]);
    expect(lerErroDeConfirmacao(erro(409, { message: "m", fases_em_uso: { a: 1 } })).fases).toEqual([]);
    expect(lerErroDeConfirmacao(erro(409, "vazio")).tipo).toBe("recusado");
  });

  it("qualquer outra coisa é um erro genérico, sem expor o detalhe", () => {
    expect(lerErroDeConfirmacao(erro(500, "traceback secreto")).mensagem).not.toMatch(/secreto/);
    expect(lerErroDeConfirmacao(new Error("rede")).tipo).toBe("erro");
    expect(lerErroDeConfirmacao(null).tipo).toBe("erro");
  });
});
