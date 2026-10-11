import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  PAPEIS_QUE_MARCAM_COMO_PAGO,
  aposMarcarComoPago,
  deveOferecerMarcarComoPago,
  temDireitoAMarcarComoPago,
  textoDasComissoes,
} from "./marcarComoPago";

describe("deveOferecerMarcarComoPago", () => {
  it("oferece quando o processo está fechado E há comissões por pagar", () => {
    expect(deveOferecerMarcarComoPago({ processo_fechado: true, comissoes_pendentes: 2 })).toBe(true);
  });

  it("não oferece num processo aberto (aí paga-se pelas Finanças, como sempre)", () => {
    expect(deveOferecerMarcarComoPago({ processo_fechado: false, comissoes_pendentes: 2 })).toBe(false);
  });

  it("não oferece sem comissões pendentes", () => {
    expect(deveOferecerMarcarComoPago({ processo_fechado: true, comissoes_pendentes: 0 })).toBe(false);
  });

  it("para quem o servidor não mandou as chaves, não oferece", () => {
    expect(deveOferecerMarcarComoPago({ id: "p1", status: "concluido" })).toBe(false);
  });

  it("só o booleano estrito conta: «true» em texto não abre o botão", () => {
    expect(deveOferecerMarcarComoPago({ processo_fechado: "true", comissoes_pendentes: 1 })).toBe(false);
  });

  it.each([null, undefined, {}, { processo_fechado: true }, { processo_fechado: true, comissoes_pendentes: "x" }])(
    "sobrevive a %j", (linha) => {
      expect(deveOferecerMarcarComoPago(linha)).toBe(false);
    },
  );
});

describe("textoDasComissoes", () => {
  it("singular e plural", () => {
    expect(textoDasComissoes(1)).toBe("1 comissão");
    expect(textoDasComissoes(3)).toBe("3 comissões");
    expect(textoDasComissoes(undefined)).toBe("0 comissões");
  });
});

describe("aposMarcarComoPago", () => {
  it("desconta o que o servidor pagou e não muta a linha original", () => {
    const linha = { id: "p1", comissoes_pendentes: 2, processo_fechado: true };
    const nova = aposMarcarComoPago(linha, 2);
    expect(nova.comissoes_pendentes).toBe(0);
    expect(linha.comissoes_pendentes).toBe(2);
  });

  it("nunca fica abaixo de zero", () => {
    expect(aposMarcarComoPago({ comissoes_pendentes: 1 }, 5).comissoes_pendentes).toBe(0);
  });
});

describe("quem pode marcar como pago", () => {
  it("é o MESMO conjunto do backend (PAPEIS_QUE_MARCAM_COMO_PAGO)", () => {
    const fonte = fs.readFileSync(
      path.resolve(process.cwd(), "../backend/services/finance_helpers.py"),
      "utf-8",
    );
    const escritores = fonte.match(/FINANCE_WRITE_ROLES\s*=\s*\[([^\]]*)\]/);
    const extra = fonte.match(/PAPEIS_QUE_MARCAM_COMO_PAGO\s*=\s*\[\*FINANCE_WRITE_ROLES,\s*([^\]]*)\]/);
    // Contraprova: um leitor que não leu nada também «passaria» a igualdade vazia.
    expect(escritores).not.toBeNull();
    expect(extra).not.toBeNull();
    const nomes = (texto) => [...texto.matchAll(/UserRole\.([A-Z_]+)/g)].map((m) => m[1].toLowerCase());
    const doBackend = [...nomes(escritores[1]), ...nomes(extra[1])].sort();
    expect(doBackend.length).toBeGreaterThanOrEqual(5);
    expect([...PAPEIS_QUE_MARCAM_COMO_PAGO].sort()).toEqual(doBackend);
  });

  it("o consultor e a indexação não", () => {
    expect(temDireitoAMarcarComoPago("administrativo")).toBe(true);
    expect(temDireitoAMarcarComoPago("Diretor")).toBe(true);
    expect(temDireitoAMarcarComoPago("consultor")).toBe(false);
    expect(temDireitoAMarcarComoPago("indexacao")).toBe(false);
    expect(temDireitoAMarcarComoPago(undefined)).toBe(false);
  });
});
