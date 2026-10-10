/**
 * O perfil que o ecrã mostra (Bloco 4, ponto 33).
 *
 * Em impersonate o ambiente tem de espelhar exactamente — e apenas — o que
 * o utilizador-alvo vê. O `activeRole` é estado do navegador e pode ser o
 * do administrador; a função não o deixa vencer a não ser que seja um
 * perfil do ALVO.
 */
import { describe, expect, it } from "vitest";

import { papelEfectivoDaSessao } from "./papelEfectivo";

const consultor = { id: "u2", role: "consultor", additional_roles: [] };
const consultorComDiretor = {
  id: "u3",
  role: "consultor",
  additional_roles: ["diretor"],
  companies: [{ company_id: "c1", company_name: "Power", role: "consultor" }],
};

describe("sessão normal", () => {
  it("o perfil activo vence o cargo base", () => {
    expect(papelEfectivoDaSessao({ user: consultor, activeRole: "diretor" })).toBe("diretor");
  });

  it("sem perfil activo vale o cargo base", () => {
    expect(papelEfectivoDaSessao({ user: consultor, activeRole: null })).toBe("consultor");
  });

  it("sem sessão devolve undefined", () => {
    expect(papelEfectivoDaSessao({})).toBeUndefined();
    expect(papelEfectivoDaSessao()).toBeUndefined();
  });
});

describe("impersonate", () => {
  it.each(["admin", "ceo"])(
    "um perfil %s que ficou do administrador NÃO vence o cargo do alvo",
    (residual) => {
      expect(
        papelEfectivoDaSessao({ isImpersonating: true, user: consultor, activeRole: residual }),
      ).toBe("consultor");
    },
  );

  it("o alvo com vários perfis pode usar qualquer um dos SEUS", () => {
    expect(
      papelEfectivoDaSessao({
        isImpersonating: true, user: consultorComDiretor, activeRole: "diretor",
      }),
    ).toBe("diretor");
  });

  it("mas não um que o alvo não tenha, mesmo que o utilizador-alvo tenha outros", () => {
    expect(
      papelEfectivoDaSessao({
        isImpersonating: true, user: consultorComDiretor, activeRole: "admin",
      }),
    ).toBe("consultor");
  });

  it("sem perfil activo vale o cargo do alvo", () => {
    expect(
      papelEfectivoDaSessao({ isImpersonating: true, user: consultor, activeRole: null }),
    ).toBe("consultor");
  });

  it("um alvo que é CEO vê o que o CEO vê (espelha, não esconde)", () => {
    expect(
      papelEfectivoDaSessao({
        isImpersonating: true, user: { role: "ceo" }, activeRole: "ceo",
      }),
    ).toBe("ceo");
  });

  it("contraprova: fora de impersonate o mesmo `activeRole` vence", () => {
    // Garante que a regra restritiva só vale em impersonate: um teste que
    // passasse com a regra aplicada sempre apagava o ContextSwitcher.
    expect(
      papelEfectivoDaSessao({ isImpersonating: false, user: consultor, activeRole: "admin" }),
    ).toBe("admin");
  });
});
