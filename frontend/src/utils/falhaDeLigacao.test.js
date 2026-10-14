import { describe, expect, it } from "vitest";

import { eFalhaDeLigacao, mensagemDeFalha } from "./falhaDeLigacao";

const comEstado = (status, data = {}) => ({ response: { status, data } });

describe("eFalhaDeLigacao", () => {
  it.each([502, 503, 504])("%s é uma falha de ligação", (estado) => {
    expect(eFalhaDeLigacao(comEstado(estado, "<html>Bad Gateway</html>"))).toBe(true);
  });

  it.each([400, 401, 403, 404, 409, 422, 500])("%s diz algo sobre o pedido: NÃO é falha de ligação", (estado) => {
    expect(eFalhaDeLigacao(comEstado(estado, { detail: "x" }))).toBe(false);
  });

  it("sem resposta (ERR_CONNECTION_CLOSED, rede cortada) é falha de ligação", () => {
    expect(eFalhaDeLigacao({ request: {}, message: "Network Error", code: "ERR_NETWORK" })).toBe(true);
    expect(eFalhaDeLigacao({ code: "ECONNABORTED", message: "timeout of 5000ms exceeded" })).toBe(true);
    expect(eFalhaDeLigacao(new Error("Network Error"))).toBe(true);
    // O `fetch` do browser: Chrome / Safari.
    expect(eFalhaDeLigacao(new TypeError("Failed to fetch"))).toBe(true);
    expect(eFalhaDeLigacao(new TypeError("Load failed"))).toBe(true);
  });

  it("um erro NOSSO (sem resposta nem rede) não se confunde com a rede", () => {
    expect(eFalhaDeLigacao(new TypeError("x is not a function"))).toBe(false);
    expect(eFalhaDeLigacao(null)).toBe(false);
    expect(eFalhaDeLigacao(undefined)).toBe(false);
  });
});

describe("mensagemDeFalha", () => {
  it("um 502 não manda mexer nas credenciais: diz que o servidor não respondeu", () => {
    const texto = mensagemDeFalha(comEstado(502, "<html>"), "Erro ao testar a ligação");
    expect(texto).toMatch(/servidor não respondeu \(erro 502\)/i);
    expect(texto).not.toMatch(/Erro ao testar a ligação/);
  });

  it("sem resposta diz que não há ligação", () => {
    expect(mensagemDeFalha(new Error("Network Error"), "x")).toMatch(/sem ligação ao servidor/i);
  });

  it("um erro da aplicação mostra o motivo do servidor", () => {
    expect(mensagemDeFalha(comEstado(400, { detail: "Credenciais SMTP inválidas." }), "x"))
      .toBe("Credenciais SMTP inválidas.");
  });

  it("sem motivo usa o texto por omissão", () => {
    expect(mensagemDeFalha(comEstado(500, {}), "Não foi possível enviar o email de teste"))
      .toBe("Não foi possível enviar o email de teste");
  });
});

describe("mensagemDeResposta (para quem usa fetch)", () => {
  it("um 502 com corpo HTML (já lido como {}) diz que o servidor não respondeu", async () => {
    const { mensagemDeResposta } = await import("./falhaDeLigacao");
    expect(mensagemDeResposta(502, {}, "Falha na conexão")).toMatch(/servidor não respondeu \(erro 502\)/i);
  });

  it("um erro da aplicação mostra detail, ou message quando não há detail", async () => {
    const { mensagemDeResposta } = await import("./falhaDeLigacao");
    expect(mensagemDeResposta(400, { detail: "Chave inválida." }, "x")).toBe("Chave inválida.");
    expect(mensagemDeResposta(400, { message: "Sem remetente." }, "x")).toBe("Sem remetente.");
    expect(mensagemDeResposta(500, null, "Falha na conexão")).toBe("Falha na conexão");
  });
});
