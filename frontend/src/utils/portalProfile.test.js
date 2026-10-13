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
  secoesDoPerfil,
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


// ====================================================================
// O perfil espelha TODO o registo (Out 2026)
// ====================================================================

const ESQUEMA_COMPLETO = [
  { field_key: "email", label: "Email", section: "titular", destino: ["contacto", "email"] },
  { field_key: "nif", label: "NIF", section: "titular", read_only: true, destino: ["dados_pessoais", "nif"] },
  { field_key: "estado_civil", label: "Estado Civil", section: "titular", field_type: "select", destino: ["dados_pessoais", "estado_civil"] },
  { field_key: "titular2_naturalidade", label: "Naturalidade 2.º", section: "segundo_titular", destino: ["titular2_data", "naturalidade"] },
  { field_key: "localizacao", label: "Localização", section: "imovel", destino: ["real_estate_data", "localizacao"] },
  { field_key: "caracteristicas", label: "Características", section: "imovel", field_type: "checkbox", options: ["Garagem", "Elevador"], destino: ["real_estate_data", "caracteristicas"] },
  { field_key: "ja_tem_casa_escolhida", label: "Já tem casa", section: "imovel", field_type: "checkbox", options: [], destino: ["real_estate_data", "ja_tem_casa_escolhida"] },
  { field_key: "salario_liquido", label: "Salário", section: "financeiro", field_type: "number", is_required: true, destino: ["financial_data", "salario_liquido"] },
  { field_key: "bancos_creditos", label: "Créditos", section: "financeiro", read_only: true, is_required: true, field_type: "checkbox", destino: ["financial_data", "bancos_creditos"] },
];

describe("secoesDoPerfil", () => {
  it("parte o esquema em cartões pela ordem do registo, só com os que têm campos", () => {
    const secoes = secoesDoPerfil(ESQUEMA_COMPLETO);
    expect(secoes.map((s) => s.id)).toEqual(["titular", "segundo_titular", "imovel", "financeiro"]);
    expect(secoes[2].campos.map((c) => c.field_key)).toEqual([
      "localizacao", "caracteristicas", "ja_tem_casa_escolhida",
    ]);
  });

  it("usa os títulos que o servidor mandou", () => {
    const secoes = secoesDoPerfil(ESQUEMA_COMPLETO, [
      { id: "titular", titulo: "Os meus dados" },
      { id: "financeiro", titulo: "Finanças" },
    ]);
    expect(secoes[0].titulo).toBe("Os meus dados");
    expect(secoes[1].titulo).toBe("Finanças");
    // As que a lista do servidor não trazia não somem: entram no fim com o título de omissão.
    expect(secoes.slice(2).map((s) => [s.id, s.titulo])).toEqual([
      ["segundo_titular", "Segundo Titular"],
      ["imovel", "Imóvel Pretendido"],
    ]);
  });

  it("sem segundo titular no esquema o cartão nem existe", () => {
    const sem = ESQUEMA_COMPLETO.filter((c) => c.section !== "segundo_titular");
    expect(secoesDoPerfil(sem).map((s) => s.id)).not.toContain("segundo_titular");
  });

  it("um esquema antigo, sem `section`, cai todo nos dados pessoais", () => {
    const antigo = ESQUEMA.map(({ section, ...resto }) => resto);
    const secoes = secoesDoPerfil(antigo);
    expect(secoes).toHaveLength(1);
    expect(secoes[0].id).toBe("titular");
    expect(secoes[0].campos).toHaveLength(antigo.length);
  });

  it("uma secção que a lista não conhece não desaparece", () => {
    const secoes = secoesDoPerfil([
      { field_key: "x", section: "nova", destino: ["dados_pessoais", "x"] },
    ]);
    expect(secoes.map((s) => s.id)).toEqual(["nova"]);
  });

  it("esquema em falta devolve lista vazia", () => {
    expect(secoesDoPerfil(undefined)).toEqual([]);
  });
});

describe("hidratar e payload com as secções", () => {
  const FICHA = {
    contacto: { email: "ana@x.pt" },
    dados_pessoais: { estado_civil: "casado" },
    titular2_data: { naturalidade: "Braga" },
    real_estate_data: { localizacao: "Lisboa", caracteristicas: ["Garagem"], ja_tem_casa_escolhida: true },
    financial_data: { salario_liquido: 1500 },
  };

  it("lê cada secção do seu grupo", () => {
    const valores = hidratarFormulario(ESQUEMA_COMPLETO, FICHA);
    expect(valores.titular2_naturalidade).toBe("Braga");
    expect(valores.localizacao).toBe("Lisboa");
    expect(valores.salario_liquido).toBe(1500);
  });

  it("caixa de opções é lista, caixa simples é booleano — nunca texto vazio", () => {
    const valores = hidratarFormulario(ESQUEMA_COMPLETO, FICHA);
    expect(valores.caracteristicas).toEqual(["Garagem"]);
    expect(valores.ja_tem_casa_escolhida).toBe(true);
    const vazios = hidratarFormulario(ESQUEMA_COMPLETO, {});
    expect(vazios.caracteristicas).toEqual([]);
    expect(vazios.ja_tem_casa_escolhida).toBe(false);
  });

  it("o campo só de leitura NÃO entra no estado editável", () => {
    const valores = hidratarFormulario(ESQUEMA_COMPLETO, {
      ...FICHA, dados_pessoais: { nif: "123456789" },
    });
    expect("nif" in valores).toBe(false);
    expect("bancos_creditos" in valores).toBe(false);
  });

  it("o payload nunca leva o que é só de leitura, mesmo que o estado o tenha", () => {
    const payload = construirPayload(ESQUEMA_COMPLETO, {
      email: "a@b.pt", nif: "123456789", bancos_creditos: ["BPI"], salario_liquido: 900,
    });
    expect(JSON.stringify(payload)).not.toContain("123456789");
    expect(JSON.stringify(payload)).not.toContain("BPI");
    expect(payload.financial_data).toEqual({ salario_liquido: 900 });
  });

  it("agrupa as secções pelos grupos do formulário", () => {
    const payload = construirPayload(
      ESQUEMA_COMPLETO,
      hidratarFormulario(ESQUEMA_COMPLETO, FICHA),
    );
    expect(payload.titular2_data).toEqual({ naturalidade: "Braga" });
    expect(payload.real_estate_data).toEqual({
      localizacao: "Lisboa", caracteristicas: ["Garagem"], ja_tem_casa_escolhida: true,
    });
    expect(payload.financial_data).toEqual({ salario_liquido: 1500 });
  });

  it("sem secções no esquema o payload é o de sempre", () => {
    expect(construirPayload(ESQUEMA, { email: "x" })).toEqual({
      contacto: { email: "x", telefone: null },
      dados_pessoais: { data_nascimento: null, codigo_postal: null },
    });
  });

  it("uma caixa desmarcada vai como false, não como null", () => {
    const payload = construirPayload(ESQUEMA_COMPLETO, { ja_tem_casa_escolhida: false, caracteristicas: [] });
    expect(payload.real_estate_data.ja_tem_casa_escolhida).toBe(false);
    expect(payload.real_estate_data.caracteristicas).toBeNull();
  });

  describe("com a base de hidratação, as secções só enviam o que MUDOU", () => {
    const base = hidratarFormulario(ESQUEMA_COMPLETO, FICHA);

    it("sem alterações as secções não viajam (não pisam o que a equipa corrigiu)", () => {
      const payload = construirPayload(ESQUEMA_COMPLETO, { ...base }, base);
      expect(payload.titular2_data).toBeUndefined();
      expect(payload.real_estate_data).toBeUndefined();
      expect(payload.financial_data).toBeUndefined();
    });

    it("só o campo alterado vai", () => {
      const payload = construirPayload(ESQUEMA_COMPLETO, { ...base, salario_liquido: 1800 }, base);
      expect(payload.financial_data).toEqual({ salario_liquido: 1800 });
      expect(payload.real_estate_data).toBeUndefined();
    });

    it("apagar um campo é uma alteração e vai como null", () => {
      const payload = construirPayload(ESQUEMA_COMPLETO, { ...base, localizacao: "" }, base);
      expect(payload.real_estate_data).toEqual({ localizacao: null });
    });

    it("uma lista alterada conta como alteração; a mesma lista não", () => {
      const igual = construirPayload(ESQUEMA_COMPLETO, { ...base, caracteristicas: ["Garagem"] }, base);
      expect(igual.real_estate_data).toBeUndefined();
      const outra = construirPayload(ESQUEMA_COMPLETO, { ...base, caracteristicas: ["Garagem", "Elevador"] }, base);
      expect(outra.real_estate_data.caracteristicas).toEqual(["Garagem", "Elevador"]);
    });

    it("os dados pessoais e contactos continuam a ir inteiros", () => {
      const payload = construirPayload(ESQUEMA_COMPLETO, { ...base }, base);
      expect(payload.contacto.email).toBe("ana@x.pt");
      expect(payload.dados_pessoais.estado_civil).toBe("casado");
    });
  });

  it("os obrigatórios só-de-leitura e as caixas não bloqueiam", () => {
    // `bancos_creditos` é obrigatório no registo mas o cliente não o pode editar aqui.
    const emFalta = obrigatoriosEmFalta(ESQUEMA_COMPLETO, {});
    expect(emFalta.map((c) => c.field_key)).toEqual(["salario_liquido"]);
  });
});
