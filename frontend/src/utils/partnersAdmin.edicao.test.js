import { describe, expect, it } from "vitest";

import { corpoDaEdicao, formularioDeEdicao, validarEdicao } from "./partnersAdmin";

const P = { id: "p1", name: "Rui", email: "Rui@P.pt", phone: "912345678" };

describe("edição de parceiros (puro)", () => {
  it("o formulário parte dos dados do servidor, sem undefined", () => {
    expect(formularioDeEdicao(P)).toEqual({ name: "Rui", email: "Rui@P.pt", phone: "912345678" });
    expect(formularioDeEdicao({ id: "x" })).toEqual({ name: "", email: "", phone: "" });
    expect(formularioDeEdicao(null)).toEqual({ name: "", email: "", phone: "" });
  });

  it("nada mudou → null", () => {
    expect(corpoDaEdicao(P, formularioDeEdicao(P), { podeMudarEmail: true })).toBeNull();
  });

  it("só vai o que mudou", () => {
    expect(corpoDaEdicao(P, { name: "Rui Silva" })).toEqual({ name: "Rui Silva" });
    expect(corpoDaEdicao(P, { phone: "" })).toEqual({ phone: "" });
  });

  it("o email só vai a quem pode, e maiúsculas não contam como mudança", () => {
    expect(corpoDaEdicao(P, { email: "outro@p.pt" }, { podeMudarEmail: false })).toBeNull();
    expect(corpoDaEdicao(P, { email: "outro@p.pt" }, { podeMudarEmail: true })).toEqual({ email: "outro@p.pt" });
    expect(corpoDaEdicao(P, { email: "rui@p.PT" }, { podeMudarEmail: true })).toBeNull();
  });

  it("espaços à volta não são uma alteração", () => {
    expect(corpoDaEdicao(P, { name: "  Rui  ", phone: " 912345678 " })).toBeNull();
  });

  it("validação: nome com 2+ letras; o email só conta a quem o pode mudar", () => {
    expect(validarEdicao({ name: "R", email: "mau" }, { podeMudarEmail: false })).toEqual({ name: "Indique o nome do parceiro." });
    expect(validarEdicao({ name: "Rui", email: "mau" }, { podeMudarEmail: true })).toEqual({ email: "Indique um email válido." });
    expect(validarEdicao({ name: "Rui", email: "a@b.pt" }, { podeMudarEmail: true })).toEqual({});
  });
});
