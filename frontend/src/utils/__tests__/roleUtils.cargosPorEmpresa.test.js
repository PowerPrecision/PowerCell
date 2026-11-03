import { describe, expect, it } from "vitest";
import {
  filterByAnyRole,
  filterByRole,
  INDEXACAO_ASSIGNMENT_ROLES,
} from "../roleUtils";

// Gestão de Atribuições (Nov 2026): o Index dado POR EMPRESA (UCR) chega em `company_roles`;
// só o `role` escondia-o do Select do Index, mesmo com o Master.
const iris = { id: "u-iris", role: "consultor", company_roles: ["consultor", "indexacao"] };
const legado = { id: "u-legado", role: "index" };
const ana = { id: "u-ana", role: "diretor", additional_roles: [] };

describe("cargos por empresa nas listas de atribuição", () => {
  it("quem tem o Index só no UCR entra no Select do Index", () => {
    const ids = filterByAnyRole([iris, ana], INDEXACAO_ASSIGNMENT_ROLES).map((u) => u.id);
    expect(ids).toEqual(["u-iris"]);
  });

  it("o alias legado «index» também é Index", () => {
    expect(filterByAnyRole([legado], INDEXACAO_ASSIGNMENT_ROLES)).toHaveLength(1);
  });

  it("filterByRole e a forma de um só utilizador leem o mesmo", () => {
    expect(filterByRole([iris, ana], "indexacao")).toEqual([iris]);
    expect(filterByAnyRole(iris, ["indexacao"])).toBe(true);
    expect(filterByAnyRole(ana, ["indexacao"])).toBe(false);
  });
});
