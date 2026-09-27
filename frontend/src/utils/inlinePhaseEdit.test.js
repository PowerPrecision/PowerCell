/**
 * Ponto 16 — Edição Inline de Fases na Listagem.
 *
 * O que estes testes protegem: a listagem passa a mudar a fase de um
 * processo sem abrir os Detalhes. Isso é conveniente e é exactamente
 * por isso que é perigoso — um clique acidental numa linha muda um
 * estado de negócio, dispara automações e notifica o cliente por email.
 * As regras de QUEM pode e de QUANDO não pode têm de viver num sítio
 * puro e testado, não espalhadas pelo JSX da tabela.
 */
import { describe, it, expect } from "vitest";
import {
  PAPEIS_QUE_MUDAM_FASE,
  FASES_TERMINAIS,
  podeEditarFase,
  opcoesDeFase,
  deveGravarNovaFase,
  precisaDeRecarregar,
} from "./inlinePhaseEdit";

describe("podeEditarFase", () => {
  it("permite os papéis que o backend aceita em can_update_status", () => {
    for (const papel of PAPEIS_QUE_MUDAM_FASE) {
      expect(
        podeEditarFase({ role: papel, status: "fase_bancaria" }),
      ).toBe(true);
    }
  });

  it("recusa os papéis que o backend NÃO aceita", () => {
    // Indexação e parceiro não estão em `can_update_status`: mostrar-lhes
    // o dropdown seria prometer uma acção que o servidor devolve com 403.
    for (const papel of ["indexacao", "parceiro", "cliente"]) {
      expect(
        podeEditarFase({ role: papel, status: "fase_bancaria" }),
      ).toBe(false);
    }
  });

  it("recusa sem papel nenhum", () => {
    expect(podeEditarFase({ role: null, status: "fase_bancaria" })).toBe(false);
    expect(podeEditarFase({})).toBe(false);
  });

  it("ignora maiúsculas e espaços no papel", () => {
    expect(podeEditarFase({ role: " Consultor ", status: "cpcv" })).toBe(true);
  });

  it("bloqueia estados terminais para quem não é admin/CEO", () => {
    // Espelha `assert_process_editable_for_role`: o servidor devolve 403.
    for (const terminal of FASES_TERMINAIS) {
      expect(podeEditarFase({ role: "consultor", status: terminal })).toBe(false);
    }
  });

  it("deixa admin e CEO editar um estado terminal", () => {
    expect(podeEditarFase({ role: "admin", status: "concluido" })).toBe(true);
    expect(podeEditarFase({ role: "ceo", status: "cancelado" })).toBe(true);
  });

  it("bloqueia um processo eliminado mesmo para admin", () => {
    // `is_deleted` é soft-delete: a linha aparece na vista "Eliminados"
    // com o botão Restaurar. Mudar-lhe a fase a partir dali seria
    // ressuscitá-lo pela porta das traseiras, sem restauro nem rasto.
    expect(
      podeEditarFase({ role: "admin", status: "fase_bancaria", isDeleted: true }),
    ).toBe(false);
  });
});

describe("opcoesDeFase", () => {
  const motor = [
    { name: "clientes_espera", label: "Clientes em Espera", order: 0 },
    { name: "fase_bancaria", label: "Fase Bancária", order: 1 },
    { name: "cpcv", label: "CPCV", order: 2 },
  ];

  it("devolve as fases do motor pela ordem do motor", () => {
    expect(opcoesDeFase(motor, "cpcv").map((o) => o.name)).toEqual([
      "clientes_espera",
      "fase_bancaria",
      "cpcv",
    ]);
  });

  it("usa o label do motor e cai no nome quando não há label", () => {
    const opcoes = opcoesDeFase(
      [{ name: "fase_nova" }, { name: "cpcv", label: "CPCV" }],
      "cpcv",
    );
    expect(opcoes.find((o) => o.name === "fase_nova").label).toBe("fase nova");
    expect(opcoes.find((o) => o.name === "cpcv").label).toBe("CPCV");
  });

  it("acrescenta o estado actual quando o motor não o conhece", () => {
    // Fase legada/apagada do motor: sem isto o Select abriria SEM valor
    // seleccionado e a célula mostrava-se vazia — o utilizador leria
    // "este processo não tem fase" sobre um processo que tem.
    const opcoes = opcoesDeFase(motor, "escriturado");
    expect(opcoes.map((o) => o.name)).toContain("escriturado");
    expect(opcoes.find((o) => o.name === "escriturado").foraDoMotor).toBe(true);
  });

  it("não duplica o estado actual quando o motor já o conhece", () => {
    const nomes = opcoesDeFase(motor, "cpcv").map((o) => o.name);
    expect(nomes.filter((n) => n === "cpcv")).toHaveLength(1);
  });

  it("aguenta um motor vazio, nulo ou mal formado", () => {
    expect(opcoesDeFase(null, "cpcv").map((o) => o.name)).toEqual(["cpcv"]);
    expect(opcoesDeFase([], "cpcv").map((o) => o.name)).toEqual(["cpcv"]);
    expect(opcoesDeFase([{ label: "sem nome" }, null], "cpcv").map((o) => o.name))
      .toEqual(["cpcv"]);
  });

  it("devolve lista vazia sem motor e sem estado actual", () => {
    expect(opcoesDeFase([], "")).toEqual([]);
  });

  it("descarta entradas duplicadas do próprio motor", () => {
    const comDuplicado = [...motor, { name: "cpcv", label: "CPCV (dup)" }];
    expect(
      opcoesDeFase(comDuplicado, "cpcv").filter((o) => o.name === "cpcv"),
    ).toHaveLength(1);
  });
});

describe("deveGravarNovaFase", () => {
  it("grava quando a fase muda", () => {
    expect(deveGravarNovaFase("fase_bancaria", "cpcv")).toBe(true);
  });

  it("não grava a fase que já lá está", () => {
    expect(deveGravarNovaFase("cpcv", "cpcv")).toBe(false);
  });

  it("não grava uma escolha vazia, nula ou só com espaços", () => {
    expect(deveGravarNovaFase("cpcv", "")).toBe(false);
    expect(deveGravarNovaFase("cpcv", null)).toBe(false);
    expect(deveGravarNovaFase("cpcv", "   ")).toBe(false);
  });

  it("grava quando o processo ainda não tem fase nenhuma", () => {
    expect(deveGravarNovaFase(null, "cpcv")).toBe(true);
    expect(deveGravarNovaFase("", "cpcv")).toBe(true);
  });

  it("ignora espaços em redor dos dois lados", () => {
    expect(deveGravarNovaFase(" cpcv ", "cpcv")).toBe(false);
  });
});

describe("precisaDeRecarregar", () => {
  it("não recarrega no caso comum (sem filtro, fase não terminal)", () => {
    expect(precisaDeRecarregar({ novaFase: "cpcv", viewMode: "active_only" }))
      .toBe(false);
  });

  it("recarrega quando a fase nova sai do filtro de estado activo", () => {
    expect(
      precisaDeRecarregar({ novaFase: "cpcv", statusFilter: "fase_bancaria" }),
    ).toBe(true);
  });

  it("não recarrega quando a fase nova é a própria fase filtrada", () => {
    expect(
      precisaDeRecarregar({ novaFase: "cpcv", statusFilter: "cpcv" }),
    ).toBe(false);
  });

  it("recarrega ao passar a terminal numa vista só de activos", () => {
    expect(
      precisaDeRecarregar({ novaFase: "concluido", viewMode: "active_only" }),
    ).toBe(true);
  });

  it("assume 'só activos' quando a vista não é dita", () => {
    // O default do URL é `active_only`; tratar a ausência como "tudo"
    // deixaria um processo concluído na lista de activos.
    expect(precisaDeRecarregar({ novaFase: "concluido" })).toBe(true);
  });

  it("não recarrega ao passar a terminal na vista de tudo", () => {
    expect(
      precisaDeRecarregar({ novaFase: "concluido", viewMode: "all" }),
    ).toBe(false);
  });

  it("não recarrega sem fase nenhuma", () => {
    expect(precisaDeRecarregar({ novaFase: "" })).toBe(false);
    expect(precisaDeRecarregar({})).toBe(false);
  });
});

describe("podeEditarFase — um papel só: o perfil activo", () => {
  it("decide pelo perfil activo mesmo quando o papel base é outro", () => {
    // Um indexador que também é consultor noutra empresa: com o chapéu
    // de consultor posto (e o UCR a confirmá-lo), pode mudar a fase. O
    // backend segue a mesma regra desde que a brecha do
    // `can_update_status` foi fechada — resolve por `get_effective_role`.
    expect(podeEditarFase({ role: "consultor", status: "cpcv" })).toBe(true);
  });

  it("recusa quem tem o chapéu de Indexação posto", () => {
    // Ainda que o papel base seja consultor: o produto respeita o
    // chapéu, e o servidor também.
    expect(podeEditarFase({ role: "indexacao", status: "cpcv" })).toBe(false);
  });

  it("ignora qualquer papel extra que lhe passem", () => {
    // Contraprova de que a dupla condição foi mesmo removida: um
    // `baseRole` sem permissão já não pode vetar o perfil activo.
    expect(
      podeEditarFase({ role: "consultor", baseRole: "indexacao", status: "cpcv" }),
    ).toBe(true);
  });

  it("num estado terminal basta o perfil activo ser admin ou CEO", () => {
    expect(
      podeEditarFase({ role: "admin", baseRole: "consultor", status: "concluido" }),
    ).toBe(true);
    expect(
      podeEditarFase({ role: "consultor", baseRole: "admin", status: "concluido" }),
    ).toBe(false);
  });
});
