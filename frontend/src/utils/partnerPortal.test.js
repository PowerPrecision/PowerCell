import { describe, expect, it } from "vitest";

import casoDeLead from "@/test/fixtures/parceiro/caso_lead.json";
import casoDeProcesso from "@/test/fixtures/parceiro/caso_processo.json";
import casos from "@/test/fixtures/parceiro/casos.json";
import painel from "@/test/fixtures/parceiro/painel.json";
import perfil from "@/test/fixtures/parceiro/perfil.json";
import {
  LEAD_VAZIA,
  TIPOS_ACEITES_NO_PARCEIRO,
  caminhoDoCaso,
  construirPayloadDaLead,
  formatarConversao,
  mensagemDeErro,
  normalizarCaso,
  normalizarCasos,
  normalizarPainel,
  pedidosPendentes,
  pedidosRecebidos,
  progressoDoPedido,
  redesActivas,
  rotuloDeAutoria,
  tamanhoLegivel,
  validarLead,
  variantDaEtapa,
} from "./partnerPortal";

describe("normalizarPainel (sobre a resposta REAL do servidor)", () => {
  const p = normalizarPainel(painel);

  it("lê o funil, os totais e a conversão", () => {
    expect(p.funil.map((e) => e.etapa)).toEqual(["pendente", "lead", "novo", "analise", "aprovado", "concluido", "perdido"]);
    expect(p.funil[0]).toEqual({ etapa: "pendente", label: "Pendentes", total: 0 });
    expect(p.funil[1]).toEqual({ etapa: "lead", label: "Leads", total: 2 });
    expect(p.pendentes).toBe(0);
    expect(p.totalDeCasos).toBe(6);
    expect(p.escriturados).toBe(1);
    expect(p.leads).toBe(2);
    expect(p.taxaDeConversao).toBe(16.7);
    expect(p.pedidosPendentes).toBe(2);
  });

  it.each([[undefined], [null], [42], ["texto"], [[]], [{ funil: "não-é-lista" }], [{ funil: { a: 1 } }]])(
    "uma resposta estranha (%o) dá sempre um painel de forma garantida",
    (resposta) => {
      const r = normalizarPainel(resposta);
      expect(Array.isArray(r.funil)).toBe(true);
      expect(r.totalDeCasos).toBe(0);
      expect(r.taxaDeConversao).toBeNull();
    }
  );

  it("descarta etapas sem nome e totais que não são números", () => {
    const r = normalizarPainel({ funil: [{ etapa: "", total: 3 }, { etapa: "novo", total: "5" }, null] });
    expect(r.funil).toEqual([{ etapa: "novo", label: "novo", total: 0 }]);
  });
});

describe("a conversão", () => {
  it("«sem base» não é zero", () => {
    expect(formatarConversao(null)).toBe("—");
    expect(formatarConversao(undefined)).toBe("—");
    expect(formatarConversao(NaN)).toBe("—");
  });
  it("formata em pt-PT", () => {
    expect(formatarConversao(16.7)).toBe("16,7 %");
    expect(formatarConversao(0)).toBe("0 %");
    expect(formatarConversao(100)).toBe("100 %");
  });
});

describe("normalizarCasos / normalizarCaso", () => {
  it("lê a lista real", () => {
    const r = normalizarCasos(casos);
    expect(r.items.length).toBe(6);
    expect(r.total).toBe(6);
    expect(r.page).toBe(1);
    expect(r.items[0].id).toBe("lead-2");
  });

  it.each([[undefined], [null], [{}], [{ items: "x" }], [{ items: { a: 1 } }], [{ items: [null, 3, {}] }]])(
    "%o dá uma lista vazia e não rebenta o .map do ecrã",
    (resposta) => {
      const r = normalizarCasos(resposta);
      expect(Array.isArray(r.items)).toBe(true);
      expect(r.items).toEqual([]);
      expect(r.pages).toBeGreaterThanOrEqual(1);
    }
  );

  it("o detalhe tem SEMPRE pedidos e ficheiros como arrays", () => {
    for (const mau of [undefined, null, {}, { pedidos: "x", ficheiros: 3 }, { pedidos: [{ id: "a", ficheiros: null }] }]) {
      const r = normalizarCaso(mau);
      expect(Array.isArray(r.pedidos)).toBe(true);
      expect(Array.isArray(r.ficheiros)).toBe(true);
      r.pedidos.forEach((p) => expect(Array.isArray(p.ficheiros)).toBe(true));
    }
  });

  it("separa os pedidos pendentes dos recebidos (a ordem do ecrã)", () => {
    const caso = normalizarCaso(casoDeProcesso);
    expect(pedidosPendentes(caso).map((p) => p.id)).toEqual(["req-1"]);
    expect(pedidosRecebidos(caso).map((p) => p.id)).toEqual(["req-2"]);
  });

  it("um pedido de uma lead vem com a nota que o consultor escreveu", () => {
    const caso = normalizarCaso(casoDeLead);
    expect(caso.kind).toBe("lead");
    expect(caso.pedidos[0].notes).toBe("Frente e verso");
  });
});

describe("pequenas regras do ecrã", () => {
  it("o progresso nunca passa do esperado (o servidor conta também o que a equipa juntou)", () => {
    expect(progressoDoPedido({ expected_count: 1, uploaded_count: 4 })).toEqual({ enviados: 1, esperados: 1 });
    expect(progressoDoPedido({ expected_count: 3, uploaded_count: 1 })).toEqual({ enviados: 1, esperados: 3 });
    expect(progressoDoPedido({})).toEqual({ enviados: 0, esperados: 1 });
  });

  it("diz quem enviou", () => {
    expect(rotuloDeAutoria("eu")).toBe("Enviado por si");
    expect(rotuloDeAutoria("cliente")).toBe("Enviado pelo cliente");
  });

  it("tamanhos", () => {
    expect(tamanhoLegivel(0)).toBe("");
    expect(tamanhoLegivel(512)).toBe("512 B");
    expect(tamanhoLegivel(2048)).toBe("2 KB");
    expect(tamanhoLegivel(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("variantes de etapa são tokens semânticos (nunca cores cruas)", () => {
    expect(variantDaEtapa("concluido")).toBe("default");
    expect(variantDaEtapa("perdido")).toBe("destructive");
    expect(variantDaEtapa("lead")).toBe("secondary");
    expect(variantDaEtapa("analise")).toBe("outline");
  });

  it("o caminho do caso escapa o id", () => {
    expect(caminhoDoCaso("a/b?c")).toBe("/parceiro/casos/a%2Fb%3Fc");
  });

  it("os tipos aceites são uma constante só", () => {
    expect(TIPOS_ACEITES_NO_PARCEIRO).toBe(".pdf,.jpg,.jpeg,.png,.doc,.docx");
  });

  it("as redes activas ignoram as suspensas e as sem rede", () => {
    expect(redesActivas(perfil).length).toBe(1);
    expect(
      redesActivas({ redes: [{ network_id: "a", status: "suspended" }, { network_id: "", status: "active" }, { network_id: "b" }] })
    ).toEqual([{ network_id: "b" }]);
    expect(redesActivas(null)).toEqual([]);
  });
});

describe("mensagemDeErro", () => {
  it("texto do servidor", () => {
    expect(mensagemDeErro({ response: { data: { detail: "Rede não encontrada." } } })).toBe("Rede não encontrada.");
  });
  it("a primeira mensagem de um 422", () => {
    expect(mensagemDeErro({ response: { data: { detail: [{ msg: "Field required" }] } } })).toBe("Field required");
  });
  it("o bloqueio do travão traz a mensagem", () => {
    const erro = { response: { status: 429, data: { detail: { message: "Tente novamente em 10 minutos." } } } };
    expect(mensagemDeErro(erro)).toBe("Tente novamente em 10 minutos.");
  });
  it("sem resposta é problema de ligação", () => {
    expect(mensagemDeErro({ message: "Network Error" })).toMatch(/ligação/i);
  });
  it("recuo", () => {
    expect(mensagemDeErro({ response: { status: 500, data: {} } }, "x")).toBe("x");
  });
});

describe("a lead", () => {
  const boa = { ...LEAD_VAZIA, name: "Joana Cliente", email: "joana@cliente.pt", consent_confirmed: true };

  it("sem consentimento não há lead", () => {
    expect(validarLead({ ...boa, consent_confirmed: false }).consent_confirmed).toBeTruthy();
  });
  it("valida nome, email e NIF", () => {
    const erros = validarLead({ ...LEAD_VAZIA, name: "J", email: "não", nif: "12" });
    expect(Object.keys(erros).sort()).toEqual(["consent_confirmed", "email", "name", "nif"]);
    expect(validarLead(boa)).toEqual({});
    expect(validarLead({ ...boa, nif: "501 964 843" })).toEqual({});
  });

  it("o corpo só leva os campos que o servidor aceita, sem opcionais vazios", () => {
    expect(construirPayloadDaLead(boa)).toEqual({
      name: "Joana Cliente",
      email: "joana@cliente.pt",
      process_type: "credito_habitacao",
      has_property: false,
      consent_confirmed: true,
    });
  });

  it("nunca leva carimbos (rede, empresa, estado, autor) — seria um 422", () => {
    const sujo = { ...boa, network_id: "x", company_id: "y", lead_status: "converted", submitted_by_partner_id: "z", assigned_to: "u" };
    const chaves = Object.keys(construirPayloadDaLead(sujo));
    for (const proibida of ["company_id", "lead_status", "submitted_by_partner_id", "assigned_to", "status", "id"]) {
      expect(chaves).not.toContain(proibida);
    }
    expect(chaves).not.toContain("network_id");
  });

  it("a rede só vai quando o parceiro a escolheu", () => {
    expect(construirPayloadDaLead(boa, "rede-1").network_id).toBe("rede-1");
    expect(construirPayloadDaLead(boa, undefined)).not.toHaveProperty("network_id");
  });

  it("apara espaços e tira os do NIF", () => {
    const p = construirPayloadDaLead({ ...boa, name: "  Ana  ", nif: "501 964 843", phone: " 912 ", notes: " olá " });
    expect(p).toMatchObject({ name: "Ana", nif: "501964843", phone: "912", notes: "olá" });
  });
});
