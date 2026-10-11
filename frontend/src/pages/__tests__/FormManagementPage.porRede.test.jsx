/**
 * O ecrã de administração do formulário é POR REDE (D-37).
 *
 * Monta a PÁGINA (nunca tinha sido montada num teste) e afirma o que interessa:
 *  - diz que rede está a editar e dá o link de registo de cada empresa dela;
 *  - fala com o servidor SÓ por Axios (`fetch` cru perde o `X-Company-Id`, e com ele a
 *    rede em contexto: editava-se sempre a rede por omissão);
 *  - a primeira gravação passa o aviso «usa o modelo» a desligado.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url));

const api = vi.hoisted(() => ({
  getFormConfigAdmin: vi.fn(),
  updateFormConfigAdmin: vi.fn(),
  resetFormConfigAdmin: vi.fn(),
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

const CAMPOS = [
  { field_key: "name", label: "Nome", step: 1, order: 1, is_visible: true, is_required: true, field_type: "text" },
  { field_key: "campo_da_domus", label: "Só da Domus", step: 1, order: 2, is_visible: true, is_required: false, field_type: "text", is_custom: true },
];

function resposta(extra = {}) {
  return {
    data: {
      fields: CAMPOS, step_config: {}, step_labels: {},
      network_id: "grupo_domus",
      empresas: ["Domus", "Domus Norte"],
      empresas_detalhe: [{ id: "cmp-domus", name: "Domus" }, { id: "cmp-norte", name: "Domus Norte" }],
      tem_formulario_proprio: true,
      ...extra,
    },
  };
}

describe("FormManagementPage — por rede", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listFormTemplates.mockResolvedValue({ data: { templates: [] } });
    api.updateFormConfigAdmin.mockResolvedValue({ data: {} });
    globalThis.fetch = vi.fn(() => { throw new Error("fetch cru: perde o X-Company-Id"); });
  });

  it("diz que rede edita e dá o link de registo de CADA empresa dela", async () => {
    api.getFormConfigAdmin.mockResolvedValue(resposta());
    render(<FormManagementPage embedded />);

    const aviso = await screen.findByTestId("formulario-rede-aviso");
    expect(aviso).toHaveTextContent("Domus, Domus Norte");
    expect(aviso).toHaveTextContent("as outras redes não são afetadas");
    expect(screen.queryByTestId("formulario-rede-modelo")).toBeNull();

    const links = within(screen.getByTestId("links-de-registo"));
    expect(links.getByText(`${window.location.origin}/registo?empresa=cmp-domus`)).toBeInTheDocument();
    expect(links.getByText(`${window.location.origin}/registo?empresa=cmp-norte`)).toBeInTheDocument();
    expect(links.getByRole("button", { name: /copiar link de registo de domus norte/i })).toBeInTheDocument();
  });

  it("avisa que a rede ainda usa o modelo base", async () => {
    api.getFormConfigAdmin.mockResolvedValue(resposta({ tem_formulario_proprio: false }));
    render(<FormManagementPage embedded />);
    expect(await screen.findByTestId("formulario-rede-modelo")).toHaveTextContent(/modelo base/i);
  });

  it("uma rede sem empresas mostra o identificador da rede e nenhum link", async () => {
    api.getFormConfigAdmin.mockResolvedValue(resposta({ empresas: [], empresas_detalhe: [] }));
    render(<FormManagementPage embedded />);
    expect(await screen.findByTestId("formulario-rede-aviso")).toHaveTextContent("grupo_domus");
    expect(screen.queryByTestId("links-de-registo")).toBeNull();
  });

  it("uma resposta sem a forma esperada não rebenta o ecrã (Array.isArray, nunca || [])", async () => {
    api.getFormConfigAdmin.mockResolvedValue(resposta({ empresas: { a: 1 }, empresas_detalhe: "x" }));
    render(<FormManagementPage embedded />);
    expect(await screen.findByTestId("formulario-rede")).toBeInTheDocument();
    expect(screen.queryByTestId("links-de-registo")).toBeNull();
  });

  it("guardar vai por Axios e desliga o aviso do modelo", async () => {
    api.getFormConfigAdmin.mockResolvedValue(resposta({ tem_formulario_proprio: false }));
    render(<FormManagementPage embedded />);
    await screen.findByTestId("formulario-rede-modelo");

    // Uma alteração (obrigatório → opcional) liga o botão «Guardar».
    await userEvent.click(screen.getByTestId("toggle-required-name"));
    await userEvent.click(screen.getByTestId("save-form-config"));
    expect(api.updateFormConfigAdmin).toHaveBeenCalledTimes(1);
    expect(api.updateFormConfigAdmin.mock.calls[0][0].fields.map((f) => f.field_key)).toContain("campo_da_domus");
    expect(globalThis.fetch).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(screen.queryByTestId("formulario-rede-modelo")).toBeNull());
  });

  it("a página não tem nenhum `fetch` cru (guarda sobre a fonte, com contraprova)", () => {
    const fonte = readFileSync(join(AQUI, "..", "FormManagementPage.js"), "utf8")
      .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
    expect(fonte).toMatch(/updateFormConfigAdmin\(/); // contraprova: leu a página certa
    expect(fonte).not.toMatch(/\bfetch\(/);
  });
});
