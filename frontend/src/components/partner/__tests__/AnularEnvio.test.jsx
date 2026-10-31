/**
 * Portal do Parceiro — anular um envio (Out 2026).
 *
 * O botão só existe no que o próprio parceiro enviou; pede confirmação; anula pelo `id` do ficheiro (nunca
 * uma chave S3) e mostra o motivo do servidor quando já não dá para anular.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ anularEnvio: vi.fn(), obterUrlDeDescarga: vi.fn() }));
vi.mock("@/services/partnerApi", () => api);
const { anularEnvio } = api;

import FicheiroDoCaso from "../FicheiroDoCaso";

const ficheiro = (extra) => ({
  id: "f-errado", filename: "recibo-errado.pdf", by: "eu", estado: "recebido",
  uploaded_at: "2026-10-30T10:00:00+00:00", ...extra,
});

function montar(f) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidar = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <ul><FicheiroDoCaso caseId="caso-7" ficheiro={f} /></ul>
    </QueryClientProvider>,
  );
  return { invalidar };
}

beforeEach(() => anularEnvio.mockReset());

describe("Anular envio", () => {
  it("só aparece no que o próprio parceiro enviou", () => {
    montar(ficheiro({ by: "cliente" }));
    expect(screen.queryByTestId("anular-envio")).not.toBeInTheDocument();
  });

  it("pede confirmação e anula pelo id do ficheiro, actualizando o caso", async () => {
    anularEnvio.mockResolvedValue({ success: true, id: "f-errado" });
    const { invalidar } = montar(ficheiro());
    await userEvent.click(screen.getByRole("button", { name: /anular envio de recibo-errado\.pdf/i }));
    expect(anularEnvio).not.toHaveBeenCalled();
    expect(await screen.findByText(/anular o envio deste ficheiro/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^anular envio$/i }));
    expect(anularEnvio).toHaveBeenCalledWith("caso-7", "f-errado");
    await vi.waitFor(() =>
      expect(invalidar).toHaveBeenCalledWith({ queryKey: ["partner", "caso", "caso-7"] }),
    );
  });

  it("«Manter» não anula", async () => {
    montar(ficheiro());
    await userEvent.click(screen.getByTestId("anular-envio"));
    await userEvent.click(await screen.findByRole("button", { name: /manter/i }));
    expect(anularEnvio).not.toHaveBeenCalled();
  });

  it("mostra o motivo do servidor quando já não dá para anular", async () => {
    // Uma função simples e não o `vi.fn` rejeitado: o espião do Vitest 3.2 regista a rejeição como erro
    // do teste mesmo depois de o componente a ter tratado.
    const espiao = api.anularEnvio;
    api.anularEnvio = async () => {
      throw { response: { status: 409, data: { detail: "A equipa já tratou este documento e já não pode ser anulado." } } };
    };
    try {
      montar(ficheiro());
      await userEvent.click(screen.getByTestId("anular-envio"));
      await userEvent.click(await screen.findByRole("button", { name: /^anular envio$/i }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/a equipa já tratou este documento/i);
    } finally {
      api.anularEnvio = espiao;
    }
  });
});
