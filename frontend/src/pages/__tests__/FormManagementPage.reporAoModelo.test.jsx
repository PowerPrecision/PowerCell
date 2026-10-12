/**
 * «Repor ao Modelo» no ecrã do formulário — montado a sério (a página).
 *
 * O botão só existe com cópia própria; abre o diálogo com password; só o servidor repõe;
 * depois recarrega a configuração.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const api = vi.hoisted(() => ({
  getFormConfigAdmin: vi.fn(),
  updateFormConfigAdmin: vi.fn(),
  resetFormConfigAdmin: vi.fn(),
  reporFormularioAoModelo: vi.fn(),
  createFormCustomField: vi.fn(),
  deleteFormCustomField: vi.fn(),
  listFormTemplates: vi.fn(),
  saveFormTemplate: vi.fn(),
  previewFormTemplate: vi.fn(),
  activateFormTemplate: vi.fn(),
  duplicateFormTemplate: vi.fn(),
  deleteFormTemplate: vi.fn(),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("../../layouts/DashboardLayout", () => ({ default: ({ children }) => <div>{children}</div> }));

import FormManagementPage from "../FormManagementPage";
import { toast } from "sonner";

const CAMPOS = [
  { field_key: "name", label: "Nome", step: 1, order: 1, is_visible: true, is_required: true, field_type: "text" },
];

function resposta(extra = {}) {
  return {
    data: {
      fields: CAMPOS, step_config: {}, step_labels: {},
      network_id: "grupo_domus", empresas: ["Domus"], empresas_detalhe: [{ id: "cmp-domus", name: "Domus" }],
      tem_formulario_proprio: true, ...extra,
    },
  };
}

describe("FormManagementPage — Repor ao Modelo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listFormTemplates.mockResolvedValue({ data: { templates: [] } });
    api.getFormConfigAdmin.mockResolvedValue(resposta());
  });

  it("sem cópia própria não há botão (já usa o modelo)", async () => {
    api.getFormConfigAdmin.mockResolvedValue(resposta({ tem_formulario_proprio: false }));
    render(<FormManagementPage embedded />);
    await screen.findByTestId("formulario-rede-modelo");
    expect(screen.queryByTestId("repor-formulario-modelo-btn")).toBeNull();
  });

  it("o botão abre o diálogo da password e não chama o servidor", async () => {
    const user = userEvent.setup();
    render(<FormManagementPage embedded />);
    await user.click(await screen.findByTestId("repor-formulario-modelo-btn"));

    const dialogo = await screen.findByTestId("repor-modelo-dialog");
    expect(dialogo).toHaveTextContent(/Domus/);
    expect(dialogo).toHaveTextContent(/não se recuperam/i);
    expect(api.reporFormularioAoModelo).not.toHaveBeenCalled();
    expect(api.resetFormConfigAdmin).not.toHaveBeenCalled();
  });

  it("confirma com a password, avisa e recarrega a configuração", async () => {
    const user = userEvent.setup();
    api.reporFormularioAoModelo.mockResolvedValue({ data: { reposto: true } });
    render(<FormManagementPage embedded />);
    await user.click(await screen.findByTestId("repor-formulario-modelo-btn"));
    await user.type(await screen.findByLabelText(/a sua password actual/i), "Segredo-1!");
    api.getFormConfigAdmin.mockResolvedValue(resposta({ tem_formulario_proprio: false }));
    await user.click(screen.getByTestId("repor-modelo-confirmar"));

    await waitFor(() => expect(api.reporFormularioAoModelo).toHaveBeenCalledWith("Segredo-1!"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Formulário reposto ao modelo"));
    await waitFor(() => expect(api.getFormConfigAdmin).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId("repor-formulario-modelo-btn")).toBeNull());
  });

  it("password errada: o erro fica no diálogo e nada recarrega", async () => {
    const user = userEvent.setup();
    api.reporFormularioAoModelo.mockRejectedValue(
      Object.assign(new Error("x"), { response: { status: 403, data: { detail: "Password incorrecta." } } }),
    );
    render(<FormManagementPage embedded />);
    await user.click(await screen.findByTestId("repor-formulario-modelo-btn"));
    await user.type(await screen.findByLabelText(/a sua password actual/i), "errada");
    await user.click(screen.getByTestId("repor-modelo-confirmar"));

    expect(await screen.findByTestId("repor-modelo-erro")).toHaveAttribute("data-tipo", "password_errada");
    expect(toast.success).not.toHaveBeenCalled();
    expect(api.getFormConfigAdmin).toHaveBeenCalledTimes(1);
  });
});
