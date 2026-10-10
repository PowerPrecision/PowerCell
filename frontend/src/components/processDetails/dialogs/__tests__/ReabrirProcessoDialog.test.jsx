import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ReabrirProcessoDialog from "../ReabrirProcessoDialog";

const FASES = [
  { name: "novo", label: "Novo" },
  { name: "cpcv", label: "CPCV" },
];

function montar(props = {}) {
  const onConfirmar = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ReabrirProcessoDialog
      open
      onOpenChange={onOpenChange}
      fases={FASES}
      onConfirmar={onConfirmar}
      {...props}
    />,
  );
  return { onConfirmar, onOpenChange };
}

describe("ReabrirProcessoDialog", () => {
  it("não deixa confirmar sem escolher a fase", () => {
    montar();
    expect(screen.getByTestId("reabrir-confirmar")).toBeDisabled();
  });

  it("confirma com a fase escolhida", async () => {
    const { onConfirmar } = montar();
    await userEvent.click(screen.getByTestId("reabrir-fase-select"));
    await userEvent.click(await screen.findByRole("option", { name: "CPCV" }));
    await userEvent.click(screen.getByTestId("reabrir-confirmar"));
    expect(onConfirmar).toHaveBeenCalledWith("cpcv");
  });

  it("enquanto reabre, nada se pode voltar a carregar", () => {
    montar({ aReabrir: true });
    expect(screen.getByTestId("reabrir-confirmar")).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancelar/i })).toBeDisabled();
  });

  it("sem fases activas diz-se, e não há o que confirmar", () => {
    montar({ fases: [] });
    expect(screen.getByTestId("reabrir-sem-fases")).toBeInTheDocument();
    expect(screen.getByTestId("reabrir-confirmar")).toBeDisabled();
  });

  it("uma lista inválida não rebenta", () => {
    montar({ fases: null });
    expect(screen.getByTestId("reabrir-sem-fases")).toBeInTheDocument();
  });

  it("cada abertura começa sem fase escolhida", async () => {
    const props = { onOpenChange: () => {}, fases: FASES, onConfirmar: () => {} };
    const { rerender } = render(<ReabrirProcessoDialog open {...props} />);
    await userEvent.click(screen.getByTestId("reabrir-fase-select"));
    await userEvent.click(await screen.findByRole("option", { name: "Novo" }));
    expect(screen.getByTestId("reabrir-confirmar")).toBeEnabled();

    rerender(<ReabrirProcessoDialog open={false} {...props} />);
    rerender(<ReabrirProcessoDialog open {...props} />);
    expect(screen.getByTestId("reabrir-confirmar")).toBeDisabled();
  });
});
