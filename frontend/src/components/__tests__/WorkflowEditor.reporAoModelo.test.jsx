/**
 * «Repor ao Modelo» no editor de fases — montado a sério.
 *
 * Só se falseia a fronteira (`services/api`). Prova-se: o botão só existe quando a rede tem
 * cópia própria, abre o diálogo com a password, e só depois de o servidor aceitar é que a lista
 * recarrega.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getWorkflowEditor: vi.fn(),
  createWorkflowStatus: vi.fn(),
  updateWorkflowStatus: vi.fn(),
  deleteWorkflowStatus: vi.fn(),
  reporWorkflowAoModelo: vi.fn(),
}));

vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import WorkflowEditor from "../WorkflowEditor";
import { toast } from "sonner";

const FASES = [
  { id: "w-1", name: "fase_index", label: "Fase Index", order: 1, color: "blue", auto_assign_roles: null, task_templates: null },
];

function editor(extra = {}) {
  return {
    data: {
      network_id: "grupo_a", empresas: ["Empresa A"], tem_workflow_proprio: true, statuses: FASES, ...extra,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getWorkflowEditor.mockResolvedValue(editor());
});

describe("WorkflowEditor — Repor ao Modelo", () => {
  it("o botão só existe quando a rede tem cópia própria", async () => {
    api.getWorkflowEditor.mockResolvedValue(editor({ tem_workflow_proprio: false }));
    render(<WorkflowEditor />);
    await screen.findByText("Fase Index");
    expect(screen.queryByTestId("repor-workflow-modelo-btn")).toBeNull();
  });

  it("abre o diálogo que pede a password e diz o que se perde", async () => {
    const user = userEvent.setup();
    render(<WorkflowEditor />);
    await user.click(await screen.findByTestId("repor-workflow-modelo-btn"));

    const dialogo = await screen.findByTestId("repor-modelo-dialog");
    expect(dialogo).toHaveTextContent(/Empresa A/);
    expect(dialogo).toHaveTextContent(/não se recuperam/i);
    expect(screen.getByLabelText(/a sua password actual/i)).toBeInTheDocument();
    expect(api.reporWorkflowAoModelo).not.toHaveBeenCalled();
  });

  it("clicar no botão NÃO repõe nada: só a confirmação com password chama o servidor", async () => {
    const user = userEvent.setup();
    render(<WorkflowEditor />);
    await user.click(await screen.findByTestId("repor-workflow-modelo-btn"));
    await screen.findByTestId("repor-modelo-dialog");
    expect(api.reporWorkflowAoModelo).not.toHaveBeenCalled();
  });

  it("confirma com a password, avisa e recarrega o editor", async () => {
    const user = userEvent.setup();
    api.reporWorkflowAoModelo.mockResolvedValue({ data: { reposto: true } });
    render(<WorkflowEditor />);
    await user.click(await screen.findByTestId("repor-workflow-modelo-btn"));

    await user.type(await screen.findByLabelText(/a sua password actual/i), "Segredo-1!");
    api.getWorkflowEditor.mockResolvedValue(editor({ tem_workflow_proprio: false }));
    await user.click(screen.getByTestId("repor-modelo-confirmar"));

    await waitFor(() => expect(api.reporWorkflowAoModelo).toHaveBeenCalledWith("Segredo-1!"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Workflow reposto ao modelo"));
    await waitFor(() => expect(api.getWorkflowEditor).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId("repor-workflow-modelo-btn")).toBeNull());
  });

  it("com password errada não recarrega nem avisa de sucesso", async () => {
    const user = userEvent.setup();
    api.reporWorkflowAoModelo.mockRejectedValue(Object.assign(new Error("x"), { response: { status: 403, data: { detail: "Password incorrecta." } } }));
    render(<WorkflowEditor />);
    await user.click(await screen.findByTestId("repor-workflow-modelo-btn"));
    await user.type(await screen.findByLabelText(/a sua password actual/i), "errada");
    await user.click(screen.getByTestId("repor-modelo-confirmar"));

    expect(await screen.findByTestId("repor-modelo-erro")).toHaveTextContent("Password incorrecta.");
    expect(toast.success).not.toHaveBeenCalled();
    expect(api.getWorkflowEditor).toHaveBeenCalledTimes(1);
  });
});
