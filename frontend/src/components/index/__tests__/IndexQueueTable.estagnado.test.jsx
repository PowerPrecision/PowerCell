/** O selo «Sem actividade» na fila de supervisão do Index (Out 2026): o SLA avisou que o trabalho começado estagnou. */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IndexQueueTable } from "../IndexQueueTable";

const linha = (id, extra = {}) => ({
  id, client_name: `Cliente ${id}`, process_number: 100, index_status: "in_review", documents_total: 2,
  index_alerts_open: 0, created_at: "2026-10-01T10:00:00Z", ...extra,
});

describe("IndexQueueTable — estagnação", () => {
  it("só o processo marcado como estagnado leva o selo", () => {
    render(<IndexQueueTable itens={[linha("a", { stagnant: true }), linha("b")]} separador="pending" onAbrir={vi.fn()} />);
    const [a, b] = screen.getAllByTestId("index-queue-row");
    expect(within(a).getByTestId("fila-estagnado")).toHaveTextContent("Sem actividade");
    expect(within(b).queryByTestId("fila-estagnado")).not.toBeInTheDocument();
  });

  it("`stagnant` tem de ser true estrito (um texto não conta)", () => {
    render(<IndexQueueTable itens={[linha("a", { stagnant: "true" })]} separador="pending" onAbrir={vi.fn()} />);
    expect(screen.queryByTestId("fila-estagnado")).not.toBeInTheDocument();
  });
});
