/**
 * Teste de fumo do compositor (Épico 6, eixo 4).
 *
 * Âmbito: prova que é um componente CONTROLADO — escrever num campo avisa o
 * contentor em vez de guardar estado próprio — e que o envio, o cancelar e
 * os anexos passam pelos callbacks certos.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import EmailComposer from "../EmailComposer";

const rascunho = (overrides = {}) => ({
  to_emails: "",
  cc_emails: "",
  bcc_emails: "",
  subject: "",
  body: "",
  account: "personal",
  ...overrides,
});

const props = (overrides = {}) => ({
  open: true,
  data: rascunho(),
  sending: false,
  ccExpanded: false,
  bccExpanded: false,
  attachments: [],
  uploading: false,
  onOpenChange: vi.fn(),
  onFieldChange: vi.fn(),
  onToggleCc: vi.fn(),
  onToggleBcc: vi.fn(),
  onSend: vi.fn(),
  onCancel: vi.fn(),
  onUploadFiles: vi.fn(),
  onRemoveAttachment: vi.fn(),
  canUseGlobalAccounts: false,
  effectiveRole: "consultor",
  resolvedSignature: "",
  ...overrides,
});

describe("EmailComposer — abertura", () => {
  it("fechado não rende nada", () => {
    render(<EmailComposer {...props({ open: false })} />);

    expect(screen.queryByText("Nova Mensagem")).not.toBeInTheDocument();
  });

  it("aberto mostra o formulário", () => {
    render(<EmailComposer {...props()} />);

    expect(screen.getByText("Nova Mensagem")).toBeInTheDocument();
    expect(screen.getByText("Para:")).toBeInTheDocument();
  });
});

describe("EmailComposer — campos controlados", () => {
  it("escrever no destinatário avisa o contentor, campo a campo", async () => {
    const utilizador = userEvent.setup();
    const onFieldChange = vi.fn();

    render(<EmailComposer {...props({ onFieldChange })} />);
    const para = screen.getByPlaceholderText(/destinatario|@/i);
    await utilizador.type(para, "ana");

    expect(onFieldChange).toHaveBeenCalledWith("to_emails", expect.any(String));
  });

  it("o valor mostrado vem das props, não de estado interno", () => {
    render(
      <EmailComposer {...props({ data: rascunho({ subject: "Proposta revista" }) })} />,
    );

    expect(screen.getByDisplayValue("Proposta revista")).toBeInTheDocument();
  });

  it("CC e BCC estão escondidos até serem pedidos", async () => {
    const utilizador = userEvent.setup();
    const onToggleCc = vi.fn();

    render(<EmailComposer {...props({ onToggleCc })} />);
    await utilizador.click(screen.getByText("Mostrar CC"));

    expect(onToggleCc).toHaveBeenCalled();
  });

  it("com CC expandido a etiqueta muda", () => {
    render(<EmailComposer {...props({ ccExpanded: true })} />);

    expect(screen.getByText("Ocultar CC")).toBeInTheDocument();
  });
});

describe("EmailComposer — envio", () => {
  it("Enviar chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onSend = vi.fn();

    render(<EmailComposer {...props({ onSend })} />);
    await utilizador.click(screen.getByRole("button", { name: /Enviar/ }));

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("a enviar, os botões ficam bloqueados", () => {
    render(<EmailComposer {...props({ sending: true })} />);

    expect(screen.getByRole("button", { name: /A enviar/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
  });

  it("Cancelar chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onCancel = vi.fn();

    render(<EmailComposer {...props({ onCancel })} />);
    await utilizador.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("EmailComposer — conta de envio", () => {
  it("quem não pode escolher conta vê a explicação, não o seletor", () => {
    render(<EmailComposer {...props({ canUseGlobalAccounts: false })} />);

    expect(screen.queryByText("Conta:")).not.toBeInTheDocument();
    expect(screen.getByText(/conta pessoal/i)).toBeInTheDocument();
  });

  it("o perfil de indexação vê a frase da conta partilhada", () => {
    render(
      <EmailComposer {...props({ canUseGlobalAccounts: false, effectiveRole: "indexacao" })} />,
    );

    expect(screen.getByText(/conta partilhada de Indexação/i)).toBeInTheDocument();
  });

  it("admin/CEO/diretor vêem o seletor de conta", () => {
    render(<EmailComposer {...props({ canUseGlobalAccounts: true })} />);

    expect(screen.getByText("Conta:")).toBeInTheDocument();
  });
});

describe("EmailComposer — anexos", () => {
  it("lista os anexos carregados", () => {
    render(
      <EmailComposer
        {...props({
          attachments: [{ id: "a1", filename: "irs.pdf", size: 1024 }],
        })}
      />,
    );

    expect(screen.getByText("irs.pdf")).toBeInTheDocument();
  });

  it("remover um anexo avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onRemoveAttachment = vi.fn();

    render(
      <EmailComposer
        {...props({
          attachments: [{ id: "a1", filename: "irs.pdf", size: 1024 }],
          onRemoveAttachment,
        })}
      />,
    );

    await utilizador.click(screen.getByRole("button", { name: "Remover irs.pdf" }));

    expect(onRemoveAttachment).toHaveBeenCalledWith("a1");
  });

  it("largar ficheiros na zona entrega-os ao contentor", () => {
    const onUploadFiles = vi.fn();
    render(<EmailComposer {...props({ onUploadFiles })} />);

    const zona = screen.getByText(/Arraste ficheiros|Clique para/i).closest("div");
    const ficheiro = new File(["conteudo"], "recibo.pdf", { type: "application/pdf" });

    const evento = new Event("drop", { bubbles: true });
    Object.defineProperty(evento, "dataTransfer", { value: { files: [ficheiro] } });
    zona.dispatchEvent(evento);

    expect(onUploadFiles).toHaveBeenCalledWith([ficheiro]);
  });
});
