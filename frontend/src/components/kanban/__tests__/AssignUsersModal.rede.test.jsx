/**
 * O modal de atribuição do Kanban pede ao servidor a lista DESTE processo
 * (o Master só vê quem o processo alcança) e não reaproveita a de outro.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getStaffUsers: vi.fn(),
}));

vi.mock("../../../services/api", () => api);

import AssignUsersModal from "../AssignUsersModal";

const processo = (id) => ({ id, process_number: 7, client_name: "Cliente " + id });

beforeEach(() => {
  api.getStaffUsers.mockReset();
  api.getStaffUsers.mockResolvedValue({ data: [
    { id: "u-1", name: "Ana", role: "consultor", is_active: true },
  ] });
});

const montar = (p) => (
  <AssignUsersModal open onOpenChange={() => {}} process={p} token="t" onSuccess={() => {}} />
);

describe("AssignUsersModal — a lista é a do processo", () => {
  it("pede o staff com o id do processo, por Axios", async () => {
    render(montar(processo("proc-1")));
    await waitFor(() => expect(api.getStaffUsers).toHaveBeenCalledTimes(1));
    expect(api.getStaffUsers).toHaveBeenCalledWith({ processId: "proc-1" });
  });

  it("outro processo volta a pedir a lista (não reaproveita a anterior)", async () => {
    const { rerender } = render(montar(processo("proc-1")));
    await waitFor(() => expect(api.getStaffUsers).toHaveBeenCalledTimes(1));

    rerender(montar(processo("proc-2")));
    await waitFor(() => expect(api.getStaffUsers).toHaveBeenCalledTimes(2));
    expect(api.getStaffUsers).toHaveBeenLastCalledWith({ processId: "proc-2" });
  });

  it("o mesmo processo não repete o pedido (contraprova)", async () => {
    const { rerender } = render(montar(processo("proc-1")));
    await waitFor(() => expect(api.getStaffUsers).toHaveBeenCalledTimes(1));
    await screen.findByText(/Gerir Atribui|Atribuir/i);

    rerender(montar({ ...processo("proc-1"), client_name: "Renomeado" }));
    await waitFor(() => expect(api.getStaffUsers).toHaveBeenCalledTimes(1));
  });
});

describe("AssignUsersModal — empresa de cada pessoa", () => {
  it("as opções dizem a empresa (o <Select> só aceita texto)", async () => {
    api.getStaffUsers.mockResolvedValue({ data: [
      { id: "u-1", name: "Ana", role: "consultor", is_active: true, empresa_etiqueta: "Precision" },
      { id: "u-2", name: "Rui", role: "consultor", is_active: true },
    ] });
    const { default: userEvent } = await import("@testing-library/user-event");
    render(montar(processo("proc-9")));
    await waitFor(() => expect(api.getStaffUsers).toHaveBeenCalled());

    const gatilhos = await screen.findAllByRole("combobox");
    await userEvent.click(gatilhos[0]);

    expect(await screen.findByRole("option", { name: "Ana (consultor) — Precision" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Rui (consultor)" })).toBeInTheDocument();
  });
});
