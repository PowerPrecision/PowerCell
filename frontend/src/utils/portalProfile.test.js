/**
 * Perfil do Portal — hidratação e payload (Lote 3, ponto 7).
 *
 * As duas peças onde um erro faz o cliente perder dados sem se aperceber:
 * ler a ficha para o formulário, e devolver o formulário à ficha. Ambas
 * vivem fora do `ClientPortal.jsx` (2963 linhas) exactamente para poderem
 * ser testadas.
 */
import { describe, expect, it } from "vitest";

import {
  construirPayload,
  hidratarFormulario,
  obrigatoriosEmFalta,
} from "./portalProfile";

const ESQUEMA = [
  { field_key: "email", label: "Email", is_required: true, is_primary: true, destino: ["contacto", "email"] },
  { field_key: "phone", label: "Telemóvel", is_required: true, is_primary: true, destino: ["contacto", "telefone"] },
  { field_key: "birth_date", label: "Data de Nascimento", is_required: true, is_primary: true, destino: ["dados_pessoais", "data_nascimento"] },
  { field_key: "codigo_postal", label: "Código Postal", is_required: false, is_primary: false, destino: ["dados_pessoais", "codigo_postal"] },
];

describe("hidratarFormulario", () => {
  it("lê cada campo do grupo certo da ficha", () => {
    const valores = hidratarFormulario(ESQUEMA, {
      contacto: { email: "ana@exemplo.pt", telefone: "912345678" },
      dados_pessoais: { codigo_postal: "4000-100" },
    });
    expect(valores.email).toBe("ana@exemplo.pt");
    expect(valores.phone).toBe("912345678");
    expect(valores.codigo_postal).toBe("4000-100");
  });

  it("indexa por field_key, não pelo nome na ficha", () => {
    // O formulário chama-lhe `phone`; a ficha guarda `contacto.telefone`.
    const valores = hidratarFormulario(ESQUEMA, {
      contacto: { telefone: "912345678" },
    });
    expect(valores.phone).toBe("912345678");
    expect(valores.telefone).toBeUndefined();
  });

  it("aceita a data de nascimento com o nome antigo", () => {
    // Fichas antigas guardaram `birth_date`. Ler só `data_nascimento`
    // mostrava o campo vazio e o cliente preenchia-o outra vez.
    const valores = hidratarFormulario(ESQUEMA, {
      dados_pessoais: { birth_date: "1988-04-12" },
    });
    expect(valores.birth_date).toBe("1988-04-12");
  });

  it("o nome novo tem precedência sobre o antigo", () => {
    const valores = hidratarFormulario(ESQUEMA, {
      dados_pessoais: { data_nascimento: "1990-01-01", birth_date: "1988-04-12" },
    });
    expect(valores.birth_date).toBe("1990-01-01");
  });

  it("campo em falta na ficha fica string vazia, nunca undefined", () => {
    // Um `undefined` num input torna-o não-controlado e o React avisa.
    const valores = hidratarFormulario(ESQUEMA, {});
    expect(valores.email).toBe("");
  });

  it("ficha em falta não rebenta", () => {
    expect(hidratarFormulario(ESQUEMA, undefined).email).toBe("");
  });

  it("esquema em falta devolve objecto vazio", () => {
    expect(hidratarFormulario(undefined, {})).toEqual({});
  });

  it("ignora entradas sem destino", () => {
    const valores = hidratarFormulario([{ field_key: "x", label: "X" }], {});
    expect(valores).toEqual({});
  });
});

describe("construirPayload", () => {
  it("agrupa pelos destinos do esquema", () => {
    const payload = construirPayload(ESQUEMA, {
      email: "ana@exemplo.pt",
      phone: "912345678",
      birth_date: "1988-04-12",
      codigo_postal: "4000-100",
    });
    expect(payload.contacto).toEqual({
      email: "ana@exemplo.pt",
      telefone: "912345678",
    });
    expect(payload.dados_pessoais).toEqual({
      data_nascimento: "1988-04-12",
      codigo_postal: "4000-100",
    });
  });

  it("um campo apagado vai como null, não é omitido", () => {
    // Apagar é uma intenção legítima; omitir deixaria o valor antigo.
    const payload = construirPayload(ESQUEMA, { email: "" });
    expect(payload.contacto.email).toBeNull();
  });

  it("não envia nada que não esteja no esquema", () => {
    // É isto que garante que o que se envia é o que se mostrou — e que o
    // backend não tem de descartar nada em silêncio.
    const payload = construirPayload(ESQUEMA, {
      email: "a@b.pt",
      nif: "123456789",
    });
    expect(JSON.stringify(payload)).not.toContain("123456789");
  });

  it("esquema vazio devolve payload vazio", () => {
    expect(construirPayload([], { email: "x" })).toEqual({
      contacto: {},
      dados_pessoais: {},
    });
  });

  it("ida e volta preserva os valores", () => {
    const ficha = {
      contacto: { email: "ana@exemplo.pt", telefone: "912345678" },
      dados_pessoais: { data_nascimento: "1988-04-12", codigo_postal: "4000-100" },
    };
    const payload = construirPayload(ESQUEMA, hidratarFormulario(ESQUEMA, ficha));
    expect(payload.contacto).toEqual(ficha.contacto);
    expect(payload.dados_pessoais).toEqual(ficha.dados_pessoais);
  });
});

describe("obrigatoriosEmFalta", () => {
  it("lista os obrigatórios por preencher", () => {
    const emFalta = obrigatoriosEmFalta(ESQUEMA, { email: "a@b.pt" });
    expect(emFalta.map((c) => c.field_key)).toEqual(["phone", "birth_date"]);
  });

  it("um opcional em branco não conta", () => {
    const emFalta = obrigatoriosEmFalta(ESQUEMA, {
      email: "a@b.pt", phone: "9", birth_date: "1988-04-12",
    });
    expect(emFalta).toEqual([]);
  });

  it("espaços não contam como preenchido", () => {
    const emFalta = obrigatoriosEmFalta(ESQUEMA, { email: "   " });
    expect(emFalta.map((c) => c.field_key)).toContain("email");
  });

  it("devolve o rótulo para a mensagem ao utilizador", () => {
    const [primeiro] = obrigatoriosEmFalta(ESQUEMA, {});
    expect(primeiro.label).toBe("Email");
  });
});
