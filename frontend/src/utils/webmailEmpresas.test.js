/**
 * Ponto 8, Fase 3 — as regras dos separadores.
 *
 * Dois testes carregam o peso todo: o que exige que a barra desapareça
 * com uma empresa só (a regra de zero ruído), e o que recusa uma empresa
 * pedida que já não está na lista — sem ele, um `company_id` guardado de
 * um acesso revogado levava a pedidos que o backend recusa com 404, e o
 * utilizador via uma caixa vazia sem perceber porquê.
 */
import { describe, it, expect } from "vitest";
import {
  deveMostrarSeparadores,
  resolverEmpresaActiva,
  rotuloDaEmpresa,
  estadoDaSincronizacao,
} from "./webmailEmpresas";

const empresa = (id, nome) => ({ company_id: id, company_name: nome });

describe("deveMostrarSeparadores", () => {
  it("esconde a barra com uma empresa só", () => {
    // Zero ruído: um separador solitário rouba uma linha de ecrã à caixa.
    expect(deveMostrarSeparadores([empresa("power", "Power")])).toBe(false);
  });

  it("mostra a barra a partir de duas", () => {
    expect(deveMostrarSeparadores([
      empresa("power", "Power"), empresa("domus", "Domus"),
    ])).toBe(true);
  });

  it("esconde a barra sem empresas nenhumas", () => {
    expect(deveMostrarSeparadores([])).toBe(false);
    expect(deveMostrarSeparadores(null)).toBe(false);
    expect(deveMostrarSeparadores(undefined)).toBe(false);
  });
});

describe("resolverEmpresaActiva", () => {
  const lista = [empresa("power", "Power"), empresa("domus", "Domus")];

  it("honra a empresa pedida quando ela existe", () => {
    expect(resolverEmpresaActiva(lista, "domus").company_id).toBe("domus");
  });

  it("cai na primeira quando a pedida já não existe", () => {
    // Acesso revogado, ou um link antigo. Insistir no id pedido dava
    // 404 no backend e uma caixa vazia sem explicação.
    expect(resolverEmpresaActiva(lista, "empresa-que-saiu").company_id)
      .toBe("power");
  });

  it("cai na primeira sem pedido nenhum", () => {
    expect(resolverEmpresaActiva(lista, "").company_id).toBe("power");
    expect(resolverEmpresaActiva(lista, null).company_id).toBe("power");
  });

  it("devolve null sem empresas", () => {
    expect(resolverEmpresaActiva([], "power")).toBeNull();
    expect(resolverEmpresaActiva(null, "power")).toBeNull();
  });

  it("descarta entradas sem company_id", () => {
    const sujo = [null, { company_name: "Sem id" }, empresa("power", "Power")];
    expect(resolverEmpresaActiva(sujo, "").company_id).toBe("power");
  });

  it("apara espaços no id pedido", () => {
    expect(resolverEmpresaActiva(lista, "  domus  ").company_id).toBe("domus");
  });
});

describe("rotuloDaEmpresa", () => {
  it("usa o nome", () => {
    expect(rotuloDaEmpresa(empresa("c1", "Power Real Estate")))
      .toBe("Power Real Estate");
  });

  it("cai no id quando não há nome — nunca um separador em branco", () => {
    expect(rotuloDaEmpresa(empresa("c1", ""))).toBe("c1");
    expect(rotuloDaEmpresa({ company_id: "c1" })).toBe("c1");
  });

  it("aguenta nulo", () => {
    expect(rotuloDaEmpresa(null)).toBe("");
  });
});

describe("estadoDaSincronizacao", () => {
  const agora = new Date("2026-09-24T12:00:00");

  it("em curso vence tudo o resto", () => {
    const r = estadoDaSincronizacao({
      syncing: true, ultimaSinc: new Date("2026-09-24T11:00:00"), agora,
    });
    expect(r.emCurso).toBe(true);
    expect(r.texto).toBe("A sincronizar…");
  });

  it("nunca sincronizado não é um erro", () => {
    // É o estado normal ao abrir a página. Pintá-lo de alarme ensinava
    // toda a gente a ignorar o indicador — a lição do monitor de jobs.
    const r = estadoDaSincronizacao({ syncing: false, ultimaSinc: null, agora });
    expect(r.estado).toBe("por-sincronizar");
    expect(r.texto).toBe("Por sincronizar");
  });

  it("acabado de sincronizar", () => {
    const r = estadoDaSincronizacao({
      ultimaSinc: new Date("2026-09-24T11:59:40"), agora,
    });
    expect(r.texto).toBe("Actualizado agora");
  });

  it("conta os minutos", () => {
    const r = estadoDaSincronizacao({
      ultimaSinc: new Date("2026-09-24T11:43:00"), agora,
    });
    expect(r.texto).toBe("Actualizado há 17 min");
  });

  it("passa a horas a partir dos 60 minutos", () => {
    const r = estadoDaSincronizacao({
      ultimaSinc: new Date("2026-09-24T09:00:00"), agora,
    });
    expect(r.texto).toBe("Actualizado há 3h");
    expect(r.estado).toBe("desactualizado");
  });

  it("um relógio adiantado lê como 'agora', nunca como tempo negativo", () => {
    // O `lastSyncTime` vem do cliente e pode vir do futuro. O ramo
    // `minutos < 1` cobre-o: "Actualizado há -4 min" lia como defeito.
    const r = estadoDaSincronizacao({
      ultimaSinc: new Date("2026-09-24T12:05:00"), agora,
    });
    expect(r.texto).toBe("Actualizado agora");
  });

  it("uma data inválida não rebenta o cabeçalho", () => {
    const r = estadoDaSincronizacao({ ultimaSinc: "isto não é data", agora });
    expect(r.estado).toBe("por-sincronizar");
  });

  it("sem argumentos nenhuns devolve um estado utilizável", () => {
    expect(estadoDaSincronizacao().estado).toBe("por-sincronizar");
  });
});
