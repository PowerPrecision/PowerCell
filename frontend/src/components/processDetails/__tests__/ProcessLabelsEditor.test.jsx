/**
 * O editor de etiquetas — ponto 15 (Lote 5, Secção B).
 *
 * O módulo puro (`utils/processLabels.test.js`) prova as regras; este
 * prova que o componente as usa e que o consultor consegue mesmo pôr e
 * tirar etiquetas — que é o que não existia: o `labels` estava no
 * modelo, os crachás eram renderizados, e não havia forma nenhuma de os
 * editar sem chamar a API à mão.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ProcessLabelsEditor from "../ProcessLabelsEditor";

const abrir = async (user) =>
  user.click(screen.getByTestId("abrir-etiquetas"));

describe("ProcessLabelsEditor — em repouso", () => {
  it("mostra as etiquetas do processo", () => {
    render(<ProcessLabelsEditor labels={["VIP", "Sub 35"]} onChange={vi.fn()} />);
    expect(screen.getAllByTestId("etiqueta-processo").map((n) => n.textContent)).toEqual([
      "VIP",
      "Sub 35",
    ]);
  });

  it("sem permissão de edição não oferece o botão", () => {
    // Um botão que abre um diálogo cuja gravação vai ser recusada é pior
    // do que não haver botão.
    render(<ProcessLabelsEditor labels={["VIP"]} onChange={vi.fn()} disabled />);
    expect(screen.queryByTestId("abrir-etiquetas")).toBeNull();
    expect(screen.getAllByTestId("etiqueta-processo")).toHaveLength(1);
  });

  it("um processo sem etiquetas continua a oferecer o botão", () => {
    render(<ProcessLabelsEditor labels={[]} onChange={vi.fn()} />);
    expect(screen.getByTestId("abrir-etiquetas")).toBeTruthy();
  });
});

describe("ProcessLabelsEditor — acrescentar", () => {
  it("acrescenta uma etiqueta e devolve a lista ao contentor", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProcessLabelsEditor labels={["VIP"]} onChange={onChange} />);

    await abrir(user);
    await user.type(screen.getByLabelText("Nova etiqueta"), "Sub 35");
    await user.click(screen.getByRole("button", { name: "Adicionar" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(["VIP", "Sub 35"]));
  });

  it("diz porquê quando recusa uma etiqueta repetida", async () => {
    // Um botão que não faz nada e não explica é o silêncio do Bug 1
    // outra vez, noutro sítio.
    const user = userEvent.setup();
    render(<ProcessLabelsEditor labels={["VIP"]} onChange={vi.fn()} />);

    await abrir(user);
    await user.type(screen.getByLabelText("Nova etiqueta"), "vip");
    await user.click(screen.getByRole("button", { name: "Adicionar" }));

    expect(screen.getByRole("alert").textContent).toContain("já está");
  });

  it("não sugere etiquetas que já estão no processo", async () => {
    const user = userEvent.setup();
    render(
      <ProcessLabelsEditor labels={["VIP"]} sugestoes={["VIP", "Urgente"]} onChange={vi.fn()} />,
    );

    await abrir(user);
    // O Dialog do Radix renderiza num PORTAL — o `container` do render
    // só tem o gatilho, por isso a consulta tem de ser no documento.
    const opcoes = [...document.querySelectorAll("datalist option")].map((o) => o.value);
    expect(opcoes).toEqual(["Urgente"]);
  });
});

describe("ProcessLabelsEditor — remover", () => {
  it("remove uma etiqueta", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProcessLabelsEditor labels={["VIP", "Sub 35"]} onChange={onChange} />);

    await abrir(user);
    await user.click(screen.getByRole("button", { name: "Remover etiqueta VIP" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(["Sub 35"]));
  });

  it("limpar todas as etiquetas envia uma lista VAZIA", async () => {
    // O caso que o `sanitizeProcessUpdatePayload` trata de propósito
    // (`allowEmptyArrays: ["labels"]`): sem isto, tirar a última
    // etiqueta não gravava nada e ela voltava no próximo refresh.
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProcessLabelsEditor labels={["VIP"]} onChange={onChange} />);

    await abrir(user);
    await user.click(screen.getByRole("button", { name: "Remover etiqueta VIP" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith([]));
  });
});

describe("ProcessLabelsEditor — cancelar", () => {
  it("cancelar não grava nada", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProcessLabelsEditor labels={["VIP"]} onChange={onChange} />);

    await abrir(user);
    await user.click(screen.getByRole("button", { name: "Remover etiqueta VIP" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onChange).not.toHaveBeenCalled();
  });

  it("reabrir parte do que está gravado, não do rascunho abandonado", async () => {
    const user = userEvent.setup();
    render(<ProcessLabelsEditor labels={["VIP"]} onChange={vi.fn()} />);

    await abrir(user);
    await user.click(screen.getByRole("button", { name: "Remover etiqueta VIP" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    await abrir(user);

    // Um rascunho abandonado não pode reaparecer como se tivesse sido aceite.
    expect(screen.getByRole("button", { name: "Remover etiqueta VIP" })).toBeTruthy();
  });
});
