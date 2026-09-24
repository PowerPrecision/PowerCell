import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProcessNavigator from "../ProcessNavigator";

function montar(props = {}) {
  const onNavegar = vi.fn();
  render(
    <ProcessNavigator
      anteriorId="p1"
      seguinteId="p3"
      posicao={12}
      total={348}
      onNavegar={onNavegar}
      {...props}
    />,
  );
  return { onNavegar };
}

describe("ProcessNavigator", () => {
  it("mostra a posição no conjunto filtrado inteiro", () => {
    montar();
    expect(screen.getByTestId("posicao-na-lista")).toHaveTextContent("12 / 348");
  });

  it("navega para o anterior e para o seguinte", async () => {
    const user = userEvent.setup();
    const { onNavegar } = montar();
    await user.click(screen.getByRole("button", { name: "Processo anterior" }));
    expect(onNavegar).toHaveBeenCalledWith("p1");
    await user.click(screen.getByRole("button", { name: "Processo seguinte" }));
    expect(onNavegar).toHaveBeenCalledWith("p3");
  });

  it("desactiva — sem esconder — o lado que não tem vizinho", () => {
    // Esconder o botão faria o controlo saltar de sítio no primeiro e
    // no último processo, e o utilizador perderia o alvo do rato.
    montar({ anteriorId: null });
    expect(screen.getByRole("button", { name: "Processo anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Processo seguinte" })).toBeEnabled();
  });

  it("não chama onNavegar quando o lado está desactivado", async () => {
    const user = userEvent.setup();
    const { onNavegar } = montar({ seguinteId: null });
    await user.click(screen.getByRole("button", { name: "Processo seguinte" }));
    expect(onNavegar).not.toHaveBeenCalled();
  });

  it("trava os dois lados enquanto pergunta ao servidor", () => {
    montar({ aCarregar: true });
    expect(screen.getByRole("button", { name: "Processo anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Processo seguinte" })).toBeDisabled();
    expect(screen.getByLabelText("A procurar")).toBeInTheDocument();
  });

  it("não mostra posição nenhuma quando ainda não a sabe", () => {
    // Melhor um espaço vazio do que "null / 0" ou "1 / 1" inventado.
    montar({ posicao: null, total: 0 });
    expect(screen.getByTestId("posicao-na-lista")).toHaveTextContent("");
  });
});
