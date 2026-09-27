/**
 * Etiquetas dos processos — Lote 5, Secção B, ponto 15.
 *
 * O armazenamento já existia (`labels: List[str]` no modelo). O que não
 * existia era o EDITOR: o comentário no `ProcessDetails` dizia que a
 * edição tinha sido "movida para um Dialog accionado pelo botão +" e
 * esse Dialog nunca chegou a ser construído — o PACOTE DD removeu o
 * cartão e o substituto ficou por fazer. Hoje só se põem etiquetas pela
 * API.
 *
 * PORQUE É QUE A COR DERIVA DO TEXTO
 *   Guardar a cor obrigaria a uma segunda colecção (definições de
 *   etiqueta) ou a mudar `labels` para objectos, migrando os dados e
 *   todas as projecções. Derivá-la do texto dá a mesma garantia com
 *   nada para manter: "VIP" é da mesma cor em todos os ecrãs porque é a
 *   mesma palavra, não porque alguém a configurou igual.
 *
 * A NORMALIZAÇÃO ESPELHA A DO BACKEND (`services/process_labels.py`).
 * Divergirem daria um editor que aceita o que a API recusa.
 */
import { describe, expect, it } from "vitest";

import {
  MAX_ETIQUETAS,
  corDaEtiqueta,
  normalizarEtiquetas,
  podeAcrescentar,
} from "./processLabels";

describe("normalizarEtiquetas", () => {
  it("apara e descarta vazios", () => {
    expect(normalizarEtiquetas(["  VIP  ", "", "   ", null])).toEqual(["VIP"]);
  });

  it("remove duplicados sem olhar à capitalização", () => {
    expect(normalizarEtiquetas(["VIP", "vip", " Vip "])).toEqual(["VIP"]);
  });

  it("preserva a forma da primeira ocorrência", () => {
    // Quem escreve "Sub 35" não quer ver "sub 35" no crachá.
    expect(normalizarEtiquetas(["Sub 35", "SUB 35"])).toEqual(["Sub 35"]);
  });

  it("aceita uma string separada por vírgulas", () => {
    expect(normalizarEtiquetas("VIP, Sub 35 ,Urgente")).toEqual(["VIP", "Sub 35", "Urgente"]);
  });

  it("limita o número de etiquetas", () => {
    const muitas = Array.from({ length: MAX_ETIQUETAS + 10 }, (_, i) => `e${i}`);
    expect(normalizarEtiquetas(muitas)).toHaveLength(MAX_ETIQUETAS);
  });

  it("uma lista vazia continua a ser lista vazia", () => {
    // Limpar as etiquetas tem de ser possível — o
    // `sanitizeProcessUpdatePayload` já permite `labels: []` de propósito.
    expect(normalizarEtiquetas([])).toEqual([]);
  });

  it("nada não rebenta", () => {
    expect(normalizarEtiquetas()).toEqual([]);
    expect(normalizarEtiquetas(null)).toEqual([]);
    expect(normalizarEtiquetas(42)).toEqual([]);
  });
});

describe("corDaEtiqueta", () => {
  it("a mesma etiqueta dá sempre a mesma cor", () => {
    expect(corDaEtiqueta("VIP")).toBe(corDaEtiqueta("VIP"));
  });

  it("não olha à capitalização nem a espaços", () => {
    // Senão "VIP" e " vip " — que são a MESMA etiqueta depois de
    // normalizadas — apareciam de cores diferentes.
    expect(corDaEtiqueta("VIP")).toBe(corDaEtiqueta("  vip "));
  });

  it("etiquetas diferentes tendem a dar cores diferentes", () => {
    const cores = new Set(["VIP", "Sub 35", "Urgente", "Renegociação"].map(corDaEtiqueta));
    expect(cores.size).toBeGreaterThan(1);
  });

  it("devolve sempre uma classe utilizável, mesmo para o vazio", () => {
    expect(typeof corDaEtiqueta("")).toBe("string");
    expect(corDaEtiqueta("").length).toBeGreaterThan(0);
    expect(typeof corDaEtiqueta()).toBe("string");
  });

  it("usa tokens semânticos, não cores Tailwind cruas", () => {
    // Regra ESLint do PACOTE 11 (dark mode): nada de `bg-blue-500`.
    for (const nome of ["VIP", "Sub 35", "Urgente", "X", "outra"]) {
      expect(corDaEtiqueta(nome)).not.toMatch(/\b(bg|text|border)-(gray|blue|red|green|yellow|purple|pink|indigo)-\d{3}\b/);
    }
  });
});

describe("podeAcrescentar", () => {
  it("recusa uma etiqueta que já lá está", () => {
    expect(podeAcrescentar(["VIP"], "vip").ok).toBe(false);
  });

  it("recusa texto vazio", () => {
    expect(podeAcrescentar([], "   ").ok).toBe(false);
  });

  it("recusa quando o limite está atingido", () => {
    const cheias = Array.from({ length: MAX_ETIQUETAS }, (_, i) => `e${i}`);
    expect(podeAcrescentar(cheias, "nova").ok).toBe(false);
  });

  it("dá um motivo legível quando recusa", () => {
    // Um botão que não faz nada e não diz porquê é o silêncio do Bug 1
    // outra vez, noutro sítio.
    for (const caso of [[["VIP"], "VIP"], [[], "  "]]) {
      const r = podeAcrescentar(caso[0], caso[1]);
      expect(r.ok).toBe(false);
      expect(typeof r.motivo).toBe("string");
      expect(r.motivo.length).toBeGreaterThan(0);
    }
  });

  it("aceita uma etiqueta nova", () => {
    expect(podeAcrescentar(["VIP"], "Sub 35")).toEqual({ ok: true, etiqueta: "Sub 35" });
  });

  it("devolve a etiqueta já normalizada", () => {
    expect(podeAcrescentar([], "  Sub 35  ").etiqueta).toBe("Sub 35");
  });
});
