/**
 * Etiquetas das redes de empresas (Lote 4, ponto 5).
 *
 * O teste central é o da AMBIGUIDADE: é ele que impede a etiqueta bonita
 * de esconder a gralha de slug que o `CompanyNetworkField` existe para
 * apanhar.
 */
import { describe, expect, it } from "vitest";

import {
  ETIQUETA_SEM_REDE,
  SEM_REDE,
  etiquetaDaRede,
  etiquetasDeRede,
  normalizarRede,
} from "./redesDeEmpresas";

describe("normalizarRede", () => {
  it("trata nulo, vazio e espaços como «sem rede»", () => {
    expect(normalizarRede(null)).toBe(SEM_REDE);
    expect(normalizarRede(undefined)).toBe(SEM_REDE);
    expect(normalizarRede("   ")).toBe(SEM_REDE);
  });

  it("apara os espaços — um espaço à direita é OUTRA rede", () => {
    // A mesma razão do `onChange` aparado no CompanyNetworkField: a
    // diferença entre "x" e "x " é invisível e parte o isolamento.
    expect(normalizarRede(" grupo_power ")).toBe("grupo_power");
  });
});

describe("etiquetaDaRede", () => {
  it("transforma o slug em texto legível", () => {
    expect(etiquetaDaRede("grupo_power_precision")).toBe("Power Precision");
    expect(etiquetaDaRede("domus")).toBe("Domus");
  });

  it("aceita hífens e maiúsculas", () => {
    expect(etiquetaDaRede("GRUPO-POWER")).toBe("Power");
  });

  it("diz «Sem grupo» quando não há rede", () => {
    expect(etiquetaDaRede(null)).toBe(ETIQUETA_SEM_REDE);
    expect(etiquetaDaRede("")).toBe(ETIQUETA_SEM_REDE);
  });

  it("não engole o nome quando a rede se chama só «grupo»", () => {
    // Descartar o prefixo sem olhar ao que sobra devolvia "" — uma
    // etiqueta vazia é indistinguível de "sem rede", que é precisamente
    // a confusão que não se pode ter neste campo.
    expect(etiquetaDaRede("grupo")).toBe("Grupo");
  });
});

describe("etiquetasDeRede", () => {
  it("embeleza quando não há ambiguidade", () => {
    const mapa = etiquetasDeRede([
      { network_id: "grupo_power_precision" },
      { network_id: "domus" },
    ]);
    expect(mapa.get("grupo_power_precision").etiqueta).toBe("Power Precision");
    expect(mapa.get("domus").etiqueta).toBe("Domus");
    expect(mapa.get("grupo_power_precision").ambigua).toBe(false);
  });

  it("MOSTRA O SLUG CRU quando dois slugs dão o mesmo rótulo", () => {
    // `grupo_power` e `grupo-power` são DUAS redes — duas ilhas — e o
    // rótulo bonito das duas é "Power". Embelezar aqui fazia o
    // administrador ver um grupo onde existem dois, e o isolamento
    // quebrado parecia correcto no ecrã.
    const mapa = etiquetasDeRede([
      { network_id: "grupo_power" },
      { network_id: "grupo-power" },
    ]);
    expect(mapa.get("grupo_power").ambigua).toBe(true);
    expect(mapa.get("grupo_power").etiqueta).toBe("grupo_power");
    expect(mapa.get("grupo-power").etiqueta).toBe("grupo-power");
  });

  it("«Sem grupo» nunca é tratado como ambíguo com um slug", () => {
    // Duas empresas sem rede são dois casos do MESMO estado (ilha), não
    // duas redes a colidir: mostrar-lhes o slug cru seria mostrar vazio.
    const mapa = etiquetasDeRede([{ network_id: null }, { network_id: "" }]);
    expect(mapa.get(SEM_REDE).etiqueta).toBe(ETIQUETA_SEM_REDE);
    expect(mapa.get(SEM_REDE).ambigua).toBe(false);
  });

  it("aguenta uma lista vazia ou inválida", () => {
    expect(etiquetasDeRede([]).size).toBe(0);
    expect(etiquetasDeRede(null).size).toBe(0);
  });
});
