/**
 * O hook que grava o cliente deixa passar um contacto APAGADO (QA, Out 2026).
 *
 * O teste da página falseia este hook; aqui monta-se o real e afirma-se o
 * pedido que sai para o servidor (o que o Axios recebe), que é onde o vazio
 * era descartado.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ updateClient: vi.fn(() => Promise.resolve({ data: { ok: true } })) }));

vi.mock("../../../services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  updateClient: api.updateClient,
}));

import { useUpdateClientMutation } from "../useProcessMutations";

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useUpdateClientMutation({ silent: true }), { wrapper });
}

beforeEach(() => api.updateClient.mockClear());

describe("useUpdateClientMutation — contactos apagados", () => {
  it("com clearContactFields o email vazio chega ao servidor como \"\"", async () => {
    const { result } = montar();

    await result.current.mutateAsync({
      clientId: "cli-1",
      data: { contacto: { email: "", telefone: "912345678" } },
      clearContactFields: ["email"],
    });

    await waitFor(() => expect(api.updateClient).toHaveBeenCalledTimes(1));
    expect(api.updateClient).toHaveBeenCalledWith("cli-1", {
      contacto: { email: "", telefone: "912345678" },
    });
  });

  it("sem clearContactFields o vazio continua a ser descartado", async () => {
    const { result } = montar();

    await result.current.mutateAsync({
      clientId: "cli-1",
      data: { contacto: { email: "", telefone: "912345678" } },
    });

    expect(api.updateClient).toHaveBeenCalledWith("cli-1", {
      contacto: { telefone: "912345678" },
    });
  });

  it("apagar o único contacto ainda gera um pedido (não é «nada para gravar»)", async () => {
    const { result } = montar();

    const resposta = await result.current.mutateAsync({
      clientId: "cli-1",
      data: { contacto: { email: "" } },
      clearContactFields: ["email"],
    });

    expect(resposta.skipped).toBeUndefined();
    expect(api.updateClient).toHaveBeenCalledWith("cli-1", { contacto: { email: "" } });
  });
});
