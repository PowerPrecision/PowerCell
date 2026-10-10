import { describe, expect, it } from "vitest";

import {
  DESLIGADO,
  SEGUIR_PERFIL,
  SEMPRE_ATIVO,
  descricaoDoEstado,
  enabledDoPedido,
  normalizarPerfis,
  normalizarUtilizadores,
  valorDaPessoa,
} from "./historyTracking";

describe("a pessoa tem TRÊS estados, não dois", () => {
  it("o servidor (true/false/null) ↔ o selector", () => {
    expect(valorDaPessoa(true)).toBe(SEMPRE_ATIVO);
    expect(valorDaPessoa(false)).toBe(DESLIGADO);
    expect(valorDaPessoa(null)).toBe(SEGUIR_PERFIL);
    expect(valorDaPessoa(undefined)).toBe(SEGUIR_PERFIL);
  });

  it("e de volta: «segue o perfil» é null (remove o override), nunca false", () => {
    expect(enabledDoPedido(SEMPRE_ATIVO)).toBe(true);
    expect(enabledDoPedido(DESLIGADO)).toBe(false);
    expect(enabledDoPedido(SEGUIR_PERFIL)).toBeNull();
  });

  it("é uma bijecção: ida e volta devolve o mesmo", () => {
    for (const valor of [SEMPRE_ATIVO, DESLIGADO, SEGUIR_PERFIL]) {
      expect(valorDaPessoa(enabledDoPedido(valor))).toBe(valor);
    }
  });
});

describe("normalizarPerfis", () => {
  it("lê a forma REAL do servidor e mantém o bloqueio e o motivo", () => {
    const res = normalizarPerfis({
      perfis: [
        { role: "consultor", enabled: false, locked: false, motivo: null },
        { role: "indexacao", enabled: false, locked: true, motivo: "Sempre silencioso" },
      ],
      padrao: true,
    });
    expect(res).toEqual([
      { role: "consultor", enabled: false, locked: false, motivo: null },
      { role: "indexacao", enabled: false, locked: true, motivo: "Sempre silencioso" },
    ]);
  });

  it.each([undefined, null, {}, { perfis: null }, { perfis: {} }])(
    "uma forma inesperada (%j) dá lista vazia — Array.isArray, nunca `|| []`",
    (forma) => {
      expect(normalizarPerfis(forma)).toEqual([]);
    },
  );

  it("um perfil sem enabled explícito NÃO conta como ativo (falha para o lado de não prometer)", () => {
    expect(normalizarPerfis({ perfis: [{ role: "x" }] })[0].enabled).toBe(false);
  });
});

describe("normalizarUtilizadores", () => {
  it("lê a forma real e distingue override de estado efectivo", () => {
    const res = normalizarUtilizadores({
      utilizadores: [
        { id: "u1", name: "Ana", email: "a@x.pt", role: "consultor", track_history: null, efectivo: false, bloqueado: false },
        { id: "u2", name: "Rui", email: "r@x.pt", role: "indexacao", track_history: null, efectivo: false, bloqueado: true },
      ],
      total: 7,
    });
    expect(res.total).toBe(7);
    expect(res.utilizadores[0].track_history).toBeNull();
    expect(res.utilizadores[0].efectivo).toBe(false);
    expect(res.utilizadores[1].bloqueado).toBe(true);
  });

  it("descarta linhas sem id e usa o email quando falta o nome", () => {
    const res = normalizarUtilizadores({
      utilizadores: [{ name: "sem id" }, { id: "u3", email: "z@x.pt" }],
    });
    expect(res.utilizadores.map((u) => u.id)).toEqual(["u3"]);
    expect(res.utilizadores[0].name).toBe("z@x.pt");
    expect(res.total).toBe(2);
  });

  it.each([undefined, null, {}, { utilizadores: null }])("forma inesperada (%j)", (forma) => {
    expect(normalizarUtilizadores(forma)).toEqual({ utilizadores: [], total: 0 });
  });
});

describe("descricaoDoEstado", () => {
  it("diz o que a pessoa realmente vai ter", () => {
    expect(descricaoDoEstado({ bloqueado: true, efectivo: false })).toMatch(/Indexação/);
    expect(descricaoDoEstado({ bloqueado: false, efectivo: true })).toBe("Regista no histórico");
    expect(descricaoDoEstado({ bloqueado: false, efectivo: false })).toBe("Não regista no histórico");
  });
});
