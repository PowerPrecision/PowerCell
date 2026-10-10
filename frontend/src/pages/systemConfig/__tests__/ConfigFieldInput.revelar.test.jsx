/**
 * «Mostrar valor actual» pede os segredos da empresa que está em ecrã.
 *
 * Antes o `reveal-secrets` não tinha `company_id`: o formulário mostrava os
 * campos de uma empresa e o olho revelava as chaves da configuração GLOBAL.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigFieldInput } from "../configFormHelpers";

const CAMPO = { key: "aws_secret_access_key", label: "Chave secreta", type: "password" };

describe("ConfigFieldInput — revelar um segredo", () => {
  let pedidos;

  beforeEach(() => {
    pedidos = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        pedidos.push(String(url));
        return { ok: true, json: async () => ({ secrets: { aws_secret_access_key: "SEGREDO-REAL" } }) };
      }),
    );
  });

  const montar = (companyId) =>
    render(
      <ConfigFieldInput
        field={CAMPO}
        value="••••••••"
        onChange={() => {}}
        allValues={{}}
        sectionName="storage"
        companyId={companyId}
      />,
    );

  it("leva o company_id da empresa em ecrã", async () => {
    montar("cmp-domus");
    fireEvent.click(screen.getByTitle("Mostrar valor actual"));

    await waitFor(() => expect(pedidos.length).toBe(1));
    expect(pedidos[0]).toContain("section=storage");
    expect(pedidos[0]).toContain("company_id=cmp-domus");
  });

  it("sem empresa, pede a global (o comportamento de sempre)", async () => {
    montar(undefined);
    fireEvent.click(screen.getByTitle("Mostrar valor actual"));

    await waitFor(() => expect(pedidos.length).toBe(1));
    expect(pedidos[0]).toContain("company_id=default");
  });
});
