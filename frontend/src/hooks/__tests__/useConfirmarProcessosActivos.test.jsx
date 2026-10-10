/**
 * O aviso «este cliente já tem processos activos» — hook + diálogo REAIS.
 *
 * Falseia só a fronteira de rede e o toast. A forma dos dados é a do
 * servidor (`{client_name, total, processos: [...]}`) e os valores do
 * fixture são diferentes das omissões.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getClientActiveProcesses: vi.fn() }));
const toast = vi.hoisted(() => ({ warning: vi.fn() }));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast }));

import useConfirmarProcessosActivos from "../useConfirmarProcessosActivos";

const COM_PROCESSOS = {
  data: {
    client_id: "c1",
    client_name: "Ana Silva",
    total: 3,
    processos: [
      { id: "p1", process_number: 412, status: "em_analise", status_label: "Em Análise Bancária", titular: "titular2", consultor_names: ["Rui Dias"] },
      { id: "p2", process_number: 380, status: "novo", status_label: "Novo", titular: "titular1", consultor_names: [] },
    ],
  },
};

let resultado;

function Harness({ clientId = "c1", opcoes }) {
  const { confirmar, dialog } = useConfirmarProcessosActivos();
  const [, forcar] = useState(0);
  return (
    <div>
      <button
        onClick={async () => {
          resultado = await confirmar(clientId, opcoes);
          forcar((n) => n + 1);
        }}
      >
        adicionar
      </button>
      {dialog}
    </div>
  );
}

const clicar = async () => {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "adicionar" }));
  });
};

describe("useConfirmarProcessosActivos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resultado = undefined;
  });

  it("sem processos activos segue em frente SEM mostrar nada", async () => {
    api.getClientActiveProcesses.mockResolvedValue({ data: { total: 0, processos: [] } });
    render(<Harness />);

    await clicar();

    await waitFor(() => expect(resultado).toBe(true));
    expect(screen.queryByTestId("active-processes-dialog")).toBeNull();
  });

  it("com processos activos mostra o aviso, nomeia os processos e a posição do cliente", async () => {
    api.getClientActiveProcesses.mockResolvedValue(COM_PROCESSOS);
    render(<Harness opcoes={{ nome: "Ana Silva" }} />);

    await clicar();

    const dialogo = await screen.findByTestId("active-processes-dialog");
    expect(dialogo.textContent).toContain("3 processos activos");
    expect(dialogo.textContent).toContain("Processo #412");
    expect(dialogo.textContent).toContain("Em Análise Bancária");
    expect(dialogo.textContent).toContain("2.º titular");
    expect(dialogo.textContent).toContain("Rui Dias");
    expect(dialogo.textContent).toContain("e mais 1.");
    // A promessa só se cumpre depois de o utilizador decidir.
    expect(resultado).toBeUndefined();
  });

  it("«Continuar mesmo assim» devolve true", async () => {
    api.getClientActiveProcesses.mockResolvedValue(COM_PROCESSOS);
    render(<Harness />);
    await clicar();

    fireEvent.click(await screen.findByRole("button", { name: /Continuar mesmo assim/ }));

    await waitFor(() => expect(resultado).toBe(true));
    await waitFor(() => expect(screen.queryByTestId("active-processes-dialog")).toBeNull());
  });

  it("«Cancelar» devolve false — e é a única forma de o fluxo parar", async () => {
    api.getClientActiveProcesses.mockResolvedValue(COM_PROCESSOS);
    render(<Harness />);
    await clicar();

    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(resultado).toBe(false));
  });

  it("passa o processo a que o cliente é adicionado, para esse não contar", async () => {
    api.getClientActiveProcesses.mockResolvedValue({ data: { total: 0, processos: [] } });
    render(<Harness clientId="c7" opcoes={{ excludeProcessId: "pP" }} />);

    await clicar();

    await waitFor(() => expect(api.getClientActiveProcesses).toHaveBeenCalledWith("c7", "pP"));
  });

  it("se a verificação FALHAR o fluxo continua — e o utilizador é avisado de que não foi verificado", async () => {
    api.getClientActiveProcesses.mockRejectedValue(new Error("rede"));
    render(<Harness />);

    await clicar();

    await waitFor(() => expect(resultado).toBe(true));
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining("Não foi possível verificar"));
    expect(screen.queryByTestId("active-processes-dialog")).toBeNull();
  });

  it("sem id de cliente não pergunta nada", async () => {
    render(<Harness clientId="" />);
    await clicar();
    await waitFor(() => expect(resultado).toBe(true));
    expect(api.getClientActiveProcesses).not.toHaveBeenCalled();
  });

  it("desmontar com a pergunta aberta resolve «cancelado» em vez de pendurar a Promise", async () => {
    api.getClientActiveProcesses.mockResolvedValue(COM_PROCESSOS);
    const { unmount } = render(<Harness />);
    await clicar();
    await screen.findByTestId("active-processes-dialog");

    unmount();

    await waitFor(() => expect(resultado).toBe(false));
  });
});
