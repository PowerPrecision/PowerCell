/**
 * Reatribuição de tarefas — ponto 10 (Lote 5, Secção B).
 *
 * O backend já aceitava `assigned_to` no `PUT /tasks/{id}`. O que não
 * havia era forma de lá chegar: o diálogo da tarefa mostrava "Atribuído
 * a" como TEXTO. Uma tarefa que caísse na pessoa errada só se resolvia
 * apagando-a e criando outra — o que perde o histórico e o prefixo
 * `[PROC-012]` que `task_api_crud.run_create_task` acrescenta.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TaskAssigneeDialog from "../TaskAssigneeDialog";

const UTILIZADORES = [
  { id: "u1", name: "Ana", role: "consultor" },
  { id: "u2", name: "Bruno", role: "intermediario" },
  { id: "u3", name: "Carla", role: "admin" },
];

const TAREFA = { id: "t1", title: "Pedir IRS", assigned_to: ["u1"], process_id: "p1" };

const montar = (props = {}) =>
  render(
    <TaskAssigneeDialog
      open
      onOpenChange={vi.fn()}
      task={TAREFA}
      users={UTILIZADORES}
      equipaDoProcesso={["u1", "u2"]}
      onConfirm={vi.fn()}
      {...props}
    />,
  );

describe("TaskAssigneeDialog — estado inicial", () => {
  it("parte de quem já é responsável", () => {
    montar();
    expect(screen.getByRole("checkbox", { name: "Ana" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Bruno" })).not.toBeChecked();
  });

  it("mostra a equipa do processo separada do resto", () => {
    montar();
    expect(screen.getByText("Equipa do processo")).toBeTruthy();
    expect(screen.getByText("Fora da equipa do processo")).toBeTruthy();
  });

  it("uma tarefa sem processo não separa nada", () => {
    montar({ task: { ...TAREFA, process_id: null }, equipaDoProcesso: [] });
    expect(screen.queryByText("Equipa do processo")).toBeNull();
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  it("equipa por confirmar é DITA, não escondida", () => {
    // Lote 4, ponto 13: cair para todo o staff em silêncio deixava o
    // utilizador com uma lista enorme sem saber porquê.
    montar({ equipaDoProcesso: [] });
    expect(screen.getByTestId("equipa-por-confirmar")).toBeTruthy();
  });

  it("sem processo não reclama de equipa nenhuma", () => {
    // Contraprova: o aviso só aparece quando significa alguma coisa.
    montar({ task: { ...TAREFA, process_id: null }, equipaDoProcesso: [] });
    expect(screen.queryByTestId("equipa-por-confirmar")).toBeNull();
  });
});

describe("TaskAssigneeDialog — escolher", () => {
  it("passar a tarefa de uma pessoa para outra", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    montar({ onConfirm });

    await user.click(screen.getByRole("checkbox", { name: "Ana" }));
    await user.click(screen.getByRole("checkbox", { name: "Bruno" }));
    await user.click(screen.getByTestId("confirmar-responsaveis"));

    expect(onConfirm).toHaveBeenCalledWith(["u2"]);
  });

  it("acrescentar alguém mantém quem já lá estava", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    montar({ onConfirm });

    await user.click(screen.getByRole("checkbox", { name: "Carla" }));
    await user.click(screen.getByTestId("confirmar-responsaveis"));

    expect(onConfirm).toHaveBeenCalledWith(["u1", "u3"]);
  });

  it("deixar a tarefa sem ninguém é possível, e avisado", async () => {
    // Uma tarefa órfã é um estado legítimo (o Lote 4 marca-as com
    // `assignment_orphaned`), mas não pode acontecer por distracção.
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    montar({ onConfirm });

    await user.click(screen.getByRole("checkbox", { name: "Ana" }));
    expect(screen.getByRole("status").textContent).toContain("sem responsável");

    await user.click(screen.getByTestId("confirmar-responsaveis"));
    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it("cancelar não confirma nada", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    montar({ onConfirm, onOpenChange });

    await user.click(screen.getByRole("checkbox", { name: "Bruno" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
