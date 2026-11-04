/**
 * «Reabrir» um processo indexado (Nov 2026): o botão só aparece num processo indexado por uma pessoa;
 * o motivo é opcional e vai no pedido; a mensagem do servidor diz para onde o processo foi.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({ reabrirIndexProcess: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { toast } from "sonner";
import { reabrirIndexProcess } from "../../../services/api";
import { useIndexMutations } from "../../../hooks/mutations/useIndexMutations";
import { ReabrirProcesso } from "../ReabrirProcesso";

function ComMutacao({ processo, daEquipa = true }) {
  const m = useIndexMutations("proc-1");
  return <ReabrirProcesso processo={processo} daEquipa={daEquipa} reabrir={m.reabrir} />;
}

function montar(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ReabrirProcesso", () => {
  beforeEach(() => vi.clearAllMocks());

  it("não aparece num processo por indexar nem num dispensado", () => {
    const { rerender } = montar(<ComMutacao processo={{ index_status: "in_review" }} />);
    expect(screen.queryByTestId("botao-reabrir-processo")).toBeNull();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ComMutacao processo={{ index_status: "indexed", index_skipped: true }} />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("botao-reabrir-processo")).toBeNull();
  });

  it("reabre com o motivo e mostra a mensagem do servidor", async () => {
    reabrirIndexProcess.mockResolvedValue({ data: { message: "Processo reaberto: está atribuído a si e pronto a tratar." } });
    montar(<ComMutacao processo={{ index_status: "indexed", index_skipped: false }} />);
    await userEvent.click(screen.getByTestId("botao-reabrir-processo"));
    expect(await screen.findByText(/atribuído a si, em tratamento/i)).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("motivo-reabrir"), "recibos de out e nov");
    await userEvent.click(screen.getByTestId("confirmar-reabrir"));
    expect(reabrirIndexProcess).toHaveBeenCalledWith("proc-1", "recibos de out e nov");
    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Processo reaberto: está atribuído a si e pronto a tratar."),
    );
  });

  it("para a gestão diz que volta à fila", async () => {
    montar(<ComMutacao processo={{ index_status: "indexed" }} daEquipa={false} />);
    await userEvent.click(screen.getByTestId("botao-reabrir-processo"));
    expect(await screen.findByText(/volta à fila do Index/i)).toBeInTheDocument();
  });
});
