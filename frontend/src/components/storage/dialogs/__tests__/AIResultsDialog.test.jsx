/**
 * Teste do diálogo de resultados da análise IA (Épico 8, Eixo 2).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import AIResultsDialog from "../AIResultsDialog";

const resultados = (overrides = {}) => ({
  analysis: {
    documents_analyzed: [
      { file_name: "irs_2025.pdf", tipo_documento: "irs", confianca: 0.92 },
    ],
    comparison: { empty_fields: [], conflicts: [], matching: [] },
    auto_fill_suggestions: {},
    ...overrides,
  },
});

const props = (overrides = {}) => ({
  open: true,
  results: resultados(),
  clientName: "Ana Martins",
  applying: false,
  onOpenChange: vi.fn(),
  onApplySuggestions: vi.fn(),
  ...overrides,
});

describe("AIResultsDialog — o que mostra", () => {
  it("fechado não rende nada", () => {
    render(<AIResultsDialog {...props({ open: false })} />);

    expect(screen.queryByText("Resultados da Análise IA")).not.toBeInTheDocument();
  });

  it("lista os documentos processados com a confiança", () => {
    render(<AIResultsDialog {...props()} />);

    expect(screen.getByText("irs_2025.pdf")).toBeInTheDocument();
    expect(screen.getByText(/92%/)).toBeInTheDocument();
  });

  it("identifica o cliente no subtítulo", () => {
    render(<AIResultsDialog {...props()} />);

    expect(screen.getByText(/Ana Martins/)).toBeInTheDocument();
  });

  it("sem nome de cliente não mostra 'undefined'", () => {
    render(<AIResultsDialog {...props({ clientName: null })} />);

    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  it("sem resultados não rebenta", () => {
    render(<AIResultsDialog {...props({ results: null })} />);

    expect(screen.getByText("Resultados da Análise IA")).toBeInTheDocument();
  });
});

describe("AIResultsDialog — aplicar sugestões", () => {
  const comSugestoes = resultados({
    auto_fill_suggestions: {
      monthly_income: { value: "1850", confidence: 0.9 },
      employer_name: { value: "Empresa X", confidence: 0.8 },
    },
  });

  it("sem sugestões, o botão de aplicar não existe", () => {
    render(<AIResultsDialog {...props()} />);

    expect(screen.queryByRole("button", { name: /Aplicar Sugestões/ })).not.toBeInTheDocument();
  });

  it("com sugestões, aplicar entrega só os valores", async () => {
    // O contentor escreve na ficha: precisa de `{campo: valor}`, não da
    // estrutura com a confiança lá dentro.
    const utilizador = userEvent.setup();
    const onApplySuggestions = vi.fn();
    render(
      <AIResultsDialog {...props({ results: comSugestoes, onApplySuggestions })} />,
    );

    await utilizador.click(screen.getByRole("button", { name: /Aplicar Sugestões/ }));

    expect(onApplySuggestions).toHaveBeenCalledWith({
      monthly_income: "1850",
      employer_name: "Empresa X",
    });
  });

  it("a aplicar, o botão bloqueia", () => {
    render(<AIResultsDialog {...props({ results: comSugestoes, applying: true })} />);

    expect(screen.getByRole("button", { name: /Aplicar Sugestões/ })).toBeDisabled();
  });

  it("Fechar pede o fecho ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<AIResultsDialog {...props({ onOpenChange })} />);

    await utilizador.click(screen.getByRole("button", { name: "Fechar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
