/**
 * O cliente da API NÃO deixa sair uma acção destrutiva sem a password actual.
 *
 * O servidor também a exige (é a parede), mas o cliente é a segunda: um ecrã novo que se
 * esqueça do diálogo falha aqui, no teste, e não em produção com um 400 que ninguém vê.
 * Estas três acções não têm (todas) um botão no ecrã hoje — o cliente da API é o único
 * sítio que garante que quem as ligar amanhã passa pelo diálogo.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { put, post, del } = vi.hoisted(() => ({ put: vi.fn(), post: vi.fn(), del: vi.fn() }));

vi.mock("axios", () => {
  const instancia = {
    get: vi.fn(), post, put, delete: del, patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { headers: { common: {} } },
  };
  return { default: { create: () => instancia, ...instancia, isCancel: () => false }, create: () => instancia };
});

import { deleteCompany, runGdprBatch, updateCompany } from "./api";

describe("deleteCompany", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([undefined, null, ""])("sem password (%s) nem sai o pedido", async (password) => {
    await expect(deleteCompany("c1", password)).rejects.toThrow(/password/i);
    expect(del).not.toHaveBeenCalled();
  });

  it("com password: DELETE com a password no CORPO e skipErrorToast", async () => {
    del.mockResolvedValue({ data: {} });
    await deleteCompany("c1", "Segredo-1!");
    expect(del).toHaveBeenCalledWith("/admin/companies/c1", { data: { password: "Segredo-1!" }, skipErrorToast: true });
  });
});

describe("runGdprBatch", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fora do ensaio, sem password, nem sai o pedido", async () => {
    await expect(runGdprBatch({ dry_run: false, batch_size: 10 })).rejects.toThrow(/password/i);
    expect(post).not.toHaveBeenCalled();
  });

  it("fora do ensaio, com password: sai, com skipErrorToast", async () => {
    post.mockResolvedValue({ data: {} });
    await runGdprBatch({ dry_run: false, password: "Segredo-1!" });
    expect(post).toHaveBeenCalledWith("/gdpr/batch", { dry_run: false, password: "Segredo-1!" }, { skipErrorToast: true });
  });

  it("o ensaio não pede password", async () => {
    post.mockResolvedValue({ data: {} });
    await runGdprBatch({ dry_run: true });
    await runGdprBatch({});
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[0][1]).toEqual({ dry_run: true });
  });
});

describe("updateCompany", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sem password é o PUT de sempre (nada de confirm_password)", async () => {
    put.mockResolvedValue({ data: {} });
    await updateCompany("c1", { name: "X" });
    expect(put).toHaveBeenCalledWith("/admin/companies/c1", { name: "X" });
  });

  it("com password junta confirm_password ao corpo e pede skipErrorToast", async () => {
    put.mockResolvedValue({ data: {} });
    await updateCompany("c1", { name: "X", network_id: "nova" }, { password: "Segredo-1!" });
    expect(put).toHaveBeenCalledWith(
      "/admin/companies/c1",
      { name: "X", network_id: "nova", confirm_password: "Segredo-1!" },
      { skipErrorToast: true },
    );
  });

  it("não muta o payload recebido", async () => {
    put.mockResolvedValue({ data: {} });
    const payload = { network_id: "nova" };
    await updateCompany("c1", payload, { password: "p" });
    expect(payload).toEqual({ network_id: "nova" });
  });
});
