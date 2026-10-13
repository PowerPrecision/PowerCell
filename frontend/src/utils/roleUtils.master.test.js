/**
 * Rotas só-Master: a CONTA Master passa com qualquer chapéu (QA, Out 2026).
 * Espelho do `require_roles` do servidor — ver `canAccessRoute` em roleUtils.js.
 */
import { describe, it, expect } from "vitest";
import { canAccessRoute, eListaSoMaster } from "./roleUtils";

// ── Rotas só-Master: a CONTA Master passa com qualquer chapéu (QA, Out 2026) ──────────────────

describe("eListaSoMaster", () => {
  it.each([[["master"]], [["MASTER"]], [["master", "Master"]]])("%j é só-Master", (lista) => {
    expect(eListaSoMaster(lista)).toBe(true);
  });

  it.each([[[]], [undefined], [null], [["master", "admin"]], [["admin"]], ["master"]])(
    "%j não é",
    (lista) => {
      expect(eListaSoMaster(lista)).toBe(false);
    },
  );
});

describe("canAccessRoute", () => {
  it.each(["admin", "ceo", "consultor", "diretor"])(
    "a CONTA Master com o chapéu de %s passa numa rota só-Master",
    (chapeu) => {
      expect(
        canAccessRoute({ effectiveRole: chapeu, accountRole: "master", allowedRoles: ["master"] }),
      ).toBe(true);
    },
  );

  it("um Admin verdadeiro continua de fora de uma rota só-Master", () => {
    expect(
      canAccessRoute({ effectiveRole: "admin", accountRole: "admin", allowedRoles: ["master"] }),
    ).toBe(false);
  });

  it("um consultor com perfil de admin NÃO herda o Master (a conta decide, não o chapéu)", () => {
    expect(
      canAccessRoute({ effectiveRole: "admin", accountRole: "consultor", allowedRoles: ["master"] }),
    ).toBe(false);
  });

  it("numa rota MISTA sem o perfil activo, a conta Master não ganha por isso (segue o perfil)", () => {
    expect(
      canAccessRoute({
        effectiveRole: "consultor", accountRole: "master", allowedRoles: ["admin", "ceo"],
      }),
    ).toBe(false);
  });

  it("o perfil activo continua a bastar onde já bastava", () => {
    expect(
      canAccessRoute({ effectiveRole: "ceo", accountRole: "ceo", allowedRoles: ["admin", "ceo"] }),
    ).toBe(true);
  });

  it("sem lista de papéis a rota é livre; sem sessão, não", () => {
    expect(canAccessRoute({ effectiveRole: undefined, allowedRoles: undefined })).toBe(true);
    expect(canAccessRoute({ allowedRoles: ["master"] })).toBe(false);
  });
});
