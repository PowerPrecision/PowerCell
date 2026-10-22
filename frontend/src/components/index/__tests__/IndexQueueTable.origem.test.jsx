/**
 * A coluna «Empresa/Origem» da fila do Index (Out 2026).
 *
 * Quem trata a fila precisa de saber de que empresa é cada processo — e se lhe foi PARTILHADO por
 * outra rede. A forma é a REAL do `GET /api/index/queue` (`company: {name, other_network}`).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IndexQueueTable } from "../IndexQueueTable";

const linha = (id, extra = {}) => ({
  id, client_name: `Cliente ${id}`, process_number: 100, index_status: "pending", documents_total: 2,
  index_alerts_open: 0, created_at: "2026-10-01T10:00:00Z", ...extra,
});

function origemDe(testid) {
  const linhas = screen.getAllByTestId("index-queue-row");
  return within(linhas.find((l) => l.textContent.includes(testid))).getByTestId("index-queue-origem");
}

describe("IndexQueueTable — Empresa/Origem", () => {
  it("o cabeçalho tem a coluna", () => {
    render(<IndexQueueTable itens={[linha("a")]} separador="pending" onAbrir={vi.fn()} />);
    expect(screen.getByRole("columnheader", { name: "Empresa/Origem" })).toBeInTheDocument();
  });

  it("mostra o nome da empresa do processo", () => {
    render(
      <IndexQueueTable
        itens={[linha("a", { company: { name: "Power Real Estate", other_network: false } })]}
        separador="pending"
        onAbrir={vi.fn()}
      />,
    );
    expect(origemDe("Cliente a")).toHaveTextContent("Power Real Estate");
    expect(within(origemDe("Cliente a")).queryByText("Partilhado")).not.toBeInTheDocument();
  });

  it("um processo partilhado por outra rede di-lo", () => {
    render(
      <IndexQueueTable
        itens={[linha("b", { company: { name: "Domus", other_network: true } })]}
        separador="pending"
        onAbrir={vi.fn()}
      />,
    );
    expect(origemDe("Cliente b")).toHaveTextContent("Domus");
    expect(within(origemDe("Cliente b")).getByText("Partilhado")).toBeInTheDocument();
  });

  it.each([
    ["company a null", { company: null }],
    ["company em falta (servidor antigo)", {}],
    ["company sem nome", { company: { name: "", other_network: false } }],
  ])("sem empresa determinável (%s) mostra «—» e nunca inventa uma", (_t, extra) => {
    render(<IndexQueueTable itens={[linha("c", extra)]} separador="pending" onAbrir={vi.fn()} />);
    expect(origemDe("Cliente c")).toHaveTextContent("—");
    expect(within(origemDe("Cliente c")).queryByText("Partilhado")).not.toBeInTheDocument();
  });

  it("«Partilhado» só com `other_network === true` estrito (texto «false» não conta)", () => {
    render(
      <IndexQueueTable
        itens={[linha("d", { company: { name: "X", other_network: "false" } })]}
        separador="pending"
        onAbrir={vi.fn()}
      />,
    );
    expect(within(origemDe("Cliente d")).queryByText("Partilhado")).not.toBeInTheDocument();
  });

  it("cada linha tem a SUA empresa", () => {
    render(
      <IndexQueueTable
        itens={[
          linha("e", { company: { name: "Empresa E", other_network: false } }),
          linha("f", { company: { name: "Empresa F", other_network: true } }),
        ]}
        separador="reviews"
        onAbrir={vi.fn()}
      />,
    );
    expect(origemDe("Cliente e")).toHaveTextContent("Empresa E");
    expect(origemDe("Cliente f")).toHaveTextContent("Empresa F");
  });
});
