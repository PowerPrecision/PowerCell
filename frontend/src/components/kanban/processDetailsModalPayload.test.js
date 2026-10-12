import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { payloadDoClienteDoModal, seccoesDoProcessoDoModal } from "./processDetailsModalPayload";

const CLIENTE = { nome: "Ana", email: "a@b.pt", telefone: "912", nif: "123456789", estado_civil: "solteiro" };
const PROCESSO = {
  property_type: "apartamento", property_location: "Porto", property_value: 200000,
  loan_amount: 150000, spread: "1.2", taxa_esforco: "30", banco_avaliacao: "CGD", valor_avaliacao: 190000,
};

describe("payloadDoClienteDoModal", () => {
  it("apagar o email vai como vazio explícito (antes: undefined, e o email voltava)", () => {
    const { payload } = payloadDoClienteDoModal(CLIENTE, { ...CLIENTE, email: "" });
    expect(payload).toEqual({ contacto: { email: "" } });
  });

  it("apagar o NIF vai como vazio explícito", () => {
    const { payload } = payloadDoClienteDoModal(CLIENTE, { ...CLIENTE, nif: "" });
    expect(payload).toEqual({ dados_pessoais: { nif: "" } });
  });

  it("só leva o que mudou", () => {
    const { payload } = payloadDoClienteDoModal(CLIENTE, { ...CLIENTE, telefone: "966" });
    expect(payload).toEqual({ contacto: { telefone: "966" } });
  });

  it("sem alterações o payload é vazio", () => {
    expect(payloadDoClienteDoModal(CLIENTE, { ...CLIENTE }).payload).toEqual({});
  });

  it("o nome apagado é um erro, não um pedido", () => {
    const out = payloadDoClienteDoModal(CLIENTE, { ...CLIENTE, nome: "  " });
    expect(out.nomeEmFalta).toBe(true);
    expect(out.payload).not.toHaveProperty("nome");
  });

  it("o nome alterado vai aparado", () => {
    const out = payloadDoClienteDoModal(CLIENTE, { ...CLIENTE, nome: " Ana Maria " });
    expect(out.payload.nome).toBe("Ana Maria");
    expect(out.nomeEmFalta).toBe(false);
  });
});

describe("seccoesDoProcessoDoModal", () => {
  it("campo apagado vai como null, na secção certa", () => {
    const out = seccoesDoProcessoDoModal(PROCESSO, { ...PROCESSO, property_location: "", spread: "" });
    expect(out).toEqual({
      real_estate_data: { localizacao: null },
      credit_data: { spread: null },
    });
  });

  it("só leva o que mudou", () => {
    const out = seccoesDoProcessoDoModal(PROCESSO, { ...PROCESSO, loan_amount: "160000" });
    expect(out).toEqual({ real_estate_data: { valor_financiado: 160000 } });
  });

  it("valor numérico apagado é null e 0 é um valor", () => {
    expect(seccoesDoProcessoDoModal(PROCESSO, { ...PROCESSO, property_value: "" }))
      .toEqual({ real_estate_data: { valor_imovel: null } });
    expect(seccoesDoProcessoDoModal(PROCESSO, { ...PROCESSO, property_value: "0" }))
      .toEqual({ real_estate_data: { valor_imovel: 0 } });
  });

  it("um número ilegível não se envia (não é um pedido para apagar)", () => {
    expect(seccoesDoProcessoDoModal(PROCESSO, { ...PROCESSO, valor_avaliacao: "abc" })).toEqual({});
  });

  it("sem alterações não há secções", () => {
    expect(seccoesDoProcessoDoModal(PROCESSO, { ...PROCESSO })).toEqual({});
  });
});

describe("ligação ao modal (apagar o chamador não parte mais nenhum teste)", () => {
  const fonte = readFileSync(resolve(__dirname, "ProcessDetailsModal.jsx"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");

  it("o modal grava pelos dois helpers", () => {
    expect(fonte).toContain("payloadDoClienteDoModal(");
    expect(fonte).toContain("seccoesDoProcessoDoModal(");
  });

  it("e já não descarta vazios com `|| undefined` (apagar era «não alterei»)", () => {
    expect(fonte).not.toMatch(/\|\|\s*undefined/);
  });
});
