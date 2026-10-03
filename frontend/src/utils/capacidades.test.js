import { describe, it, expect } from "vitest";

import {
  CRIAR_PROCESSO,
  EXPORTAR_PROCESSO,
  capacidadesDoPapel,
  motivoDoBloqueio,
  podeFazer,
} from "./capacidades";

const INDEXADOR = {
  id: "u2",
  role: "indexacao",
  capabilities_por_papel: {
    indexacao: { PROCESS_CREATE: false, PROCESS_EXPORT: false },
  },
};

const CONSULTOR_QUE_E_DIRETOR = {
  id: "u1",
  role: "consultor",
  capabilities_por_papel: {
    consultor: { PROCESS_CREATE: true, PROCESS_EXPORT: false },
    diretor: { PROCESS_CREATE: true, PROCESS_EXPORT: true },
  },
};

describe("podeFazer — o papel ACTIVO manda", () => {
  it("o indexador não cria processos", () => {
    expect(podeFazer(INDEXADOR, CRIAR_PROCESSO, "indexacao")).toBe(false);
  });

  it("o consultor cria processos", () => {
    expect(podeFazer(CONSULTOR_QUE_E_DIRETOR, CRIAR_PROCESSO, "consultor")).toBe(true);
  });

  it("entrar COMO diretor muda a resposta", () => {
    // O defeito original: o `hasPermission` lia `user.role` e dava a resposta
    // do cargo base, enquanto a porta do servidor usa o efectivo.
    expect(podeFazer(CONSULTOR_QUE_E_DIRETOR, EXPORTAR_PROCESSO, "consultor")).toBe(false);
    expect(podeFazer(CONSULTOR_QUE_E_DIRETOR, EXPORTAR_PROCESSO, "diretor")).toBe(true);
  });

  it("o admin e o CEO têm bypass", () => {
    for (const papel of ["admin", "ceo", "ADMIN"]) {
      expect(podeFazer({ id: "a", role: papel }, CRIAR_PROCESSO, papel)).toBe(true);
    }
  });

  it("uma capacidade conhecida e ausente do mapa é NÃO", () => {
    expect(podeFazer(INDEXADOR, "PROCESS_DELETE", "indexacao")).toBe(false);
  });

  it("sem utilizador ou sem capacidade recusa", () => {
    expect(podeFazer(null, CRIAR_PROCESSO, "consultor")).toBe(false);
    expect(podeFazer(INDEXADOR, "", "indexacao")).toBe(false);
  });
});

describe("sem contrato, NÃO se esconde nada", () => {
  it("um utilizador sem mapa nenhum mantém os botões", () => {
    // Falhar fechado aqui esconderia TODOS os botões a TODOS no dia de um
    // deploy desalinhado — e um ecrã sem botões não produz erro nenhum.
    expect(podeFazer({ id: "u", role: "consultor" }, CRIAR_PROCESSO, "consultor")).toBe(true);
  });

  it("capacidadesDoPapel distingue «não sei» de «nenhuma»", () => {
    expect(capacidadesDoPapel({ id: "u", role: "consultor" }, "consultor")).toBeNull();
    expect(capacidadesDoPapel(INDEXADOR, "indexacao")).toEqual({
      PROCESS_CREATE: false,
      PROCESS_EXPORT: false,
    });
  });

  it("recorre ao mapa plano das sessões anteriores a este lote", () => {
    const antigo = {
      id: "u",
      role: "indexacao",
      permissions: { capabilities: { PROCESS_CREATE: false } },
    };
    expect(podeFazer(antigo, CRIAR_PROCESSO, "indexacao")).toBe(false);
  });

  it("um papel que não está no mapa cai no recurso, não no vazio", () => {
    const user = {
      id: "u",
      role: "consultor",
      capabilities_por_papel: { consultor: { PROCESS_CREATE: true } },
    };
    // Papel inexistente no mapa e sem mapa plano → "não sei" → deixa passar.
    expect(podeFazer(user, CRIAR_PROCESSO, "intermediario")).toBe(true);
  });
});

describe("o cadeado explica-se", () => {
  it("cada capacidade conhecida tem motivo próprio", () => {
    expect(motivoDoBloqueio(CRIAR_PROCESSO)).toMatch(/não cria processos/i);
  });

  it("uma capacidade desconhecida nunca fica sem texto", () => {
    expect(motivoDoBloqueio("XPTO")).toBeTruthy();
  });
});
