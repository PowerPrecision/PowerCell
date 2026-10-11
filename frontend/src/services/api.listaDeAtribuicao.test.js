/**
 * A dropdown de atribuição diz ao servidor de que processo se trata
 * (`process_id`): é o que faz a lista do Master acompanhar o alcance do
 * processo em vez de mostrar toda a gente. Mede-se o PARÂMETRO que sai —
 * a resposta é do servidor.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import api, { getStaffUsers, getUsers } from "./api";

afterEach(() => vi.restoreAllMocks());

const espiar = () => vi.spyOn(api, "get").mockResolvedValue({ data: [] });

describe("getUsers / getStaffUsers — process_id", () => {
  it("o staff leva o process_id quando a atribuição é de um processo", async () => {
    const get = espiar();
    await getStaffUsers({ processId: "proc-9" });
    expect(get).toHaveBeenCalledWith("/users/staff", { params: { process_id: "proc-9" } });
  });

  it("sem processo (criação, calendário, tarefas) não há parâmetro nenhum", async () => {
    const get = espiar();
    await getStaffUsers();
    expect(get).toHaveBeenCalledWith("/users/staff", { params: {} });
  });

  it("a lista por perfil também o leva, e mantém os outros filtros", async () => {
    const get = espiar();
    await getUsers("indexacao", { forAssignment: true, processId: "proc-9" });
    expect(get).toHaveBeenCalledWith("/users", {
      params: { role: "indexacao", for_assignment: true, process_id: "proc-9" },
    });
  });

  it("getUsers sem processo continua igual ao que era (contraprova)", async () => {
    const get = espiar();
    await getUsers();
    expect(get).toHaveBeenCalledWith("/users", { params: {} });
  });
});
