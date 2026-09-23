/**
 * Teste do diálogo "Este documento é de quem?" (Épico 8, Eixo 1).
 *
 * Âmbito: prova que é um componente CONTROLADO — cada clique devolve UMA
 * intenção ao contentor em vez de reescrever a lista aqui dentro — e que a
 * guarda de segurança se mantém: não se aplica nada com um documento por
 * decidir, porque isso escreveria dados de identidade no titular errado.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TitularChoiceDialog, { ESCOLHAS } from "../TitularChoiceDialog";

const documento = (overrides = {}) => ({
  key: "d1",
  file_name: "cartao_cidadao.pdf",
  choice: null,
  titular1_name: "Ana Martins",
  titular2_name: "Bruno Martins",
  ...overrides,
});

const props = (overrides = {}) => ({
  open: true,
  items: [documento()],
  onOpenChange: vi.fn(),
  onChoose: vi.fn(),
  onConfirm: vi.fn(),
  ...overrides,
});

describe("TitularChoiceDialog — abertura", () => {
  it("fechado não rende nada", () => {
    render(<TitularChoiceDialog {...props({ open: false })} />);

    expect(screen.queryByText("Este documento é de quem?")).not.toBeInTheDocument();
  });

  it("aberto mostra o documento por decidir", () => {
    render(<TitularChoiceDialog {...props()} />);

    expect(screen.getByText("Este documento é de quem?")).toBeInTheDocument();
    expect(screen.getByText("cartao_cidadao.pdf")).toBeInTheDocument();
  });

  it("os nomes dos titulares aparecem nos botões", () => {
    // Sem o nome, o consultor tem de adivinhar qual é o titular 1.
    render(<TitularChoiceDialog {...props()} />);

    expect(screen.getByRole("button", { name: /Titular 1: Ana Martins/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Titular 2: Bruno Martins/ })).toBeInTheDocument();
  });

  it("sem nome conhecido, o botão fica só com o número", () => {
    render(
      <TitularChoiceDialog
        {...props({ items: [documento({ titular1_name: null, titular2_name: null })] })}
      />,
    );

    expect(screen.getByRole("button", { name: "Titular 1" })).toBeInTheDocument();
  });
});

describe("TitularChoiceDialog — escolhas devolvem UMA intenção", () => {
  it("escolher o titular 1 avisa o contentor com o índice", async () => {
    const utilizador = userEvent.setup();
    const onChoose = vi.fn();
    render(<TitularChoiceDialog {...props({ onChoose })} />);

    await utilizador.click(screen.getByRole("button", { name: /Titular 1/ }));

    expect(onChoose).toHaveBeenCalledWith(0, ESCOLHAS.TITULAR_1);
    expect(onChoose).toHaveBeenCalledTimes(1);
  });

  it("escolher o titular 2 e ignorar usam a mesma via", async () => {
    const utilizador = userEvent.setup();
    const onChoose = vi.fn();
    render(<TitularChoiceDialog {...props({ onChoose })} />);

    await utilizador.click(screen.getByRole("button", { name: /Titular 2/ }));
    await utilizador.click(screen.getByRole("button", { name: "Ignorar" }));

    expect(onChoose).toHaveBeenNthCalledWith(1, 0, ESCOLHAS.TITULAR_2);
    expect(onChoose).toHaveBeenNthCalledWith(2, 0, ESCOLHAS.IGNORAR);
  });

  it("com vários documentos, o índice identifica o certo", async () => {
    const utilizador = userEvent.setup();
    const onChoose = vi.fn();
    render(
      <TitularChoiceDialog
        {...props({
          items: [
            documento({ key: "a", file_name: "primeiro.pdf" }),
            documento({ key: "b", file_name: "segundo.pdf" }),
          ],
          onChoose,
        })}
      />,
    );

    // `closest("div")` daria a div do NOME, que não contém os botões; o
    // cartão do documento é o nível acima.
    const segundo = screen.getByText("segundo.pdf").parentElement;

    // As TRÊS vias têm de levar o índice certo: cobrir só uma deixava
    // passar um índice fixo nas outras duas — e os dados de identidade
    // iam parar ao documento errado.
    await utilizador.click(within(segundo).getByRole("button", { name: /Titular 1/ }));
    expect(onChoose).toHaveBeenLastCalledWith(1, ESCOLHAS.TITULAR_1);

    await utilizador.click(within(segundo).getByRole("button", { name: /Titular 2/ }));
    expect(onChoose).toHaveBeenLastCalledWith(1, ESCOLHAS.TITULAR_2);

    await utilizador.click(within(segundo).getByRole("button", { name: "Ignorar" }));
    expect(onChoose).toHaveBeenLastCalledWith(1, ESCOLHAS.IGNORAR);
  });

  it("a escolha feita fica visualmente marcada", () => {
    // O estado mostrado vem das props, não de estado interno.
    const { rerender } = render(<TitularChoiceDialog {...props()} />);
    const antes = screen.getByRole("button", { name: /Titular 1/ }).className;

    rerender(
      <TitularChoiceDialog
        {...props({ items: [documento({ choice: ESCOLHAS.TITULAR_1 })] })}
      />,
    );

    expect(screen.getByRole("button", { name: /Titular 1/ }).className).not.toBe(antes);
  });
});

describe("TitularChoiceDialog — guarda de aplicação", () => {
  it("com um documento por decidir, Aplicar está bloqueado", () => {
    // Aplicar aqui escreveria dados de identidade no titular errado.
    render(<TitularChoiceDialog {...props()} />);

    expect(screen.getByRole("button", { name: /Aplicar/ })).toBeDisabled();
  });

  it("com todos decididos, Aplicar liberta", () => {
    render(
      <TitularChoiceDialog
        {...props({ items: [documento({ choice: ESCOLHAS.IGNORAR })] })}
      />,
    );

    expect(screen.getByRole("button", { name: /Aplicar/ })).toBeEnabled();
  });

  it("basta UM por decidir para bloquear", () => {
    render(
      <TitularChoiceDialog
        {...props({
          items: [
            documento({ key: "a", choice: ESCOLHAS.TITULAR_1 }),
            documento({ key: "b", choice: null }),
          ],
        })}
      />,
    );

    expect(screen.getByRole("button", { name: /Aplicar/ })).toBeDisabled();
  });

  it("Aplicar chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <TitularChoiceDialog
        {...props({ items: [documento({ choice: ESCOLHAS.TITULAR_1 })], onConfirm })}
      />,
    );

    await utilizador.click(screen.getByRole("button", { name: /Aplicar/ }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("Cancelar fecha sem aplicar", async () => {
    const utilizador = userEvent.setup();
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn();
    render(<TitularChoiceDialog {...props({ onOpenChange, onConfirm })} />);

    await utilizador.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("sem documentos, Aplicar não está bloqueado", () => {
    // `[].some(...)` é falso: lista vazia não tem nada por decidir.
    render(<TitularChoiceDialog {...props({ items: [] })} />);

    expect(screen.getByRole("button", { name: /Aplicar/ })).toBeEnabled();
  });
});
