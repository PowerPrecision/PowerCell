/**
 * D-34 — o estado de um registo financeiro de um processo fechado não é um botão.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EstadoEditavelDoRegisto from "./EstadoEditavelDoRegisto";

const montar = (props = {}) => {
  const onAlterar = vi.fn();
  render(
    <EstadoEditavelDoRegisto id="f1" tituloDoBotao="Clique para alterar para Faturado" onAlterar={onAlterar} {...props}>
      <span>Pendente</span>
    </EstadoEditavelDoRegisto>,
  );
  return { onAlterar };
};

describe("EstadoEditavelDoRegisto", () => {
  it("processo aberto: é um botão e alterar chama o handler (contraprova)", async () => {
    const { onAlterar } = montar();
    await userEvent.click(screen.getByRole("button", { name: /pendente/i }));
    expect(onAlterar).toHaveBeenCalledTimes(1);
  });

  it("processo fechado: sem botão, com o cadeado e o motivo", async () => {
    const { onAlterar } = montar({ processoFechado: true });
    expect(screen.queryByRole("button")).toBeNull();
    const fechado = screen.getByTestId("financa-fechada-f1");
    expect(fechado).toHaveAttribute("title", expect.stringMatching(/reabra/i));
    expect(fechado).toHaveTextContent("Pendente");
    await userEvent.click(fechado);
    expect(onAlterar).not.toHaveBeenCalled();
  });
});
