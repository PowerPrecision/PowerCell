/**
 * Portal do Parceiro — a quantidade de um pedido é uma RECOMENDAÇÃO (decisão da direcção, Out 2026).
 * O 1.º ficheiro cumpre o pedido («Recebido») mas o cartão continua a convidar a juntar mais.
 * A forma do pedido é a do servidor (`_dto_do_pedido`) e os valores diferem das omissões.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/services/partnerApi", () => ({ obterUrlDeDescarga: vi.fn(), enviarFicheiro: vi.fn() }));

import PedidoDeDocumento from "../PedidoDeDocumento";

const ficheiro = (n) => ({ id: `f${n}`, filename: `extracto-${n}.pdf`, by: "eu", uploaded_at: "2026-10-05T10:00:00+00:00" });

const pedido = (extra) => ({
  id: "ped-1",
  label: "Extractos bancários",
  notes: "",
  estado: "recebido",
  expected_count: 3,
  uploaded_count: 1,
  ficheiros: [ficheiro(1)],
  ...extra,
});

function montar(p, props = {}) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <PedidoDeDocumento caseId="c1" pedido={p} {...props} />
    </QueryClientProvider>,
  );
}

describe("PedidoDeDocumento — convite a juntar mais", () => {
  it("recebido com 1 de 3: continua «Recebido», convida e oferece «Adicionar mais»", () => {
    montar(pedido());
    expect(screen.getByTestId("pedido-ped-1")).toHaveAttribute("data-estado", "recebido");
    expect(screen.getByTestId("convite-ped-1")).toHaveTextContent("Pode juntar mais — recomendado: 3.");
    expect(screen.getByText("Adicionar mais")).toBeInTheDocument();
  });

  it("pendente sem ficheiros diz que pode enviar menos (não é obrigatório)", () => {
    montar(pedido({ estado: "pendente", uploaded_count: 0, ficheiros: [] }));
    expect(screen.getByTestId("convite-ped-1")).toHaveTextContent("Recomendado: 3 ficheiros — pode enviar menos.");
  });

  it("com a recomendação atingida não convida nem oferece mais", () => {
    montar(pedido({ uploaded_count: 3, ficheiros: [1, 2, 3].map(ficheiro) }));
    expect(screen.queryByTestId("convite-ped-1")).not.toBeInTheDocument();
    expect(screen.queryByText("Adicionar mais")).not.toBeInTheDocument();
  });

  it("um pedido de 1 ficheiro nunca convida", () => {
    montar(pedido({ expected_count: 1 }));
    expect(screen.queryByTestId("convite-ped-1")).not.toBeInTheDocument();
  });

  it("desactivado (lead expirada/associada): o convite não oferece envio", () => {
    montar(pedido(), { desactivado: true });
    expect(screen.queryByText("Adicionar mais")).not.toBeInTheDocument();
  });
});
