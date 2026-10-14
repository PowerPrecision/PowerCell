/** Gestão de parceiros (staff) — regras puras, sobre a forma REAL do servidor. */
import { describe, expect, it } from "vitest";

import conviteCriado from "@/test/fixtures/parceiro/convite_criado.json";
import parceiros from "@/test/fixtures/parceiro/parceiros.json";
import {
  corpoDoConvite,
  estadoDoParceiro,
  linkDoConvite,
  nomesDasEmpresas,
  normalizarParceiros,
  podeSuspender,
  validarConvite,
} from "./partnersAdmin";

const redes = (...estados) => estados.map((status, i) => ({ network_id: `r${i}`, company_name: `E${i}`, status }));

describe("normalizarParceiros", () => {
  it("lê a forma real", () => {
    const lista = normalizarParceiros(parceiros);
    expect(lista.map((p) => p.id)).toEqual(["pt-1", "parceiro-novo", "pt-2"]);
    expect(lista[1].redes[0].company_name).toBe("Power Real Estate");
  });

  it("lixo e listas que não são listas dão []", () => {
    for (const lixo of [null, undefined, "x", {}, { partners: {} }, { partners: "a" }]) {
      expect(normalizarParceiros(lixo)).toEqual([]);
    }
  });

  it("descarta entradas sem id e normaliza `redes` (objecto não é lista)", () => {
    const lista = normalizarParceiros({ partners: [null, { name: "sem id" }, { id: "a", redes: { x: 1 } }] });
    expect(lista).toEqual([{ id: "a", redes: [] }]);
  });
});

describe("estadoDoParceiro", () => {
  it("convidado, activo, parcial e suspenso", () => {
    expect(estadoDoParceiro({ status: "invited", redes: redes("active") }).chave).toBe("convidado");
    expect(estadoDoParceiro({ status: "active", redes: redes("active", "active") }).chave).toBe("activo");
    expect(estadoDoParceiro({ status: "active", redes: redes("active", "suspended") }).chave).toBe("parcial");
    expect(estadoDoParceiro({ status: "active", redes: redes("suspended") }).chave).toBe("suspenso");
  });

  it("uma ligação sem estado conta como activa (o servidor omite-o por omissão)", () => {
    expect(estadoDoParceiro({ status: "active", redes: [{ network_id: "r" }] }).chave).toBe("activo");
  });

  it("sem ligações (agente independente) está activo — e suspenso quando a CONTA o está", () => {
    expect(estadoDoParceiro({ status: "active", redes: [] }).chave).toBe("activo");
    expect(estadoDoParceiro({ status: "suspended", redes: [] }).chave).toBe("suspenso");
  });

  it("o botão diz «Suspender» quando há algo activo: uma ligação, ou a conta de um independente", () => {
    expect(podeSuspender({ redes: redes("active", "suspended") })).toBe(true);
    expect(podeSuspender({ redes: redes("suspended") })).toBe(false);
    expect(podeSuspender({ status: "active", redes: [] })).toBe(true);
    expect(podeSuspender({ status: "suspended", redes: [] })).toBe(false);
    expect(podeSuspender(null)).toBe(false);
  });
});

describe("empresas e link do convite", () => {
  it("nomes das empresas (cai no id da rede quando falta o nome)", () => {
    expect(nomesDasEmpresas({ redes: [{ company_name: "A" }, { network_id: "rede_x" }, {}] })).toBe("A, rede_x");
  });

  it("sem ligações diz «Independente» e não uma célula vazia", () => {
    expect(nomesDasEmpresas({ redes: [] })).toBe("Independente");
  });

  it("o link junta a origem ao caminho do servidor (sem barras duplas)", () => {
    expect(linkDoConvite(conviteCriado.invite_path, "https://app.x.pt/")).toBe("https://app.x.pt/parceiro/convite/TOKEN-DO-CONVITE");
    expect(linkDoConvite("parceiro/convite/t", "https://app.x.pt")).toBe("https://app.x.pt/parceiro/convite/t");
  });
});

describe("o convite", () => {
  it("valida nome e email — a empresa é OPCIONAL (Lote 5)", () => {
    expect(Object.keys(validarConvite({}))).toEqual(["name", "email"]);
    expect(validarConvite({ name: "Rui", email: "rui@p.pt" })).toEqual({});
    expect(validarConvite({ name: "Rui", email: "rui@p.pt", company_id: "cmp" })).toEqual({});
    expect(validarConvite({ name: "Rui", email: "rui@p", company_id: "cmp" }).email).toBeTruthy();
  });

  it("sem empresa o corpo NÃO leva `company_id` (o servidor não recebe uma string vazia)", () => {
    expect(corpoDoConvite({ name: "Rui", email: "r@p.pt", company_id: "  " })).toEqual({ name: "Rui", email: "r@p.pt" });
  });

  it("o corpo leva SÓ o que o servidor aceita (extra=forbid), sem opcionais vazios", () => {
    expect(corpoDoConvite({ name: " Rui ", email: " r@p.pt ", company_id: "cmp", phone: "  ", rede: "x" })).toEqual({
      name: "Rui", email: "r@p.pt", company_id: "cmp",
    });
    expect(corpoDoConvite({ name: "R", email: "r@p.pt", company_id: "c", phone: " 912 " }).phone).toBe("912");
  });
});
