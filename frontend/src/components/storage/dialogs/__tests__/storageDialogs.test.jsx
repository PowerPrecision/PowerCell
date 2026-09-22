/**
 * Testes dos diálogos do gestor de ficheiros (Épico 8, Eixo 2).
 *
 * Num só ficheiro por serem pequenos, coesos e testados da mesma maneira:
 * todos são de apresentação, todos devolvem intenções e nenhum guarda
 * estado do contentor. Os dois maiores — `AIResultsDialog` e
 * `UploadConflictDialog` — têm ficheiro próprio.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import BulkDeleteDialog from "../BulkDeleteDialog";
import DeleteFileDialog from "../DeleteFileDialog";
import EmpresaNifDialog from "../EmpresaNifDialog";
import GenerateTemplateDialog from "../GenerateTemplateDialog";
import ManualRenameDialog from "../ManualRenameDialog";
import MoveConflictDialog from "../MoveConflictDialog";
import OrganizeResultsDialog from "../OrganizeResultsDialog";
import SmartRenameResultsDialog from "../SmartRenameResultsDialog";

// ====================================================================

describe("DeleteFileDialog", () => {
  const props = (o = {}) => ({
    open: true,
    fileName: "irs_2025.pdf",
    deleting: false,
    onOpenChange: vi.fn(),
    onConfirm: vi.fn(),
    ...o,
  });

  it("nomeia o ficheiro que vai ser eliminado", () => {
    // Confirmar uma eliminação sem saber de quê é um convite ao engano.
    render(<DeleteFileDialog {...props()} />);

    expect(screen.getByText(/irs_2025\.pdf/)).toBeInTheDocument();
  });

  it("avisa que a acção não é reversível", () => {
    render(<DeleteFileDialog {...props()} />);

    expect(screen.getByText(/não pode ser revertida/i)).toBeInTheDocument();
  });

  it("confirmar avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onConfirm = vi.fn();
    render(<DeleteFileDialog {...props({ onConfirm })} />);

    await utilizador.click(screen.getByRole("button", { name: "Eliminar" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("a eliminar, os botões bloqueiam", () => {
    render(<DeleteFileDialog {...props({ deleting: true })} />);

    expect(screen.getByRole("button", { name: /Eliminar/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
  });
});

describe("BulkDeleteDialog", () => {
  const props = (o = {}) => ({
    open: true,
    count: 3,
    deleting: false,
    onOpenChange: vi.fn(),
    onConfirm: vi.fn(),
    ...o,
  });

  it("diz quantos ficheiros vão ser eliminados", () => {
    render(<BulkDeleteDialog {...props()} />);

    // O texto aparece no título E no botão; o título é o que informa.
    expect(screen.getByRole("heading", { name: /Eliminar 3 ficheiro/ })).toBeInTheDocument();
  });

  it("confirmar avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onConfirm = vi.fn();
    render(<BulkDeleteDialog {...props({ onConfirm })} />);

    await utilizador.click(screen.getByRole("button", { name: /Eliminar 3/ }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("a eliminar, mostra o progresso e tranca o fecho", async () => {
    // O `preventDefault` no confirmar existe para o Radix não fechar o
    // diálogo antes de a eliminação acabar.
    const utilizador = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<BulkDeleteDialog {...props({ deleting: true, onOpenChange })} />);

    expect(screen.getByText(/A eliminar/)).toBeInTheDocument();
    await utilizador.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});

describe("ManualRenameDialog", () => {
  const props = (o = {}) => ({
    open: true,
    fileName: "documento.pdf",
    newName: "",
    renaming: false,
    onOpenChange: vi.fn(),
    onNameChange: vi.fn(),
    onConfirm: vi.fn(),
    ...o,
  });

  it("é controlado: o valor vem das props", () => {
    render(<ManualRenameDialog {...props({ newName: "novo nome" })} />);

    expect(screen.getByDisplayValue("novo nome")).toBeInTheDocument();
  });

  it("escrever avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onNameChange = vi.fn();
    render(<ManualRenameDialog {...props({ onNameChange })} />);

    await utilizador.type(screen.getByPlaceholderText(/novo nome/i), "x");

    expect(onNameChange).toHaveBeenCalledWith("x");
  });

  it("com o nome vazio, renomear está bloqueado", () => {
    // Renomear para "" apagaria o nome do ficheiro no S3.
    render(<ManualRenameDialog {...props()} />);

    expect(screen.getByRole("button", { name: /Renomear/ })).toBeDisabled();
  });

  it("só com espaços continua bloqueado", () => {
    render(<ManualRenameDialog {...props({ newName: "   " })} />);

    expect(screen.getByRole("button", { name: /Renomear/ })).toBeDisabled();
  });

  it("Enter confirma quando há nome", async () => {
    const utilizador = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ManualRenameDialog {...props({ newName: "valido", onConfirm })} />);

    await utilizador.type(screen.getByDisplayValue("valido"), "{Enter}");

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("Enter com o nome vazio não confirma", async () => {
    const utilizador = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ManualRenameDialog {...props({ onConfirm })} />);

    await utilizador.type(screen.getByPlaceholderText(/novo nome/i), "{Enter}");

    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("SmartRenameResultsDialog", () => {
  const resultados = { total: 5, renamed: 3, skipped: 1, errors: 1, details: [] };

  it("fechado não rende nada", () => {
    render(<SmartRenameResultsDialog open={false} results={resultados} onOpenChange={vi.fn()} />);

    expect(screen.queryByText("Renomeação Inteligente")).not.toBeInTheDocument();
  });

  it("mostra o resumo dos números", () => {
    render(<SmartRenameResultsDialog open results={resultados} onOpenChange={vi.fn()} />);

    expect(screen.getByText("Renomeação Inteligente")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("sem resultados não rebenta", () => {
    render(<SmartRenameResultsDialog open results={null} onOpenChange={vi.fn()} />);

    expect(screen.getByText("Renomeação Inteligente")).toBeInTheDocument();
  });
});

describe("OrganizeResultsDialog", () => {
  it("sem resultados fica fechado", () => {
    // O `open` é derivado de `results`: `null` é o estado fechado.
    render(<OrganizeResultsDialog results={null} onClose={vi.fn()} />);

    expect(screen.queryByText("Organização Completa")).not.toBeInTheDocument();
  });

  it("com resultados abre e mostra os números", () => {
    render(
      <OrganizeResultsDialog
        results={{ analyzed: 4, organized: 3, categories: [], details: [] }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Organização Completa")).toBeInTheDocument();
  });

  it("Fechar avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onClose = vi.fn();
    render(
      <OrganizeResultsDialog
        results={{ analyzed: 1, organized: 1, categories: [], details: [] }}
        onClose={onClose}
      />,
    );

    await utilizador.click(screen.getByRole("button", { name: "Fechar" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("GenerateTemplateDialog", () => {
  const props = (o = {}) => ({
    open: true,
    templates: [{ id: "cpcv", label: "CPCV" }],
    selectedTemplate: "",
    error: null,
    generating: false,
    onOpenChange: vi.fn(),
    onTemplateChange: vi.fn(),
    onGenerate: vi.fn(),
    ...o,
  });

  it("sem tipo escolhido, gerar está bloqueado", () => {
    render(<GenerateTemplateDialog {...props()} />);

    expect(screen.getByRole("button", { name: /Gerar e Descarregar/ })).toBeDisabled();
  });

  it("com tipo escolhido, gerar liberta", () => {
    render(<GenerateTemplateDialog {...props({ selectedTemplate: "cpcv" })} />);

    expect(screen.getByRole("button", { name: /Gerar e Descarregar/ })).toBeEnabled();
  });

  it("mostra os campos em falta que o servidor devolveu", () => {
    // Estes campos chegam num corpo de erro que vem como Blob; perdê-los
    // deixaria o utilizador sem saber o que preencher.
    render(
      <GenerateTemplateDialog
        {...props({
          error: { message: "Dados incompletos", missingFields: ["NIF do titular"] },
        })}
      />,
    );

    expect(screen.getByText("Dados incompletos")).toBeInTheDocument();
    expect(screen.getByText(/NIF do titular/)).toBeInTheDocument();
  });

  it("a gerar, o botão bloqueia", () => {
    render(<GenerateTemplateDialog {...props({ selectedTemplate: "cpcv", generating: true })} />);

    expect(screen.getByRole("button", { name: /Gerar e Descarregar/ })).toBeDisabled();
  });
});

describe("MoveConflictDialog", () => {
  const props = (o = {}) => ({
    open: true,
    conflicts: [{ conflictFilename: "irs.pdf", file: { name: "irs.pdf" } }],
    targetCategory: "Financeiros",
    onDecide: vi.fn(),
    onDecideForAll: vi.fn(),
    onCancel: vi.fn(),
    ...o,
  });

  it("nomeia o ficheiro e a pasta de destino", () => {
    render(<MoveConflictDialog {...props()} />);

    expect(screen.getByText("irs.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Financeiros/)).toBeInTheDocument();
  });

  it("ignorar devolve a decisão ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onDecide = vi.fn();
    render(<MoveConflictDialog {...props({ onDecide })} />);

    await utilizador.click(screen.getByRole("button", { name: /Ignorar Este/ }));

    expect(onDecide).toHaveBeenCalledWith("skip");
  });

  it("com um só conflito não oferece 'para todos'", () => {
    // Oferecer "renomear todos" para um único ficheiro é ruído.
    render(<MoveConflictDialog {...props()} />);

    expect(screen.queryByRole("button", { name: /Renomear Todos/ })).not.toBeInTheDocument();
  });

  it("com vários conflitos oferece 'para todos'", async () => {
    const utilizador = userEvent.setup();
    const onDecideForAll = vi.fn();
    render(
      <MoveConflictDialog
        {...props({
          conflicts: [
            { conflictFilename: "a.pdf", file: { name: "a.pdf" } },
            { conflictFilename: "b.pdf", file: { name: "b.pdf" } },
          ],
          onDecideForAll,
        })}
      />,
    );

    await utilizador.click(screen.getByRole("button", { name: /Renomear Todos/ }));

    expect(onDecideForAll).toHaveBeenCalledWith("rename");
  });
});

describe("EmpresaNifDialog", () => {
  const props = (o = {}) => ({
    open: true,
    files: [new File([""], "doc.pdf")],
    nif: "",
    checking: false,
    existingProcesses: null,
    contrastColorOf: () => "#000",
    onNifChange: vi.fn(),
    onVerify: vi.fn(),
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    ...o,
  });

  it("com o NIF incompleto, verificar está bloqueado", () => {
    render(<EmpresaNifDialog {...props({ nif: "5091" })} />);

    expect(screen.getByRole("button", { name: "Verificar NIF" })).toBeDisabled();
  });

  it("com 9 dígitos, verificar liberta", () => {
    render(<EmpresaNifDialog {...props({ nif: "509123456" })} />);

    expect(screen.getByRole("button", { name: "Verificar NIF" })).toBeEnabled();
  });

  it("com o NIF incompleto, confirmar upload está bloqueado", () => {
    // Carregar sem empresa identificada põe documentos no processo errado.
    render(<EmpresaNifDialog {...props({ nif: "12" })} />);

    expect(screen.getByRole("button", { name: /Confirmar Upload/ })).toBeDisabled();
  });

  it("com 9 dígitos, confirmar upload liberta", () => {
    render(<EmpresaNifDialog {...props({ nif: "509123456" })} />);

    expect(screen.getByRole("button", { name: /Confirmar Upload/ })).toBeEnabled();
  });

  it("escrever avisa o contentor só com dígitos", async () => {
    const utilizador = userEvent.setup();
    const onNifChange = vi.fn();
    render(<EmpresaNifDialog {...props({ onNifChange })} />);

    await utilizador.type(screen.getByPlaceholderText(/509123456/), "5a");

    // O campo é controlado e as props não mudam durante o teste, pelo que
    // cada tecla é enviada isolada: o dígito passa, a letra é filtrada.
    expect(onNifChange).toHaveBeenCalledWith("5");
    expect(onNifChange).toHaveBeenLastCalledWith("");
  });

  it("Cancelar avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onCancel = vi.fn();
    render(<EmpresaNifDialog {...props({ onCancel })} />);

    await utilizador.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
