import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAVES_DO_HUB,
  EVENTO_DA_SESSAO_DO_PORTAL,
  aplicarEscolha,
  detalheDoProcesso,
  guardarHub,
  lerHub,
  limparHub,
  listaDeProcessos,
  podeTrocarDeProcesso,
  precisaDeEscolher,
  rotuloDoProcesso,
  temHub,
  voltarAoHub,
} from "./portalHub";
import { CHAVES_DA_SESSAO_DO_PORTAL, limparSessaoDoPortal } from "./portalInativo";

const P1 = { id: "p-1", numero: 11, tipo_rotulo: "Crédito Habitação", empresa: "Power Real Estate", estado_rotulo: "Fase Bancária" };
const P2 = { id: "p-2", numero: 22, tipo_rotulo: "Crédito Pessoal", empresa: "Domus", estado_rotulo: "Clientes em Espera" };

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("listaDeProcessos — a forma que o servidor devolve normaliza-se UMA vez", () => {
  it.each([[undefined], [null], ["x"], [{}], [{ 0: P1 }], [42]])("%j não é uma lista", (valor) => {
    expect(listaDeProcessos(valor)).toEqual([]);
  });

  it("deita fora o que não tem id (texto)", () => {
    expect(listaDeProcessos([P1, null, {}, { id: 3 }, { id: "" }, "x", P2])).toEqual([P1, P2]);
  });
});

describe("temHub", () => {
  it("só com dois ou mais processos", () => {
    expect(temHub([])).toBe(false);
    expect(temHub([P1])).toBe(false);
    expect(temHub([P1, P2])).toBe(true);
    expect(temHub({ 0: P1, 1: P2 })).toBe(false);
  });
});

describe("guardarHub", () => {
  it("guarda o token, a lista e o processo escolhido", () => {
    expect(guardarHub({ hub_token: "H", processos: [P1, P2] }, { escolhido: "p-2" })).toBe(true);
    expect(lerHub()).toEqual({ token: "H", processos: [P1, P2], escolhido: "p-2" });
  });

  it("sem escolhido fica por escolher", () => {
    guardarHub({ hub_token: "H", processos: [P1, P2] });
    expect(lerHub().escolhido).toBe("");
  });

  it("com um só processo NÃO há Hub e não se guarda a credencial", () => {
    expect(guardarHub({ hub_token: "H", processos: [P1] })).toBe(false);
    expect(lerHub()).toEqual({ token: "", processos: [], escolhido: "" });
    expect(localStorage.getItem("portalHubToken")).toBeNull();
  });

  it("sem token do Hub não há Hub", () => {
    expect(guardarHub({ processos: [P1, P2] })).toBe(false);
    expect(guardarHub({ hub_token: 5, processos: [P1, P2] })).toBe(false);
  });

  it("uma resposta sem Hub esquece o de uma sessão anterior", () => {
    guardarHub({ hub_token: "H", processos: [P1, P2] });
    guardarHub({ processos: [] });
    expect(lerHub().token).toBe("");
  });
});

describe("lerHub", () => {
  it("um JSON estragado é uma lista vazia, não um erro", () => {
    localStorage.setItem("portalHubProcessos", "{não é json");
    expect(lerHub().processos).toEqual([]);
  });

  it("um JSON que não é uma lista é uma lista vazia", () => {
    localStorage.setItem("portalHubProcessos", JSON.stringify({ id: "x" }));
    expect(lerHub().processos).toEqual([]);
  });

  it("um armazenamento bloqueado não levanta", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    expect(lerHub()).toEqual({ token: "", processos: [], escolhido: "" });
  });
});

describe("precisaDeEscolher", () => {
  const hub = (extra) => ({ token: "H", processos: [P1, P2], escolhido: "", ...extra });

  it("com 2+ processos e nenhum escolhido, sim", () => {
    expect(precisaDeEscolher(hub())).toBe(true);
  });

  it("depois de escolher, não", () => {
    expect(precisaDeEscolher(hub({ escolhido: "p-1" }))).toBe(false);
  });

  it("um escolhido que já não está na lista volta a mostrar o Hub", () => {
    expect(precisaDeEscolher(hub({ escolhido: "p-antigo" }))).toBe(true);
  });

  it("sem token ou com menos de 2 processos, não", () => {
    expect(precisaDeEscolher(hub({ token: "" }))).toBe(false);
    expect(precisaDeEscolher(hub({ processos: [P1] }))).toBe(false);
    expect(precisaDeEscolher(undefined)).toBe(false);
    expect(precisaDeEscolher(hub({ processos: { 0: P1, 1: P2 } }))).toBe(false);
  });
});

describe("podeTrocarDeProcesso", () => {
  it("só com Hub", () => {
    expect(podeTrocarDeProcesso({ token: "H", processos: [P1, P2] })).toBe(true);
    expect(podeTrocarDeProcesso({ token: "", processos: [P1, P2] })).toBe(false);
    expect(podeTrocarDeProcesso({ token: "H", processos: [P1] })).toBe(false);
  });
});

describe("os rótulos", () => {
  it("«Tipo · Empresa»", () => {
    expect(rotuloDoProcesso(P1)).toBe("Crédito Habitação · Power Real Estate");
  });

  it("sem empresa, só o tipo; sem nada, «Processo»", () => {
    expect(rotuloDoProcesso({ tipo_rotulo: "Seguros", empresa: null })).toBe("Seguros");
    expect(rotuloDoProcesso({})).toBe("Processo");
    expect(rotuloDoProcesso({ tipo_rotulo: "Seguros", empresa: "  " })).toBe("Seguros");
  });

  it("o detalhe junta o número e a fase, e diz só o que há", () => {
    expect(detalheDoProcesso(P1)).toBe("Processo n.º 11 · Fase Bancária");
    expect(detalheDoProcesso({ numero: 0 })).toBe("Processo n.º 0");
    expect(detalheDoProcesso({ estado_rotulo: "Fase" })).toBe("Fase");
    expect(detalheDoProcesso({})).toBe("");
  });
});

describe("aplicarEscolha — o token de sessão passa a ser o do processo escolhido", () => {
  it("troca o token e regista o processo", () => {
    localStorage.setItem("portalToken", "antigo");
    const aviso = vi.fn();
    window.addEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    expect(aplicarEscolha({ token: "novo", process_id: "p-2" })).toBe(true);
    window.removeEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    expect(localStorage.getItem("portalToken")).toBe("novo");
    expect(localStorage.getItem("portal_token")).toBe("novo");
    expect(localStorage.getItem("portalProcessId")).toBe("p-2");
    expect(localStorage.getItem("portalProcessoEscolhido")).toBe("p-2");
    expect(aviso).toHaveBeenCalledTimes(1);
  });

  it.each([[{}], [{ token: "t" }], [{ process_id: "p" }], [{ token: "", process_id: "p" }], [null]])(
    "%j não é uma escolha e não mexe em nada",
    (resposta) => {
      localStorage.setItem("portalToken", "antigo");
      expect(aplicarEscolha(resposta)).toBe(false);
      expect(localStorage.getItem("portalToken")).toBe("antigo");
    },
  );
});

describe("voltarAoHub", () => {
  it("esquece o processo escolhido e avisa, sem terminar a sessão", () => {
    guardarHub({ hub_token: "H", processos: [P1, P2] }, { escolhido: "p-1" });
    localStorage.setItem("portalToken", "tok");
    const aviso = vi.fn();
    window.addEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    voltarAoHub();
    window.removeEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    expect(precisaDeEscolher(lerHub())).toBe(true);
    expect(localStorage.getItem("portalToken")).toBe("tok");
    expect(aviso).toHaveBeenCalledTimes(1);
  });
});

describe("terminar a sessão esquece o Hub", () => {
  it("as chaves do Hub fazem parte das da sessão do Portal (uma só lista de verdade)", () => {
    for (const chave of CHAVES_DO_HUB) expect(CHAVES_DA_SESSAO_DO_PORTAL).toContain(chave);
  });

  it("limparSessaoDoPortal apaga a credencial do Hub e avisa", () => {
    guardarHub({ hub_token: "H", processos: [P1, P2] }, { escolhido: "p-1" });
    const aviso = vi.fn();
    window.addEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    limparSessaoDoPortal();
    window.removeEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    expect(lerHub().token).toBe("");
    expect(aviso).toHaveBeenCalled();
  });

  it("limparHub apaga as três chaves", () => {
    guardarHub({ hub_token: "H", processos: [P1, P2] }, { escolhido: "p-1" });
    limparHub();
    for (const chave of CHAVES_DO_HUB) expect(localStorage.getItem(chave)).toBeNull();
  });
});
