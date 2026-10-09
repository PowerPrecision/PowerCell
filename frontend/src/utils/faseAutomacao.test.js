import { describe, expect, it } from "vitest";
import {
  MAXIMO_DE_MODELOS_POR_FASE,
  automacaoDaFase,
  automacaoVazia,
  errosDaAutomacao,
  modeloVazio,
  payloadDaAutomacao,
  payloadDaAutomacaoNaCriacao,
  resumoDaAutomacao,
} from "./faseAutomacao";

const MODELO = {
  id: "t1", title: "Pedir IRS", priority: "Alta", due_in_days: 5, assigned_role: "intermediario",
};

describe("automacaoDaFase — do servidor para o formulário", () => {
  it("null e ausente são «herdar»; [] é «configurado como nada»", () => {
    expect(automacaoDaFase({})).toEqual({ papeis: null, modelos: null });
    expect(automacaoDaFase({ auto_assign_roles: null, task_templates: null }))
      .toEqual({ papeis: null, modelos: null });
    expect(automacaoDaFase({ auto_assign_roles: [], task_templates: [] }))
      .toEqual({ papeis: [], modelos: [] });
  });

  it.each([undefined, null, "x", 3, { a: 1 }])(
    "um valor que não é lista (%j) nunca rebenta e conta como «herdar»",
    (valor) => {
      expect(automacaoDaFase({ auto_assign_roles: valor, task_templates: valor }))
        .toEqual({ papeis: null, modelos: null });
    },
  );

  it("o prazo passa a texto e o resto mantém-se", () => {
    const { modelos } = automacaoDaFase({ task_templates: [MODELO] });
    expect(modelos[0]).toEqual({
      id: "t1", title: "Pedir IRS", priority: "Alta", due_in_days: "5", assigned_role: "intermediario",
    });
  });

  it("prazo 0 é um prazo (não «sem prazo»)", () => {
    expect(automacaoDaFase({ task_templates: [{ ...MODELO, due_in_days: 0 }] }).modelos[0].due_in_days)
      .toBe("0");
  });

  it("valores desconhecidos caem nos de recurso em vez de chegarem ao formulário", () => {
    const { modelos, papeis } = automacaoDaFase({
      auto_assign_roles: ["consultor", "indexacao"],
      task_templates: [{ title: "x", priority: "Urgente", assigned_role: "admin", due_in_days: "3" }],
    });
    expect(papeis).toEqual(["consultor"]);
    expect(modelos[0]).toMatchObject({ priority: "Média", assigned_role: "todos", due_in_days: "" });
  });
});

describe("payloadDaAutomacao — do formulário para o servidor", () => {
  it("devolve SEMPRE as duas chaves; null manda voltar a herdar", () => {
    expect(payloadDaAutomacao(automacaoVazia()))
      .toEqual({ auto_assign_roles: null, task_templates: null });
  });

  it("lista vazia segue como lista vazia (não como null)", () => {
    expect(payloadDaAutomacao({ papeis: [], modelos: [] }))
      .toEqual({ auto_assign_roles: [], task_templates: [] });
  });

  it("converte o prazo para número, '' para null e 0 para 0", () => {
    const { task_templates: t } = payloadDaAutomacao({
      papeis: null,
      modelos: [
        { ...modeloVazio(), title: "a", due_in_days: "" },
        { ...modeloVazio(), title: "b", due_in_days: "0" },
        { ...modeloVazio(), title: "c", due_in_days: "12" },
      ],
    });
    expect(t.map((m) => m.due_in_days)).toEqual([null, 0, 12]);
  });

  it("preserva o id existente e não inventa um para as tarefas novas", () => {
    const { task_templates: t } = payloadDaAutomacao({
      papeis: null,
      modelos: [{ ...modeloVazio(), id: "t1", title: "a" }, { ...modeloVazio(), title: "b" }],
    });
    expect(t[0].id).toBe("t1");
    expect("id" in t[1]).toBe(false);
  });

  it("apara o título", () => {
    expect(payloadDaAutomacao({ papeis: null, modelos: [{ ...modeloVazio(), title: "  a  " }] })
      .task_templates[0].title).toBe("a");
  });

  it("não partilha a lista de papéis com o formulário", () => {
    const papeis = ["consultor"];
    const out = payloadDaAutomacao({ papeis, modelos: null });
    out.auto_assign_roles.push("x");
    expect(papeis).toEqual(["consultor"]);
  });

  it("ida e volta: o que o servidor devolve regressa igual", () => {
    const fase = { auto_assign_roles: ["intermediario"], task_templates: [MODELO] };
    expect(payloadDaAutomacao(automacaoDaFase(fase)))
      .toEqual({ auto_assign_roles: ["intermediario"], task_templates: [MODELO] });
  });
});

describe("payloadDaAutomacaoNaCriacao", () => {
  it("o que é null não se envia: a fase nasce a herdar", () => {
    expect(payloadDaAutomacaoNaCriacao(automacaoVazia())).toEqual({});
  });
  it("o que está configurado vai, mesmo vazio", () => {
    expect(payloadDaAutomacaoNaCriacao({ papeis: [], modelos: null }))
      .toEqual({ auto_assign_roles: [] });
  });
});

describe("errosDaAutomacao", () => {
  it("sem tarefas não há erros", () => {
    expect(errosDaAutomacao(automacaoVazia())).toEqual([]);
    expect(errosDaAutomacao({ papeis: [], modelos: [] })).toEqual([]);
  });

  it.each(["", "   "])("título vazio (%j) é um erro com o número da tarefa", (titulo) => {
    const erros = errosDaAutomacao({ papeis: null, modelos: [{ ...modeloVazio(), title: titulo }] });
    expect(erros).toHaveLength(1);
    expect(erros[0]).toMatch(/Tarefa 1/);
  });

  it.each(["abc", "-1", "1.5", "366", "99999"])("prazo inválido (%s) é um erro", (dias) => {
    const erros = errosDaAutomacao({
      papeis: null, modelos: [{ ...modeloVazio(), title: "a", due_in_days: dias }],
    });
    expect(erros).toHaveLength(1);
  });

  it.each(["", "0", "365"])("prazo válido (%j) passa", (dias) => {
    expect(errosDaAutomacao({
      papeis: null, modelos: [{ ...modeloVazio(), title: "a", due_in_days: dias }],
    })).toEqual([]);
  });

  it("acima do tecto é um erro", () => {
    const modelos = Array.from({ length: MAXIMO_DE_MODELOS_POR_FASE + 1 }, () => ({
      ...modeloVazio(), title: "a",
    }));
    expect(errosDaAutomacao({ papeis: null, modelos })[0]).toMatch(/máximo/);
  });

  it("aponta a tarefa certa quando é a segunda que está mal", () => {
    const erros = errosDaAutomacao({
      papeis: null, modelos: [{ ...modeloVazio(), title: "a" }, { ...modeloVazio(), title: "" }],
    });
    expect(erros[0]).toMatch(/Tarefa 2/);
  });
});

describe("resumoDaAutomacao", () => {
  it("fase sem configuração não tem resumo", () => {
    expect(resumoDaAutomacao({})).toBeNull();
  });
  it("diz o que atribui e quantas tarefas cria", () => {
    expect(resumoDaAutomacao({ auto_assign_roles: ["consultor", "intermediario"], task_templates: [MODELO] }))
      .toBe("atribui consultor + intermediario · 1 tarefa");
  });
  it("distingue «não atribui» e «sem tarefas» de «não configurado»", () => {
    expect(resumoDaAutomacao({ auto_assign_roles: [], task_templates: [] }))
      .toBe("não atribui · sem tarefas");
  });
  it("pluraliza", () => {
    expect(resumoDaAutomacao({ task_templates: [MODELO, MODELO] })).toBe("2 tarefas");
  });
});
