import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ArquivarNoProcessoDialog from "../ArquivarNoProcessoDialog";

const POR_INDEXAR = {
  process_id: "p-1",
  process_number: 42,
  client_name: "Joana Valente",
  status_label: "Em análise",
  motivo: "endereço do titular",
  ja_indexado: false,
};
const INDEXADO = {
  process_id: "p-2",
  process_number: 77,
  client_name: "Joana Valente M.",
  status_label: "Em aprovação",
  motivo: "endereço monitorizado",
  ja_indexado: true,
};

function montar(props = {}) {
  const onConfirmar = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ArquivarNoProcessoDialog
      open
      onOpenChange={onOpenChange}
      nomeDoAnexo="cc.pdf"
      estado="pronto"
      resposta={{ enderecos: ["joana@x.pt"], sugestoes: [POR_INDEXAR], sugerido: "p-1", ambiguo: false }}
      onConfirmar={onConfirmar}
      {...props}
    />,
  );
  return { onConfirmar, onOpenChange };
}

describe("ArquivarNoProcessoDialog", () => {
  it("um só processo vem pré-seleccionado e arquiva sem mais cliques", async () => {
    const { onConfirmar } = montar();
    const radio = screen.getByRole("radio", { name: /#42 · Joana Valente/ });
    expect(radio).toBeChecked();

    await userEvent.click(screen.getByTestId("arquivar-confirmar"));
    expect(onConfirmar).toHaveBeenCalledWith({ processId: "p-1", category: "Outros" });
  });

  it("processo por indexar: avisa da pasta Index e NÃO pergunta a pasta", () => {
    montar();
    expect(screen.getByRole("note")).toHaveTextContent(/pasta Index/);
    expect(screen.queryByLabelText("Pasta de destino")).not.toBeInTheDocument();
  });

  it("vários processos: nenhum pré-seleccionado e o botão fica desligado", () => {
    montar({
      resposta: { enderecos: [], sugestoes: [POR_INDEXAR, INDEXADO], sugerido: null, ambiguo: true },
    });
    expect(screen.getByText(/mais do que um processo activo/)).toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) expect(radio).not.toBeChecked();
    expect(screen.getByTestId("arquivar-confirmar")).toBeDisabled();
  });

  it("escolher um processo indexado mostra a pasta e avisa que não há IA", async () => {
    const { onConfirmar } = montar({
      resposta: { enderecos: [], sugestoes: [POR_INDEXAR, INDEXADO], sugerido: null, ambiguo: true },
    });
    await userEvent.click(screen.getByRole("radio", { name: /#77/ }));

    expect(screen.getByRole("note")).toHaveTextContent(/sem passar pela IA/);
    expect(screen.getByLabelText("Pasta de destino")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("arquivar-confirmar"));
    expect(onConfirmar).toHaveBeenCalledWith({ processId: "p-2", category: "Outros" });
  });

  it("sem processos diz o que fazer a seguir", () => {
    montar({ resposta: { enderecos: ["joana@x.pt"], sugestoes: [], sugerido: null } });
    const vazio = screen.getByTestId("arquivar-sem-processo");
    expect(within(vazio).getByText(/joana@x.pt/)).toBeInTheDocument();
    expect(within(vazio).getByText(/Ligar a processo/)).toBeInTheDocument();
    expect(screen.getByTestId("arquivar-confirmar")).toBeDisabled();
  });

  it("a carregar: estado de espera e botão desligado", () => {
    montar({ estado: "a_carregar", resposta: null });
    expect(screen.getByRole("status", { name: /a procurar/i })).toBeInTheDocument();
    expect(screen.getByTestId("arquivar-confirmar")).toBeDisabled();
  });

  it("erro: mostra a mensagem e deixa tentar de novo", async () => {
    const onTentarDeNovo = vi.fn();
    montar({ estado: "erro", resposta: null, erro: "Servidor em baixo", onTentarDeNovo });
    expect(screen.getByRole("alert")).toHaveTextContent("Servidor em baixo");
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(onTentarDeNovo).toHaveBeenCalled();
  });

  it("a arquivar: não deixa confirmar duas vezes nem cancelar", () => {
    montar({ arquivando: true });
    expect(screen.getByTestId("arquivar-confirmar")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
  });

  it.each([undefined, null, {}, { sugestoes: {} }])(
    "uma resposta sem a forma esperada (%j) não rebenta",
    (resposta) => {
      montar({ resposta });
      expect(screen.getByTestId("arquivar-sem-processo")).toBeInTheDocument();
    },
  );
});
