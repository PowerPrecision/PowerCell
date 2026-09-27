/**
 * A coluna de reconciliação só deixa cartões SAIR.
 *
 * ÉPICO 10, PARTE 3.
 *   O quadro passou a recolher, numa coluna própria, os processos cujo
 *   `status` gravado o motor não reconhece — os 125 do retrato de
 *   produção (`perdido`, `cancelado`, `arquivo`). Ela não é uma fase: é
 *   uma caixa de entrada de reconciliação, visível a ADMIN/CEO.
 *
 *   Arrastar um cartão PARA lá seria pedir ao servidor um estado que não
 *   existe — ele responde 400 "Estado inválido" e o utilizador leva um
 *   erro por uma acção que a UI lhe deixou fazer. O certo é a coluna não
 *   a aceitar.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import KanbanColumn from "../KanbanColumn";

const coluna = (extra = {}) => ({
  id: "clientes_espera",
  name: "clientes_espera",
  label: "Clientes em Espera",
  color: "#6B7280",
  order: 1,
  count: 1,
  processes: [
    { id: "p1", process_number: "PROC-001", client_name: "Ana" },
  ],
  ...extra,
});

// `KanbanCard` usa `useNavigate` — sem Router, a coluna nem monta.
const montar = (col, handlers = {}) =>
  render(
    <MemoryRouter>
    <KanbanColumn
      column={col}
      isCollapsed={false}
      dragOverColumn={null}
      onDragOver={handlers.onDragOver || vi.fn()}
      onDragLeave={vi.fn()}
      onDrop={handlers.onDrop || vi.fn()}
      onToggleCollapse={vi.fn()}
      onDragStart={vi.fn()}
      onCardClick={vi.fn()}
      draggingCard={null}
    />
    </MemoryRouter>,
  );

describe("Coluna de reconciliação", () => {
  it("não aceita um cartão largado em cima", () => {
    const onDrop = vi.fn();
    const { container } = montar(
      coluna({
        name: "__desconhecidas__",
        label: "Fases desconhecidas",
        reconciliacao: true,
      }),
      { onDrop },
    );
    fireEvent.drop(container.firstChild);
    expect(onDrop).not.toHaveBeenCalled();
  });

  it("nem sinaliza que aceitaria", () => {
    // Sem isto, o contorno tracejado convidava a largar lá o cartão.
    const onDragOver = vi.fn();
    const { container } = montar(
      coluna({ name: "__desconhecidas__", reconciliacao: true }),
      { onDragOver },
    );
    fireEvent.dragOver(container.firstChild);
    expect(onDragOver).not.toHaveBeenCalled();
  });

  it("mostra a etiqueta e a contagem, para não esconder o problema", () => {
    montar(
      coluna({
        name: "__desconhecidas__",
        label: "Fases desconhecidas",
        reconciliacao: true,
        order: 10000,
        count: 125,
      }),
    );
    // Sem número de passo à frente: não é um passo do workflow.
    expect(screen.getByText("Fases desconhecidas")).toBeInTheDocument();
    expect(screen.getByText("125")).toBeInTheDocument();
    expect(screen.queryByText(/10000/)).not.toBeInTheDocument();
  });
});

describe("Contraprova: uma coluna normal continua a aceitar", () => {
  it("chama o onDrop", () => {
    const onDrop = vi.fn();
    const { container } = montar(coluna(), { onDrop });
    fireEvent.drop(container.firstChild);
    expect(onDrop).toHaveBeenCalledWith(expect.anything(), "clientes_espera");
  });

  it("chama o onDragOver", () => {
    const onDragOver = vi.fn();
    const { container } = montar(coluna(), { onDragOver });
    fireEvent.dragOver(container.firstChild);
    expect(onDragOver).toHaveBeenCalledWith(expect.anything(), "clientes_espera");
  });

  it("uma coluna sem a flag não é tratada como reconciliação", () => {
    // `reconciliacao` ausente !== false — a comparação tem de ser estrita.
    const onDrop = vi.fn();
    const { container } = montar(coluna({ reconciliacao: undefined }), { onDrop });
    fireEvent.drop(container.firstChild);
    expect(onDrop).toHaveBeenCalled();
  });
});
