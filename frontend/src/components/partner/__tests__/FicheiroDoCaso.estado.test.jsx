/**
 * P3 — cada ficheiro mostra o seu estado. «Recebido» é o de todos; o comprovativo de pagamento
 * segue a validação financeira. Um estado desconhecido cai em «Recebido» (nunca inventa rótulo).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as renderCru, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/services/partnerApi", () => ({ obterUrlDeDescarga: vi.fn() }));

import FicheiroDoCaso, { ROTULO_DO_ESTADO } from "../FicheiroDoCaso";

// O botão «Anular envio» (ficheiros do próprio) usa o cliente do React Query.
const Provider = ({ children }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
const render = (ui) => renderCru(ui, { wrapper: Provider });

const base = { id: "f1", filename: "comprovativo.pdf", by: "eu", uploaded_at: "2026-10-05T10:00:00+00:00" };

function montar(estado) {
  return render(
    <ul>
      <FicheiroDoCaso caseId="c1" ficheiro={{ ...base, ...(estado === undefined ? {} : { estado }) }} />
    </ul>,
  );
}

describe("FicheiroDoCaso — estado", () => {
  it.each([
    ["recebido", "Recebido"],
    ["em_validacao", "Em validação"],
    ["validado", "Validado"],
    ["rejeitado", "Rejeitado"],
  ])("mostra %s como «%s»", (estado, texto) => {
    montar(estado);
    const selo = screen.getByTestId("estado-do-ficheiro");
    expect(selo).toHaveTextContent(texto);
    expect(selo).toHaveAttribute("data-estado", estado);
  });

  it("um servidor antigo (sem estado) ou um estado desconhecido valem «Recebido»", () => {
    montar(undefined);
    expect(screen.getByTestId("estado-do-ficheiro")).toHaveAttribute("data-estado", "recebido");
  });

  it("um estado inventado não vira rótulo", () => {
    montar("aprovadissimo");
    expect(screen.getByTestId("estado-do-ficheiro")).toHaveTextContent("Recebido");
    expect(screen.queryByText(/aprovadissimo/i)).toBeNull();
  });

  it("dentro de um pedido o «Recebido» não se repete, mas o estado próprio do comprovativo sim", () => {
    const { rerender } = render(
      <ul><FicheiroDoCaso caseId="c1" dentroDoPedido ficheiro={{ ...base, estado: "recebido" }} /></ul>,
    );
    expect(screen.queryByTestId("estado-do-ficheiro")).toBeNull();
    rerender(<ul><FicheiroDoCaso caseId="c1" dentroDoPedido ficheiro={{ ...base, estado: "validado" }} /></ul>);
    expect(screen.getByTestId("estado-do-ficheiro")).toHaveTextContent("Validado");
  });

  it("os rótulos são os quatro que o servidor conhece", () => {
    expect(Object.keys(ROTULO_DO_ESTADO).sort()).toEqual(["em_validacao", "recebido", "rejeitado", "validado"]);
  });
});
