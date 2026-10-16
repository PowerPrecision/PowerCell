import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../services/api", () => ({
  getProcessAlerts: vi.fn(),
}));

import { getProcessAlerts } from "../../services/api";
import ProcessAlerts from "../ProcessAlerts";
import { invalidateProcessDetailsQueries, queryKeys } from "../../lib/queryClient";

const comAlerta = {
  data: {
    alerts: [{ type: "document_expiry", priority: "high", message: "CC expira em 3 dias", days_remaining: 3 }],
    has_critical: false,
    has_high: true,
  },
};
const semAlertas = { data: { alerts: [], has_critical: false, has_high: false } };

function montar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ProcessAlerts processId="p-1" />
    </QueryClientProvider>,
  );
  return qc;
}

describe("ProcessAlerts — a cache acompanha o estado do processo", () => {
  beforeEach(() => vi.clearAllMocks());

  it("o alerta desaparece quando o processo é invalidado e a causa já não existe", async () => {
    getProcessAlerts.mockResolvedValueOnce(comAlerta).mockResolvedValue(semAlertas);
    const qc = montar();
    expect(await screen.findByText("CC expira em 3 dias")).toBeInTheDocument();

    // É o que qualquer gravação do processo faz.
    await act(async () => {
      await invalidateProcessDetailsQueries(qc, "p-1");
    });

    await waitFor(() => expect(screen.queryByText("CC expira em 3 dias")).not.toBeInTheDocument());
    expect(await screen.findByText(/sem alertas ativos/i)).toBeInTheDocument();
  });

  it("a chave dos alertas desce do prefixo do detalhe (contraprova da ligação)", () => {
    const chave = queryKeys.processes.alerts("p-1");
    expect(chave.slice(0, queryKeys.processes.detail("p-1").length)).toEqual(queryKeys.processes.detail("p-1"));
  });

  it("falha sem nada em cache NÃO diz «sem alertas»", async () => {
    getProcessAlerts.mockRejectedValue(new Error("rede"));
    montar();
    expect(await screen.findByTestId("process-alerts-erro")).toBeInTheDocument();
    expect(screen.queryByText(/sem alertas ativos/i)).not.toBeInTheDocument();
  });

  it("uma falha ao refrescar mantém o que já se sabia", async () => {
    getProcessAlerts.mockResolvedValueOnce(comAlerta).mockRejectedValue(new Error("rede"));
    const qc = montar();
    expect(await screen.findByText("CC expira em 3 dias")).toBeInTheDocument();
    await act(async () => {
      await invalidateProcessDetailsQueries(qc, "p-1");
    });
    expect(screen.getByText("CC expira em 3 dias")).toBeInTheDocument();
  });
});
