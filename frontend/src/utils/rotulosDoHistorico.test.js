import { describe, expect, it } from "vitest";
import {
  CAMPOS_DO_HISTORICO,
  acaoLegivel,
  descreverAlteracao,
  eCampoDeIds,
  rotuloDoCampo,
  valorLegivel,
} from "./rotulosDoHistorico";
import { describeAuditEvent } from "./processAuditHistory";
import { buildSummaryTimeline } from "./summaryTimeline";

const CRUA = /[a-z]+_[a-z_]+/; // qualquer snake_case que sobre num texto de ecrã é uma chave por traduzir

describe("rotuloDoCampo", () => {
  it("as chaves da queixa saem em português", () => {
    expect(rotuloDoCampo("assigned_mediador_ids")).toBe("Intermediários");
    expect(rotuloDoCampo("portal_access")).toBe("Acesso ao Portal");
  });

  it("uma chave desconhecida nunca aparece crua", () => {
    for (const chave of ["campo_inventado_agora", "a.b.c", "real_estate_data.preco_maximo", "x_ids"]) {
      expect(rotuloDoCampo(chave)).not.toMatch(CRUA);
    }
    expect(rotuloDoCampo("personal_data.nif")).toBe("Dados pessoais · NIF");
    expect(rotuloDoCampo("responsavel_ids")).toBe("Responsavel");
  });

  it("vazio e nulos não rebentam", () => {
    expect(rotuloDoCampo("")).toBe("Valor");
    expect(rotuloDoCampo(null)).toBe("Valor");
    expect(rotuloDoCampo(undefined)).toBe("Valor");
  });

  it("todo o rótulo e toda a frase do dicionário estão traduzidos (sem underscores)", () => {
    for (const [chave, { rotulo, atualizado }] of Object.entries(CAMPOS_DO_HISTORICO)) {
      expect(rotulo, chave).not.toMatch(/_/);
      expect(atualizado, chave).not.toMatch(/_/);
    }
  });
});

describe("campos de ids e valores", () => {
  it("reconhece os campos de ids (e só esses)", () => {
    expect(eCampoDeIds("assigned_mediador_ids")).toBe(true);
    expect(eCampoDeIds("client_id")).toBe(true);
    expect(eCampoDeIds("a.b.owner_id")).toBe(true);
    expect(eCampoDeIds("consultor_names")).toBe(false);
    expect(eCampoDeIds("video")).toBe(false);
  });

  it("o valor de um campo de ids não se mostra", () => {
    expect(valorLegivel("assigned_mediador_ids", ["3f2c-uuid"])).toBe("");
  });

  it("booleanos, listas de texto, listas de objectos, vazio", () => {
    expect(valorLegivel("is_indexed", true)).toBe("Sim");
    expect(valorLegivel("is_indexed", false)).toBe("Não");
    expect(valorLegivel("consultor_names", ["Ana", "Rui"])).toBe("Ana, Rui");
    expect(valorLegivel("documents", [{ a: 1 }, { b: 2 }])).toBe("2 itens");
    expect(valorLegivel("documents", [{ a: 1 }])).toBe("1 item");
    expect(valorLegivel("x", [])).toBe("nenhum");
    expect(valorLegivel("x", { a: 1 })).toBe("");
    expect(valorLegivel("x", null)).toBe("");
  });
});

describe("descreverAlteracao", () => {
  it("atribuição de intermediários: frase amigável, sem ids", () => {
    const r = descreverAlteracao({
      action: "Atribuiu intermediário", field: "assigned_mediador_ids", oldValue: ["a1"], newValue: ["b2-uuid-longo"],
    });
    expect(r.detalhe).toBe("Intermediários atualizados");
    expect(`${r.principal} ${r.detalhe}`).not.toMatch(/b2-uuid|a1|_ids/);
  });

  it("acesso ao Portal", () => {
    expect(descreverAlteracao({ action: "Gerou link", field: "portal_access", newValue: "ativo" }).detalhe)
      .toBe("Acesso ao Portal: ativo");
    expect(descreverAlteracao({ action: "Gerou link", field: "portal_access" }).detalhe).toBe("Acesso ao Portal atualizado");
  });

  it("alterado de X para Y e removido", () => {
    expect(descreverAlteracao({ action: "Alterou", field: "finance_status", oldValue: "pendente", newValue: "pago" }))
      .toEqual({ principal: "Alterou: Estado financeiro alterado de pendente para pago", detalhe: "pendente → pago" });
    expect(descreverAlteracao({ action: "Alterou", field: "email", oldValue: "a@x.pt" }).detalhe).toBe("Email removido");
  });

  it("sem campo devolve só a acção", () => {
    expect(descreverAlteracao({ action: "Criou processo" })).toEqual({ principal: "Criou processo", detalhe: "" });
  });
});

describe("acaoLegivel", () => {
  it("traduz o token técnico dentro da frase", () => {
    expect(acaoLegivel("Alterou personal_data")).toBe("Alterou Dados pessoais");
    expect(acaoLegivel("Atribuiu consultor")).toBe("Atribuiu consultor");
    expect(acaoLegivel("")).toBe("Atualização");
  });
});

describe("integração: o que a Timeline e o Histórico mostram", () => {
  const ITEM = {
    id: "h1", action: "Atribuiu intermediário", field: "assigned_mediador_ids",
    old_value: [], new_value: ["u-9f8e7d"], user_name: "Carla", created_at: "2026-10-16T10:00:00Z",
    // a frase que o SERVIDOR calcula traz a chave crua e os ids — é ela que não pode chegar ao ecrã
    description: "Atribuiu intermediário: assigned_mediador_ids → ['u-9f8e7d']",
  };

  it("o Histórico de Auditoria ignora a frase crua do servidor", () => {
    const texto = describeAuditEvent(ITEM);
    expect(texto).not.toMatch(/assigned_|u-9f8e7d/);
  });

  it("a Timeline do Resumo mostra o distintivo traduzido", () => {
    const [evento] = buildSummaryTimeline({ id: "p" }, [ITEM]);
    expect(evento.description).toBe("Intermediários atualizados");
    expect(evento.title).toBe("Atribuiu intermediário");
  });

  it("a mudança de fase não é tocada (contraprova)", () => {
    const fase = { id: "h2", action: "Moveu processo", field: "status", old_value: "novo", new_value: "em_analise", created_at: "2026-10-16T11:00:00Z" };
    expect(describeAuditEvent(fase)).toBe("Fase alterada de novo para em_analise");
    expect(buildSummaryTimeline(null, [fase])[0].description).toBe("novo → em_analise");
  });

  it("um registo antigo sem `field` mantém a frase do servidor", () => {
    expect(describeAuditEvent({ action: "x", description: "Enviou o link" })).toBe("Enviou o link");
  });
});
