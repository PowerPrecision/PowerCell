/**
 * «Rever sugestões» de UM documento (QA-6): painel lateral, e a contagem vem do que se vê.
 *
 * O defeito: a selecção partia de uma lista fixa de quatro campos, por isso um documento SEM
 * sugestões mostrava «A IA não encontrou sugestões» e, por baixo, «Aplicar Selecionadas (4)».
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const aplicar = vi.fn().mockResolvedValue({});
const rejeitar = vi.fn().mockResolvedValue({});
vi.mock("../../services/api", () => ({
  applyAIReview: (...a) => aplicar(...a),
  rejectAIReview: (...a) => rejeitar(...a),
}));

import DocumentReviewModal from "../DocumentReviewModal";

beforeEach(() => vi.clearAllMocks());

const montar = (doc, extra = {}) =>
  render(<DocumentReviewModal open onOpenChange={vi.fn()} doc={doc} onResolved={vi.fn()} {...extra} />);

const SEM_SUGESTOES = { id: "d1", filename: "cc.pdf", category: "Outros" };
const UMA_SUGESTAO = {
  id: "d1", filename: "cc.pdf", category: "Outros", suggested_category: "Identificação",
  suggested_confidence: 0.9,
};

describe("DocumentReviewModal", () => {
  it("abre como painel lateral (uma única janela com o título da revisão)", () => {
    montar(UMA_SUGESTAO);
    const painel = screen.getByRole("dialog");
    expect(painel).toHaveTextContent("Revisão de Sugestões IA");
    expect(painel).toHaveAttribute("data-testid", "revisao-sugestoes-documento");
  });

  it("sem sugestões NÃO oferece aplicar nada — a mensagem e o botão não se contradizem", () => {
    montar(SEM_SUGESTOES);
    expect(screen.getByText(/não encontrou sugestões/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /aplicar selecionadas/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /rejeitar tudo/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /fechar/i }).length).toBeGreaterThan(0);
  });

  it("a contagem do botão é a dos campos que se vêem (1, não 4)", () => {
    montar(UMA_SUGESTAO);
    expect(screen.getByRole("button", { name: /aplicar selecionadas \(1\)/i })).toBeEnabled();
  });

  it("um campo cuja sugestão é igual ao atual não conta nem se oferece", () => {
    montar({ ...UMA_SUGESTAO, suggested_category: "Outros" });
    expect(screen.getByRole("button", { name: /aplicar selecionadas \(0\)/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /selecionado|ignorar/i })).not.toBeInTheDocument();
  });

  it("aplica só os campos com alteração", async () => {
    const u = userEvent.setup();
    montar(UMA_SUGESTAO);
    await u.click(screen.getByRole("button", { name: /aplicar selecionadas/i }));
    await waitFor(() => expect(aplicar).toHaveBeenCalledTimes(1));
    expect(aplicar).toHaveBeenCalledWith("d1", { fields: ["categoria"] });
  });

  it("ignorar o único campo desactiva o botão", async () => {
    const u = userEvent.setup();
    montar(UMA_SUGESTAO);
    await u.click(screen.getByRole("button", { name: /selecionado/i }));
    expect(screen.getByRole("button", { name: /aplicar selecionadas \(0\)/i })).toBeDisabled();
  });
});
