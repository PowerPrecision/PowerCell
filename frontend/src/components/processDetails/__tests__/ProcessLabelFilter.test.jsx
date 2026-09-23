/**
 * O filtro por etiquetas — ponto 15 (Lote 5, Secção B).
 *
 * Partilhado pela Lista de Processos e pelo Kanban. No backend são
 * construtores de query SEPARADOS (foi assim que o quadro ficou de fora
 * do isolamento no Lote 4); do lado do utilizador a pergunta é a mesma,
 * e um filtro que só existisse num dos ecrãs era metade da resposta.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ProcessLabelFilter from "../ProcessLabelFilter";

describe("ProcessLabelFilter — quando não há nada a filtrar", () => {
  it("sem etiquetas em uso não renderiza nada", () => {
    // Um dropdown vazio é um convite a um clique que não faz nada.
    const { container } = render(<ProcessLabelFilter disponiveis={[]} onChange={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("mas aparece se houver um filtro activo sem catálogo", () => {
    // O catálogo pode falhar (a base em baixo devolve lista vazia de
    // propósito) — esconder o filtro deixaria o utilizador com uma
    // listagem filtrada sem forma de a desfiltrar.
    const { container } = render(
      <ProcessLabelFilter disponiveis={[]} seleccionadas={["VIP"]} onChange={vi.fn()} />,
    );
    expect(container.firstChild).not.toBeNull();
  });
});

describe("ProcessLabelFilter — escolher", () => {
  it("seleccionar uma etiqueta devolve-a ao contentor", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProcessLabelFilter disponiveis={["VIP", "Sub 35"]} onChange={onChange} />);

    await user.click(screen.getByTestId("filtro-etiquetas"));
    await user.click(screen.getByRole("checkbox", { name: "Sub 35" }));

    expect(onChange).toHaveBeenCalledWith(["Sub 35"]);
  });

  it("clicar numa etiqueta já activa tira-a", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ProcessLabelFilter
        disponiveis={["VIP", "Sub 35"]}
        seleccionadas={["VIP"]}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByTestId("filtro-etiquetas"));
    await user.click(screen.getByRole("checkbox", { name: "VIP" }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("o crachá de um filtro activo tem botão para o remover", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ProcessLabelFilter disponiveis={["VIP"]} seleccionadas={["VIP"]} onChange={onChange} />,
    );

    await user.click(screen.getByRole("button", { name: "Remover filtro VIP" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("limpar desfaz todos os filtros de uma vez", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ProcessLabelFilter
        disponiveis={["VIP", "Sub 35"]}
        seleccionadas={["VIP", "Sub 35"]}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Limpar" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

describe("ProcessLabelFilter — AND vs OR", () => {
  it("com uma só etiqueta não pergunta a lógica", async () => {
    // "Corresponder a todas" de uma etiqueta é a mesma coisa que
    // "qualquer uma": a escolha não significa nada e só confunde.
    const user = userEvent.setup();
    render(
      <ProcessLabelFilter
        disponiveis={["VIP", "Sub 35"]}
        seleccionadas={["VIP"]}
        onChange={vi.fn()}
        onLogicaChange={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId("filtro-etiquetas"));
    expect(screen.queryByTestId("alternar-logica-etiquetas")).toBeNull();
  });

  it("com duas etiquetas deixa alternar entre todas e qualquer uma", async () => {
    const user = userEvent.setup();
    const onLogicaChange = vi.fn();
    render(
      <ProcessLabelFilter
        disponiveis={["VIP", "Sub 35"]}
        seleccionadas={["VIP", "Sub 35"]}
        onChange={vi.fn()}
        logica="OR"
        onLogicaChange={onLogicaChange}
      />,
    );

    await user.click(screen.getByTestId("filtro-etiquetas"));
    await user.click(screen.getByTestId("alternar-logica-etiquetas"));

    expect(onLogicaChange).toHaveBeenCalledWith("AND");
  });

  it("o botão diz o que está em vigor, não o que vai fazer", async () => {
    const user = userEvent.setup();
    render(
      <ProcessLabelFilter
        disponiveis={["VIP", "Sub 35"]}
        seleccionadas={["VIP", "Sub 35"]}
        onChange={vi.fn()}
        logica="AND"
        onLogicaChange={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId("filtro-etiquetas"));
    expect(screen.getByTestId("alternar-logica-etiquetas").textContent).toBe("todas");
  });
});
