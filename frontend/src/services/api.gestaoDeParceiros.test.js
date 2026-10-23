/**
 * Gestão de parceiros pelo cliente Axios: o caminho certo, o corpo certo, o erro dito no sítio
 * (`skipErrorToast`) e — para eliminar — a recusa de sair o pedido sem a password actual.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import api, { changePartnerCompany, deletePartner, resetPartnerPassword, updatePartner } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("api.js — gestão de parceiros", () => {
  it("mudar de empresa: POST com o company_id", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    await changePartnerCompany("p1", "cmp-1");
    expect(post).toHaveBeenCalledWith("/admin/partners/p1/change-company", { company_id: "cmp-1" }, { skipErrorToast: true });
  });

  it("nova password: POST sem corpo", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    await resetPartnerPassword("p1");
    expect(post).toHaveBeenCalledWith("/admin/partners/p1/reset-password", null, { skipErrorToast: true });
  });

  it("editar: PATCH com skipErrorToast (o erro diz-se no diálogo)", async () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue({ data: {} });
    await updatePartner("p1", { name: "X" });
    expect(patch).toHaveBeenCalledWith("/admin/partners/p1", { name: "X" }, { skipErrorToast: true });
  });

  it("eliminar: DELETE com a password no corpo", async () => {
    const del = vi.spyOn(api, "delete").mockResolvedValue({ data: {} });
    await deletePartner("p1", "Segredo-1!");
    expect(del).toHaveBeenCalledWith("/admin/partners/p1", { data: { password: "Segredo-1!" }, skipErrorToast: true });
  });

  it.each([undefined, null, ""])("eliminar sem password (%s) nem sai o pedido", async (password) => {
    const del = vi.spyOn(api, "delete").mockResolvedValue({ data: {} });
    await expect(deletePartner("p1", password)).rejects.toThrow(/password/i);
    expect(del).not.toHaveBeenCalled();
  });
});
