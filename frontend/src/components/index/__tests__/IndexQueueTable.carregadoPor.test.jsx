/**
 * A coluna «Carregado por» da fila do Index (Out 2026).
 *
 * Quem trata a fila precisa de saber quem carregou cada processo. A forma é a REAL do
 * `GET /api/index/queue` (`loaded_by: {name, tipo}` ou `null`).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IndexQueueTable } from "../IndexQueueTable";

const linha = (id, extra = {}) => ({
  id, client_name: `Cliente ${id}`, process_number: 100, index_status: "pending", documents_total: 2,
  index_alerts_open: 0, created_at: "2026-10-01T10:00:00Z", ...extra,
});

function carregadoPor(nomeDoCliente) {
  const linhas = screen.getAllByTestId("index-queue-row");
  return within(linhas.find((l) => l.textContent.includes(nomeDoCliente))).getByTestId("index-queue-carregado-por");
}

describe("IndexQueueTable — Carregado por", () => {
  it("o cabeçalho tem a coluna", () => {
    render(<IndexQueueTable itens={[linha("a")]} separador="pending" onAbrir={vi.fn()} />);
    expect(screen.getByRole("columnheader", { name: "Carregado por" })).toBeInTheDocument();
  });

  it("cada linha mostra o nome de quem carregou o SEU processo", () => {
    render(
      <IndexQueueTable
        itens={[
          linha("a", { loaded_by: { name: "Rui Intermediário", tipo: "utilizador" } }),
          linha("b", { loaded_by: { name: "Imobiliária Sol", tipo: "parceiro" } }),
        ]}
        separador="pending"
        onAbrir={vi.fn()}
      />,
    );
    expect(carregadoPor("Cliente a")).toHaveTextContent("Rui Intermediário");
    expect(within(carregadoPor("Cliente a")).queryByText("Parceiro")).not.toBeInTheDocument();
    expect(carregadoPor("Cliente b")).toHaveTextContent("Imobiliária Sol");
    expect(within(carregadoPor("Cliente b")).getByText("Parceiro")).toBeInTheDocument();
  });

  it.each([
    ["loaded_by a null", { loaded_by: null }],
    ["loaded_by em falta (servidor antigo)", {}],
    ["loaded_by sem nome", { loaded_by: { name: "", tipo: "utilizador" } }],
  ])("sem autor conhecido (%s) mostra «—»", (_t, extra) => {
    render(<IndexQueueTable itens={[linha("c", extra)]} separador="pending" onAbrir={vi.fn()} />);
    expect(carregadoPor("Cliente c")).toHaveTextContent("—");
  });
});
