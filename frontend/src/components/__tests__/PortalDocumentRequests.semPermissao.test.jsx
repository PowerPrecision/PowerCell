/**
 * Pedidos de documentos do Portal num processo que o utilizador não pode ler (por indexar e não
 * atribuído a ele): o servidor responde 403 POR DESENHO, por isso o ecrã nem deve fazer o pedido
 * (deixava um erro vermelho na consola e um aviso por uma negação esperada). O hook é o REAL.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getPortalDocRequests: vi.fn(),
  createPortalDocRequest: vi.fn(),
  updatePortalDocRequest: vi.fn(),
  deletePortalDocRequest: vi.fn(),
}));
vi.mock("../../services/api", async (importOriginal) => ({ ...(await importOriginal()), ...api }));

import PortalDocumentRequests from "../PortalDocumentRequests";

function montar(props = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PortalDocumentRequests processId="proc-9" processNumber="P-9" clientName="Rui" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getPortalDocRequests.mockResolvedValue({
    data: { documents: [{ id: "d1", category: "IRS", status: "REQUESTED", label: "IRS" }] },
  });
});

describe("PortalDocumentRequests — permissão do servidor", () => {
  it("podeVerDocumentos=false: NÃO faz o pedido e diz porquê (não finge «sem pedidos»)", async () => {
    montar({ podeVerDocumentos: false });
    expect(await screen.findByTestId("pedidos-do-portal-indisponiveis")).toHaveTextContent(/indexado|atribuído/i);
    expect(api.getPortalDocRequests).not.toHaveBeenCalled();
  });

  it.each([[true], [undefined]])("podeVerDocumentos=%s: pede os pedidos como antes", async (valor) => {
    montar({ podeVerDocumentos: valor });
    await waitFor(() => expect(api.getPortalDocRequests).toHaveBeenCalledWith("proc-9"));
    expect(screen.queryByTestId("pedidos-do-portal-indisponiveis")).not.toBeInTheDocument();
  });
});
