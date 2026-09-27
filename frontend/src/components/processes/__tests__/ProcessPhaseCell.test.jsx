/**
 * Ponto 16 — a célula editável da fase na listagem.
 *
 * O teste que mais interessa aqui é o do `stopPropagation`: a linha
 * inteira da tabela tem um `onClick` que navega para os Detalhes. Sem o
 * travão, abrir o dropdown levava o utilizador para outra página antes
 * de ele chegar a escolher a fase — a funcionalidade seria impossível
 * de usar e nada no código diria porquê.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProcessPhaseCell from "../ProcessPhaseCell";

const MOTOR = [
  { name: "clientes_espera", label: "Clientes em Espera", color: "blue", order: 0 },
  { name: "fase_bancaria", label: "Fase Bancária", color: "orange", order: 1 },
  { name: "cpcv", label: "CPCV", color: "green", order: 2 },
];

function montar(props = {}) {
  const onChange = props.onChange || vi.fn();
  const utils = render(
    <ProcessPhaseCell
      status="fase_bancaria"
      role="consultor"
      workflowStatuses={MOTOR}
      onChange={onChange}
      {...props}
    />,
  );
  return { ...utils, onChange };
}

describe("ProcessPhaseCell", () => {
  beforeEach(() => vi.clearAllMocks());

  it("mostra a fase actual como valor seleccionado", () => {
    montar();
    expect(
      screen.getByRole("combobox", { name: /fase do processo/i }),
    ).toHaveTextContent("Fase Bancária");
  });

  it("não deixa o clique chegar à linha da tabela", async () => {
    // A linha navega para os Detalhes no onClick. Se o clique no
    // dropdown subisse, o utilizador saía da página ao tentar editar.
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    render(
      <table><tbody>
        <tr onClick={onRowClick}>
          <td>
            <ProcessPhaseCell
              status="fase_bancaria"
              role="consultor"
              workflowStatuses={MOTOR}
              onChange={vi.fn()}
            />
          </td>
        </tr>
      </tbody></table>,
    );
    await user.click(screen.getByRole("combobox", { name: /fase do processo/i }));
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("chama onChange com o nome da fase escolhida", async () => {
    const user = userEvent.setup();
    const { onChange } = montar();
    await user.click(screen.getByRole("combobox", { name: /fase do processo/i }));
    await user.click(await screen.findByRole("option", { name: /CPCV/i }));
    expect(onChange).toHaveBeenCalledWith("cpcv");
  });

  it("o Radix não reemite a fase já seleccionada (a regra é do util)", async () => {
    // Este teste documenta a BIBLIOTECA, não o produto: o Radix não
    // dispara `onValueChange` para o item já seleccionado, por isso
    // passa mesmo sem o guarda. A regra de não gravar duas vezes a
    // mesma fase é testada de frente em `inlinePhaseEdit.test.js`
    // (`deveGravarNovaFase`) — foi uma mutação sobrevivente que o
    // mostrou.
    const user = userEvent.setup();
    const { onChange } = montar();
    await user.click(screen.getByRole("combobox", { name: /fase do processo/i }));
    await user.click(await screen.findByRole("option", { name: /Fase Bancária/i }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("mostra um crachá não editável a quem não pode mudar a fase", () => {
    montar({ role: "indexacao" });
    expect(
      screen.queryByRole("combobox", { name: /fase do processo/i }),
    ).toBeNull();
    expect(screen.getByText("Fase Bancária")).toBeInTheDocument();
  });

  it("mostra um crachá não editável num estado terminal", () => {
    montar({ role: "consultor", status: "concluido" });
    expect(
      screen.queryByRole("combobox", { name: /fase do processo/i }),
    ).toBeNull();
  });

  it("mostra 'Eliminado' e nunca o dropdown num processo eliminado", () => {
    montar({ role: "admin", isDeleted: true });
    expect(screen.getByTestId("fase-eliminado")).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: /fase do processo/i }),
    ).toBeNull();
  });

  it("desactiva o dropdown enquanto grava", () => {
    montar({ saving: true });
    expect(
      screen.getByRole("combobox", { name: /fase do processo/i }),
    ).toBeDisabled();
  });

  it("mostra a fase legada que o motor já não conhece", () => {
    montar({ status: "escriturado" });
    expect(
      screen.getByRole("combobox", { name: /fase do processo/i }),
    ).toHaveTextContent("escriturado");
  });
});
