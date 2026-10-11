/**
 * Um cartão de uma fase FECHADA não se arrasta (D-34).
 *
 * Antes, arrastar um cartão «Concluído» para uma fase activa era a forma de
 * reabrir, e entre duas fases terminais (concluído → arquivo) passava sem
 * reabrir. A regra do dono do produto é uma só: um processo fechado é um
 * arquivo intocável até ser REABERTO — pela acção «Reabrir», não pelo arrasto.
 * O servidor recusa (403) a TODOS os perfis; o ecrã tem de dizer o mesmo
 * antes do gesto.
 *
 * Só o DOM real prova isto: `draggable` é um atributo, e o `dragstart` de um
 * cartão fechado não pode chegar ao quadro.
 */
import { describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import KanbanColumn from "../KanbanColumn";

const coluna = (extra = {}) => ({
  id: "col",
  name: "fase_bancaria",
  label: "Fase Bancária",
  color: "#6B7280",
  order: 1,
  count: 1,
  is_active: true,
  processes: [{ id: "p1", process_number: "PROC-001", client_name: "Ana" }],
  ...extra,
});

function montar(col, onDragStart = vi.fn()) {
  render(
    <MemoryRouter>
      <KanbanColumn
        column={col}
        isCollapsed={false}
        dragOverColumn={null}
        onDragOver={vi.fn()}
        onDragLeave={vi.fn()}
        onDrop={vi.fn()}
        onToggleCollapse={vi.fn()}
        onDragStart={onDragStart}
        onCardClick={vi.fn()}
        draggingCard={null}
      />
    </MemoryRouter>,
  );
  return { cartao: screen.getByTestId("process-card-p1"), onDragStart };
}

describe("Kanban — cartões de uma fase fechada", () => {
  it("numa fase activa o cartão arrasta-se (contraprova)", () => {
    const { cartao, onDragStart } = montar(coluna());
    expect(cartao.getAttribute("draggable")).toBe("true");
    fireEvent.dragStart(cartao);
    expect(onDragStart).toHaveBeenCalledTimes(1);
  });

  it("numa fase que o motor marca como fechada (is_active=false) NÃO se arrasta", () => {
    // Nome fora da lista legada: só o motor sabe que é terminal.
    const { cartao, onDragStart } = montar(coluna({ name: "pos_venda", is_active: false }));
    expect(cartao.getAttribute("draggable")).toBe("false");
    expect(cartao.getAttribute("data-fechado")).toBe("true");
    fireEvent.dragStart(cartao);
    expect(onDragStart).not.toHaveBeenCalled();
  });

  it("sem a flag do motor, a lista legada fecha 'concluido' e 'arquivo'", () => {
    for (const name of ["concluido", "arquivo", "cancelado"]) {
      const { is_active, ...semFlag } = coluna({ name }); // eslint-disable-line no-unused-vars
      cleanup(); // uma coluna de cada vez: o `getByTestId` não pode ver a anterior
      const { cartao, onDragStart } = montar(semFlag);
      expect(cartao.getAttribute("draggable")).toBe("false");
      fireEvent.dragStart(cartao);
      expect(onDragStart).not.toHaveBeenCalled();
    }
  });

  it("uma fase que o motor marca activa vence o nome (is_active=true)", () => {
    const { cartao } = montar(coluna({ name: "concluido", is_active: true }));
    expect(cartao.getAttribute("draggable")).toBe("true");
  });

  it("diz porquê no cartão (title) e continua a abrir ao clicar", () => {
    const onCardClick = vi.fn();
    render(
      <MemoryRouter>
        <KanbanColumn
          column={coluna({ name: "concluido", is_active: false })}
          isCollapsed={false} dragOverColumn={null}
          onDragOver={vi.fn()} onDragLeave={vi.fn()} onDrop={vi.fn()}
          onToggleCollapse={vi.fn()} onDragStart={vi.fn()}
          onCardClick={onCardClick} draggingCard={null}
        />
      </MemoryRouter>,
    );
    const cartao = screen.getByTestId("process-card-p1");
    expect(cartao.getAttribute("title")).toMatch(/reabra/i);
    fireEvent.click(cartao);
    expect(onCardClick).toHaveBeenCalledTimes(1);
  });
});
