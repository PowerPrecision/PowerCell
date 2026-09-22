/**
 * Teste do diálogo de revisão da análise IA (Épico 8, Eixo 1).
 *
 * Âmbito: as três vias de resolução de um conflito (ficar o existente,
 * ficar o extraído, escrever à mão) e a guarda que impede confirmar com
 * conflitos por resolver.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import AIReviewDialog from "../AIReviewDialog";

const conflito = (overrides = {}) => ({
  field: "monthly_income",
  existing_value: "1500",
  new_value: "1850",
  source: "recibo_vencimento.pdf",
  ...overrides,
});

const props = (overrides = {}) => ({
  open: true,
  conflicts: [conflito()],
  onOpenChange: vi.fn(),
  onResolve: vi.fn(),
  onConfirmAll: vi.fn(),
  ...overrides,
});

describe("AIReviewDialog — apresentação do conflito", () => {
  it("fechado não rende nada", () => {
    render(<AIReviewDialog {...props({ open: false })} />);

    expect(screen.queryByText("Revisão de Dados Extraídos")).not.toBeInTheDocument();
  });

  it("mostra os dois valores em confronto", () => {
    render(<AIReviewDialog {...props()} />);

    expect(screen.getByText("1500")).toBeInTheDocument();
    expect(screen.getByText("1850")).toBeInTheDocument();
  });

  it("o nome do campo vem legível, não em snake_case", () => {
    render(<AIReviewDialog {...props()} />);

    expect(screen.getByText("Monthly Income")).toBeInTheDocument();
  });

  it("indica de que documento veio o valor extraído", () => {
    // Sem a fonte, o consultor não sabe em que confiar.
    render(<AIReviewDialog {...props()} />);

    expect(screen.getByText(/recibo_vencimento\.pdf/)).toBeInTheDocument();
  });

  it("um valor em falta aparece como traço, não como 'undefined'", () => {
    render(
      <AIReviewDialog {...props({ conflicts: [conflito({ existing_value: null })] })} />,
    );

    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("sem conflitos, anuncia que está tudo resolvido", () => {
    render(<AIReviewDialog {...props({ conflicts: [] })} />);

    expect(screen.getByText("Todos os conflitos foram resolvidos!")).toBeInTheDocument();
  });
});

describe("AIReviewDialog — as três vias de resolução", () => {
  it("escolher o valor existente devolve-o ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onResolve = vi.fn();
    render(<AIReviewDialog {...props({ onResolve })} />);

    await utilizador.click(screen.getByText("Valor Existente").closest("button"));

    expect(onResolve).toHaveBeenCalledWith("monthly_income", "1500");
  });

  it("escolher o valor extraído devolve-o ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onResolve = vi.fn();
    render(<AIReviewDialog {...props({ onResolve })} />);

    await utilizador.click(screen.getByText(/Valor Extraído/).closest("button"));

    expect(onResolve).toHaveBeenCalledWith("monthly_income", "1850");
  });

  it("escrever à mão e carregar em Aplicar resolve o conflito", async () => {
    // REGRESSÃO: no monolito este botão lia o valor com
    // `e.target.parentElement.querySelector("input")`. Basta um ícone
    // dentro do botão para `e.target` passar a ser o `<svg>` e o clique
    // deixar de fazer nada, em silêncio. O campo é agora controlado.
    const utilizador = userEvent.setup();
    const onResolve = vi.fn();
    render(<AIReviewDialog {...props({ onResolve })} />);

    await utilizador.type(screen.getByLabelText(/Valor manual/), "1700");
    await utilizador.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(onResolve).toHaveBeenCalledWith("monthly_income", "1700");
  });

  it("Enter no campo manual resolve sem passar pelo botão", async () => {
    const utilizador = userEvent.setup();
    const onResolve = vi.fn();
    render(<AIReviewDialog {...props({ onResolve })} />);

    await utilizador.type(screen.getByLabelText(/Valor manual/), "1700{Enter}");

    expect(onResolve).toHaveBeenCalledWith("monthly_income", "1700");
  });

  it("o campo manual limpa-se depois de aplicar", async () => {
    const utilizador = userEvent.setup();
    render(<AIReviewDialog {...props()} />);

    const campo = screen.getByLabelText(/Valor manual/);
    await utilizador.type(campo, "1700{Enter}");

    expect(campo).toHaveValue("");
  });

  it("Aplicar está bloqueado com o campo vazio", async () => {
    // Aplicar vazio apagaria o valor do campo na ficha.
    render(<AIReviewDialog {...props()} />);

    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();
  });

  it("cada conflito tem o seu próprio rascunho", async () => {
    const utilizador = userEvent.setup();
    const onResolve = vi.fn();
    render(
      <AIReviewDialog
        {...props({
          conflicts: [
            conflito({ field: "monthly_income" }),
            conflito({ field: "employer_name", existing_value: "A", new_value: "B" }),
          ],
          onResolve,
        })}
      />,
    );

    await utilizador.type(screen.getByLabelText(/Employer Name/), "Empresa X{Enter}");

    expect(onResolve).toHaveBeenCalledWith("employer_name", "Empresa X");
    expect(screen.getByLabelText(/Monthly Income/)).toHaveValue("");
  });
});

describe("AIReviewDialog — guarda de confirmação", () => {
  it("com conflitos por resolver, Confirmar Todos está bloqueado", () => {
    render(<AIReviewDialog {...props()} />);

    expect(screen.getByRole("button", { name: /Confirmar Todos/ })).toBeDisabled();
  });

  it("sem conflitos, Confirmar Todos liberta", () => {
    render(<AIReviewDialog {...props({ conflicts: [] })} />);

    expect(screen.getByRole("button", { name: /Confirmar Todos/ })).toBeEnabled();
  });

  it("Confirmar Todos avisa o contentor e não anuncia nada por si", async () => {
    // O toast "não esqueça de guardar" vive no contentor: é ele que sabe
    // que há alterações por gravar.
    const utilizador = userEvent.setup();
    const onConfirmAll = vi.fn();
    render(<AIReviewDialog {...props({ conflicts: [], onConfirmAll })} />);

    await utilizador.click(screen.getByRole("button", { name: /Confirmar Todos/ }));

    expect(onConfirmAll).toHaveBeenCalledTimes(1);
  });

  it("Fechar pede o fecho ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<AIReviewDialog {...props({ onOpenChange })} />);

    await utilizador.click(screen.getByRole("button", { name: "Fechar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
