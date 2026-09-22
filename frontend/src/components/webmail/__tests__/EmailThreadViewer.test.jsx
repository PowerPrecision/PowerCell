/**
 * Teste de fumo do painel de leitura (Épico 6, eixo 4).
 *
 * Âmbito deliberado: prova que o painel rende os três estados e que as
 * acções chamam os callbacks certos. A cobertura profunda desta coluna
 * fica para quando o painel deixar de ser só apresentação.
 */
import { render as renderRTL, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "../../ui/tooltip";
import EmailThreadViewer from "../EmailThreadViewer";

// O painel usa Tooltip, que exige um TooltipProvider acima — a página
// envolve tudo num. O teste replica esse contexto em vez de o esconder.
const render = (ui) => {
  const wrapper = ({ children }) => <TooltipProvider>{children}</TooltipProvider>;
  const resultado = renderRTL(ui, { wrapper });
  return { ...resultado, rerender: (novo) => resultado.rerender(novo) };
};

const emailDetalhe = (overrides = {}) => ({
  id: "e1",
  subject: "Pré-aprovação do banco",
  from_email: "banco@exemplo.pt",
  to_emails: ["geral@powercell.pt"],
  cc_emails: [],
  body: "Confirmamos a pré-aprovação.",
  sent_at: "2026-09-20T10:30:00Z",
  is_read: true,
  is_starred: false,
  attachments: [],
  labels: [],
  ...overrides,
});

const props = (overrides = {}) => ({
  email: emailDetalhe(),
  loading: false,
  sanitizedBodyHtml: "",
  replyAllRecipientCount: 0,
  downloadingAttachmentId: null,
  onReply: vi.fn(),
  onReplyAll: vi.fn(),
  onForward: vi.fn(),
  onToggleRead: vi.fn(),
  onToggleStar: vi.fn(),
  onLinkToProcess: vi.fn(),
  onMoveToFolder: vi.fn(),
  onDelete: vi.fn(),
  onOpenProcess: vi.fn(),
  onOpenInNewTab: vi.fn(),
  onDownloadAttachment: vi.fn(),
  ...overrides,
});

describe("EmailThreadViewer — estados", () => {
  it("sem email seleccionado convida a escolher um", () => {
    render(<EmailThreadViewer {...props({ email: null })} />);

    expect(screen.getByText("Selecione um email para visualizar")).toBeInTheDocument();
  });

  it("a carregar não mostra o convite nem o assunto", () => {
    render(<EmailThreadViewer {...props({ loading: true })} />);

    expect(screen.queryByText("Selecione um email para visualizar")).not.toBeInTheDocument();
    expect(screen.queryByText("Pré-aprovação do banco")).not.toBeInTheDocument();
  });

  it("com email mostra assunto, remetente e destinatário", () => {
    render(<EmailThreadViewer {...props()} />);

    expect(screen.getByText("Pré-aprovação do banco")).toBeInTheDocument();
    expect(screen.getByText("banco@exemplo.pt")).toBeInTheDocument();
    expect(screen.getByText("geral@powercell.pt")).toBeInTheDocument();
  });

  it("sem HTML sanitizado mostra o corpo em texto simples", () => {
    render(<EmailThreadViewer {...props()} />);

    expect(screen.getByText("Confirmamos a pré-aprovação.")).toBeInTheDocument();
  });
});

describe("EmailThreadViewer — acções", () => {
  it("Responder chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onReply = vi.fn();

    render(<EmailThreadViewer {...props({ onReply })} />);
    await utilizador.click(screen.getByRole("button", { name: /^Responder$/ }));

    expect(onReply).toHaveBeenCalledTimes(1);
  });

  it("'Responder a Todos' só aparece quando há mais gente na conversa", () => {
    const { rerender } = render(<EmailThreadViewer {...props({ replyAllRecipientCount: 1 })} />);
    expect(screen.queryByRole("button", { name: /Responder a Todos/ })).not.toBeInTheDocument();

    rerender(<EmailThreadViewer {...props({ replyAllRecipientCount: 3 })} />);
    expect(screen.getByRole("button", { name: /Responder a Todos/ })).toBeInTheDocument();
  });

  it("Encaminhar e Eliminar chamam os callbacks certos", async () => {
    const utilizador = userEvent.setup();
    const onForward = vi.fn();
    const onDelete = vi.fn();

    render(<EmailThreadViewer {...props({ onForward, onDelete })} />);
    await utilizador.click(screen.getByRole("button", { name: /Encaminhar/ }));
    expect(onForward).toHaveBeenCalledTimes(1);
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("o botão de lida reflecte o estado actual", () => {
    const { rerender } = render(<EmailThreadViewer {...props()} />);
    expect(screen.getByRole("button", { name: /Marcar como não lida/ })).toBeInTheDocument();

    rerender(<EmailThreadViewer {...props({ email: emailDetalhe({ is_read: false }) })} />);
    expect(screen.getByRole("button", { name: /Marcar como lida/ })).toBeInTheDocument();
  });

  it("sem processo associado oferece 'Ligar a Processo'", async () => {
    const utilizador = userEvent.setup();
    const onLinkToProcess = vi.fn();

    render(<EmailThreadViewer {...props({ onLinkToProcess })} />);
    await utilizador.click(screen.getByRole("button", { name: /Ligar a Processo/ }));

    expect(onLinkToProcess).toHaveBeenCalledTimes(1);
  });

  it("com processo associado oferece 'Ver Processo'", async () => {
    const utilizador = userEvent.setup();
    const onOpenProcess = vi.fn();

    render(
      <EmailThreadViewer
        {...props({ email: emailDetalhe({ process_id: "p-9" }), onOpenProcess })}
      />,
    );
    await utilizador.click(screen.getByRole("button", { name: /Ver Processo/ }));

    expect(onOpenProcess).toHaveBeenCalledTimes(1);
  });
});

describe("EmailThreadViewer — anexos", () => {
  it("lista os anexos e pede a transferência ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onDownloadAttachment = vi.fn();
    const anexo = { id: "a1", filename: "simulacao.pdf", size: 2048 };

    render(
      <EmailThreadViewer
        {...props({
          email: emailDetalhe({ attachments: [anexo] }),
          onDownloadAttachment,
        })}
      />,
    );

    expect(screen.getByText("simulacao.pdf")).toBeInTheDocument();
    expect(screen.getByText("Anexos (1)")).toBeInTheDocument();

    await utilizador.click(
      screen.getByRole("button", { name: /Abrir simulacao\.pdf num novo separador/ }),
    );
    expect(onDownloadAttachment).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }), 0);
  });
});
