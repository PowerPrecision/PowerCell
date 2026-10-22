/**
 * O visualizador do «Ver documento»: a navegação reinicia quando a linha muda (Out 2026).
 *
 * Fechar e abrir desmonta o conteúdo de qualquer maneira; o caso que só este teste apanha é a lista
 * mudar COM o diálogo aberto — sem a chave por ids, o «Documento 2 de 3» da linha anterior ficava
 * preso e o utilizador via o 2.º documento de uma linha que nem escolheu.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/api", () => ({
  getIndexDocumentContent: vi.fn(async () => ({ data: new Blob(["x"], { type: "application/pdf" }), headers: { "content-type": "application/pdf" } })),
  readBlobErrorBody: vi.fn(async () => null),
}));

import { getIndexDocumentContent } from "../../services/api";
import VisualizadorDeDocumento from "./VisualizadorDeDocumento";

const LINHA_A = [{ id: "a1", rotulo: "A1" }, { id: "a2", rotulo: "A2" }, { id: "a3", rotulo: "A3" }];
const LINHA_B = [{ id: "b1", rotulo: "B1" }, { id: "b2", rotulo: "B2" }];

afterEach(() => vi.clearAllMocks());

describe("VisualizadorDeDocumento", () => {
  it("outra linha com o diálogo aberto recomeça no 1.º documento", async () => {
    const utilizador = userEvent.setup();
    const { rerender } = render(<VisualizadorDeDocumento documentos={LINHA_A} onFechar={() => {}} />);
    await utilizador.click(screen.getByRole("button", { name: "Documento seguinte" }));
    expect(screen.getByTestId("visualizador-posicao")).toHaveTextContent("Documento 2 de 3");

    rerender(<VisualizadorDeDocumento documentos={LINHA_B} onFechar={() => {}} />);
    expect(screen.getByTestId("visualizador-posicao")).toHaveTextContent("Documento 1 de 2");
    await vi.waitFor(() => expect(getIndexDocumentContent).toHaveBeenLastCalledWith("b1"));
  });

  it("contraprova: a mesma linha mantém o sítio onde estava", async () => {
    const utilizador = userEvent.setup();
    const { rerender } = render(<VisualizadorDeDocumento documentos={LINHA_A} onFechar={() => {}} />);
    await utilizador.click(screen.getByRole("button", { name: "Documento seguinte" }));
    rerender(<VisualizadorDeDocumento documentos={[...LINHA_A]} onFechar={() => {}} />);
    expect(screen.getByTestId("visualizador-posicao")).toHaveTextContent("Documento 2 de 3");
  });

  it("sem documentos está fechado", () => {
    render(<VisualizadorDeDocumento documentos={[]} onFechar={() => {}} />);
    expect(screen.queryByTestId("visualizador-corpo")).toBeNull();
  });
});
