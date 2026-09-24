/**
 * O CRUD de Automações — ponto 13 (Lote 5, Secção B).
 *
 * O QUE PARECIA FALTAR E NÃO FALTAVA
 *   Rotas, serviços e UI de edição/eliminação estavam todos lá. O que
 *   fazia o ecrã parecer avariado eram TRÊS silêncios:
 *
 *   1. `fetchRules` tinha `catch { /* silent *\/ }` e a seguir
 *      `setLoading(false)`. Uma leitura falhada caía no estado vazio
 *      "Criar primeira regra": o administrador via "não há regras" e
 *      concluía que o CRUD não funcionava. É o padrão do Bug 1 (VLM no
 *      Escuro) noutro ecrã — um erro renderizado como sucesso vazio.
 *   2. `handleToggle` engolia o erro: o interruptor saltava para trás
 *      sem explicação.
 *   3. `handleDelete` apagava uma regra de NEGÓCIO com um clique, sem
 *      confirmação, e engolia a mensagem do backend.
 *
 * A ORDEM DOS RAMOS É PARTE DA CORREÇÃO: com `rules.length === 0` à
 * frente do erro, uma leitura falhada continuava a dizer "Nenhuma regra
 * criada" — o mesmo defeito escrito de outra maneira.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div>{children}</div>,
}));
vi.mock("../../components/automation/EngineStatusPanel", () => ({
  default: () => <div />,
}));

const getAutomationRules = vi.fn();
const deleteAutomationRule = vi.fn();
const updateAutomationRule = vi.fn();
vi.mock("../../services/api", () => ({
  getAutomationRules: (...a) => getAutomationRules(...a),
  createAutomationRule: vi.fn(),
  updateAutomationRule: (...a) => updateAutomationRule(...a),
  deleteAutomationRule: (...a) => deleteAutomationRule(...a),
  getWorkflowStatuses: vi.fn().mockResolvedValue({ data: [] }),
}));

const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (...a) => toastError(...a),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

const { default: AutomationPage } = await import("../AutomationPage");

const REGRA = {
  id: "r1",
  name: "Ao indexar, pedir IRS",
  trigger: "process_status_changed",
  action: "create_task",
  is_active: true,
  trigger_config: { target_status: "fase_documental" },
  action_config: { title: "Pedir IRS" },
};

beforeEach(() => {
  vi.clearAllMocks();
  getAutomationRules.mockResolvedValue({ data: { rules: [REGRA] } });
  deleteAutomationRule.mockResolvedValue({ data: {} });
  updateAutomationRule.mockResolvedValue({ data: {} });
});

describe("AutomationPage — uma leitura falhada não é uma lista vazia", () => {
  it("mostra o erro em vez de 'Criar primeira regra'", async () => {
    getAutomationRules.mockRejectedValue({
      response: { data: { detail: "Sem permissões para ler as regras" } },
    });
    render(<AutomationPage />);

    expect(await screen.findByTestId("automation-erro")).toBeTruthy();
    expect(screen.queryByText("Criar primeira regra")).toBeNull();
  });

  it("a mensagem do backend chega ao utilizador", async () => {
    getAutomationRules.mockRejectedValue({
      response: { data: { detail: "Sem permissões para ler as regras" } },
    });
    render(<AutomationPage />);

    expect(await screen.findByTestId("automation-erro")).toHaveTextContent(
      "Sem permissões",
    );
  });

  it("contraprova: sem regras E sem erro, o estado vazio é o certo", async () => {
    getAutomationRules.mockResolvedValue({ data: { rules: [] } });
    render(<AutomationPage />);

    expect(await screen.findByText("Criar primeira regra")).toBeTruthy();
    expect(screen.queryByTestId("automation-erro")).toBeNull();
  });
});

describe("AutomationPage — eliminar exige confirmação", () => {
  it("clicar em eliminar NÃO apaga logo", async () => {
    const user = userEvent.setup();
    render(<AutomationPage />);
    await screen.findByTestId("rule-card-r1");

    await user.click(screen.getByRole("button", { name: "Eliminar regra" }));

    expect(deleteAutomationRule).not.toHaveBeenCalled();
    expect(screen.getByText("Eliminar esta regra?")).toBeTruthy();
  });

  it("só apaga depois de confirmar", async () => {
    const user = userEvent.setup();
    render(<AutomationPage />);
    await screen.findByTestId("rule-card-r1");

    await user.click(screen.getByRole("button", { name: "Eliminar regra" }));
    await user.click(screen.getByTestId("confirmar-eliminar-regra"));

    await waitFor(() => expect(deleteAutomationRule).toHaveBeenCalledWith("r1"));
  });

  it("cancelar não apaga nada", async () => {
    const user = userEvent.setup();
    render(<AutomationPage />);
    await screen.findByTestId("rule-card-r1");

    await user.click(screen.getByRole("button", { name: "Eliminar regra" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(deleteAutomationRule).not.toHaveBeenCalled();
  });

  it("uma eliminação falhada diz porquê", async () => {
    const user = userEvent.setup();
    deleteAutomationRule.mockRejectedValue({
      response: { data: { detail: "Regra não encontrada" } },
    });
    render(<AutomationPage />);
    await screen.findByTestId("rule-card-r1");

    await user.click(screen.getByRole("button", { name: "Eliminar regra" }));
    await user.click(screen.getByTestId("confirmar-eliminar-regra"));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(expect.stringContaining("Regra não encontrada")),
    );
  });
});

describe("AutomationPage — o interruptor deixou de engolir", () => {
  it("um erro ao activar/desactivar é dito", async () => {
    const user = userEvent.setup();
    updateAutomationRule.mockRejectedValue({
      response: { data: { detail: "Regra de outra rede" } },
    });
    render(<AutomationPage />);
    await screen.findByTestId("rule-card-r1");

    await user.click(
      screen.getByRole("switch", { name: /Ativar\/desativar regra/ }),
    );

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(expect.stringContaining("outra rede")),
    );
  });
});
