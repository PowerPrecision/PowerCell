/**
 * Teste de fumo da navegação de pastas (Épico 6, eixo 4).
 *
 * Âmbito: prova que a coluna rende as pastas, marcadores e pastas
 * personalizadas, e que cada clique devolve UMA intenção ao contentor.
 * Antes da extracção, um clique fazia quatro `set*` encadeados aqui dentro.
 */
import { render as renderRTL, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Inbox, Send, Star } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "../../ui/tooltip";
import FolderNavigation from "../FolderNavigation";

const render = (ui) =>
  renderRTL(ui, { wrapper: ({ children }) => <TooltipProvider>{children}</TooltipProvider> });

const PASTAS = [
  { id: "inbox", label: "Caixa de Entrada", icon: Inbox },
  { id: "sent", label: "Enviados", icon: Send },
  { id: "starred", label: "Destacados", icon: Star },
];

const props = (overrides = {}) => ({
  folders: PASTAS,
  customFolders: [],
  labels: [],
  mailboxOptions: [{ value: "personal:", label: "A minha caixa", unread: 0 }],
  activeFolder: "inbox",
  activeCustomFolder: null,
  selectedLabel: null,
  mailboxValue: "personal:",
  mailboxLocked: false,
  unreadCount: 0,
  folderCounts: {},
  totalEmails: 0,
  onSelectFolder: vi.fn(),
  onSelectLabel: vi.fn(),
  onSelectCustomFolder: vi.fn(),
  onOpenFolderMenu: vi.fn(),
  onCreateFolder: vi.fn(),
  onCompose: vi.fn(),
  onMailboxChange: vi.fn(),
  ...overrides,
});

describe("FolderNavigation — pastas do sistema", () => {
  it("rende todas as pastas recebidas", () => {
    render(<FolderNavigation {...props()} />);

    expect(screen.getByText("Caixa de Entrada")).toBeInTheDocument();
    expect(screen.getByText("Enviados")).toBeInTheDocument();
    expect(screen.getByText("Destacados")).toBeInTheDocument();
  });

  it("escolher uma pasta devolve UMA intenção", async () => {
    const utilizador = userEvent.setup();
    const onSelectFolder = vi.fn();

    render(<FolderNavigation {...props({ onSelectFolder })} />);
    await utilizador.click(screen.getByText("Enviados"));

    expect(onSelectFolder).toHaveBeenCalledWith("sent");
    expect(onSelectFolder).toHaveBeenCalledTimes(1);
  });

  it("a Caixa de Entrada mostra as não lidas, não o total", () => {
    render(
      <FolderNavigation
        {...props({ folderCounts: { inbox: 12 }, unreadCount: 3 })}
      />,
    );

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByText("12")).not.toBeInTheDocument();
  });

  it("as outras pastas mostram a contagem própria", () => {
    render(<FolderNavigation {...props({ folderCounts: { sent: 7 } })} />);

    expect(screen.getByText("7")).toBeInTheDocument();
  });
});

describe("FolderNavigation — marcadores", () => {
  it("sem marcadores, a secção não aparece", () => {
    render(<FolderNavigation {...props({ labels: [] })} />);

    expect(screen.queryByText("Marcadores")).not.toBeInTheDocument();
  });

  it("clicar num marcador selecciona-o", async () => {
    const utilizador = userEvent.setup();
    const onSelectLabel = vi.fn();

    render(
      <FolderNavigation
        {...props({ labels: [{ id: "l1", name: "Urgente", color: "#f00" }], onSelectLabel })}
      />,
    );
    await utilizador.click(screen.getByText("Urgente"));

    expect(onSelectLabel).toHaveBeenCalledWith("Urgente");
  });

  it("clicar no marcador já activo limpa-o", async () => {
    const utilizador = userEvent.setup();
    const onSelectLabel = vi.fn();

    render(
      <FolderNavigation
        {...props({
          labels: [{ id: "l1", name: "Urgente" }],
          selectedLabel: "Urgente",
          onSelectLabel,
        })}
      />,
    );
    await utilizador.click(screen.getByText("Urgente"));

    expect(onSelectLabel).toHaveBeenCalledWith(null);
  });
});

describe("FolderNavigation — pastas personalizadas", () => {
  const pastaPropria = [{ id: "f1", name: "Bancos", color: "#00f", email_count: 4 }];

  it("clicar na pasta selecciona-a", async () => {
    const utilizador = userEvent.setup();
    const onSelectCustomFolder = vi.fn();

    render(
      <FolderNavigation {...props({ customFolders: pastaPropria, onSelectCustomFolder })} />,
    );
    await utilizador.click(screen.getByText("Bancos"));

    expect(onSelectCustomFolder).toHaveBeenCalledWith("f1");
  });

  it("o menu da pasta é um botão IRMÃO, não aninhado", async () => {
    // Regressão: no monolito este botão vivia DENTRO do botão da pasta —
    // HTML inválido. Clicar no menu não pode seleccionar a pasta.
    const utilizador = userEvent.setup();
    const onOpenFolderMenu = vi.fn();
    const onSelectCustomFolder = vi.fn();

    render(
      <FolderNavigation
        {...props({ customFolders: pastaPropria, onOpenFolderMenu, onSelectCustomFolder })}
      />,
    );

    const menu = screen.getByRole("button", { name: "Opções da pasta Bancos" });
    expect(menu.closest("button:not([aria-label])")).toBeNull();

    await utilizador.click(menu);
    expect(onOpenFolderMenu).toHaveBeenCalledWith(
      expect.objectContaining({ id: "f1" }),
      expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }),
    );
    expect(onSelectCustomFolder).not.toHaveBeenCalled();
  });

  it("criar pasta chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onCreateFolder = vi.fn();

    render(<FolderNavigation {...props({ onCreateFolder })} />);
    await utilizador.click(screen.getByTitle("Nova pasta"));

    expect(onCreateFolder).toHaveBeenCalledTimes(1);
  });
});

describe("FolderNavigation — acções do topo", () => {
  it("Nova Mensagem chama o callback", async () => {
    const utilizador = userEvent.setup();
    const onCompose = vi.fn();

    render(<FolderNavigation {...props({ onCompose })} />);
    await utilizador.click(screen.getByRole("button", { name: /Nova Mensagem/ }));

    expect(onCompose).toHaveBeenCalledTimes(1);
  });

  it("já NÃO tem o botão de sincronizar de largura total", () => {
    // Ponto 8, Fase 3 — o comportamento não desapareceu, MUDOU DE SÍTIO:
    // vive agora no cabeçalho do separador da empresa
    // (`WebmailCompanyTabs`), como indicador discreto. Ocupar uma fatia
    // permanente da barra lateral com uma acção usada uma vez por sessão
    // era o "painel intrusivo" que este ponto veio remover.
    render(<FolderNavigation {...props()} />);

    expect(screen.queryByRole("button", { name: /sincronizar/i })).toBeNull();
  });

  it("o rodapé conta os emails", () => {
    render(<FolderNavigation {...props({ totalEmails: 42 })} />);

    expect(screen.getByText("42 emails")).toBeInTheDocument();
  });

  it("um só email não vem no plural", () => {
    render(<FolderNavigation {...props({ totalEmails: 1 })} />);

    expect(screen.getByText("1 email")).toBeInTheDocument();
  });
});
