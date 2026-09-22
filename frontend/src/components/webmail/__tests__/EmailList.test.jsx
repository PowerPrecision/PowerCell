/**
 * Testes de COMPONENTE da lista de emails (Épico 6, eixo 4).
 *
 * Primeiro teste visual do projecto: até aqui, `node --test` só conseguia
 * exercitar funções puras e nenhum componente tinha rede de segurança.
 *
 * O que estes testes fixam, e porquê:
 * - a lista rende uma linha por CONVERSA (não por email) — o agrupamento do
 *   Épico 5 é o contrato desta coluna;
 * - expandir a conversa e abrir a mensagem são acções SEPARADAS. No monolito
 *   isso obrigou a pôr dois `<button>` lado a lado (um botão não pode viver
 *   dentro de outro); se a extracção os aninhar, o teste do "expandir não
 *   abre" fica vermelho.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import EmailList from "../EmailList";

const email = (overrides = {}) => ({
  id: "e1",
  subject: "Proposta de crédito",
  preview: "Segue em anexo a simulação",
  from_email: "cliente@exemplo.pt",
  client_name: "",
  to_emails: ["geral@powercell.pt"],
  direction: "received",
  is_read: true,
  is_starred: false,
  attachments: [],
  labels: [],
  sent_at: "2026-09-20T10:30:00Z",
  ...overrides,
});

/** Uma conversa com uma só mensagem. */
const conversaSimples = (overrides = {}) => {
  const msg = email(overrides);
  return { key: `t-${msg.id}`, latest: msg, emails: [msg], count: 1 };
};

/** Uma conversa com várias mensagens (a mais recente primeiro). */
const conversaComVarias = (mensagens) => ({
  key: "t-conversa",
  latest: mensagens[0],
  emails: mensagens,
  count: mensagens.length,
});

const props = (overrides = {}) => ({
  threads: [conversaSimples()],
  loading: false,
  headerTitle: "Caixa de Entrada",
  emptyMessage: "Sem emails nesta pasta",
  totalEmails: 1,
  selectedEmailId: null,
  selectedEmails: new Set(),
  multiSelectMode: false,
  expandedThreads: new Set(),
  currentPage: 1,
  totalPages: 1,
  onSelectEmail: vi.fn(),
  onToggleThread: vi.fn(),
  onSelectAll: vi.fn(),
  onPageChange: vi.fn(),
  onClearFolder: null,
  onClearLabel: null,
  ...overrides,
});

describe("EmailList — renderização", () => {
  it("mostra o título da pasta e uma linha por conversa", () => {
    render(
      <EmailList
        {...props({
          threads: [
            conversaSimples({ id: "a", subject: "Primeiro" }),
            conversaSimples({ id: "b", subject: "Segundo" }),
          ],
          totalEmails: 2,
        })}
      />,
    );

    expect(screen.getByText("Caixa de Entrada")).toBeInTheDocument();
    expect(screen.getByText("Primeiro")).toBeInTheDocument();
    expect(screen.getByText("Segundo")).toBeInTheDocument();
  });

  it("mostra o remetente nos emails recebidos e o destinatário nos enviados", () => {
    render(
      <EmailList
        {...props({
          threads: [
            conversaSimples({ id: "a", from_email: "maria@exemplo.pt" }),
            conversaSimples({
              id: "b",
              direction: "sent",
              to_emails: ["banco@exemplo.pt"],
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText("maria@exemplo.pt")).toBeInTheDocument();
    expect(screen.getByText("banco@exemplo.pt")).toBeInTheDocument();
  });

  it("prefere o nome do cliente ao endereço, quando existe", () => {
    render(
      <EmailList {...props({ threads: [conversaSimples({ client_name: "Ana Dias" })] })} />,
    );

    expect(screen.getByText("Ana Dias")).toBeInTheDocument();
    expect(screen.queryByText("cliente@exemplo.pt")).not.toBeInTheDocument();
  });

  it("assunto em falta não parte a linha", () => {
    render(<EmailList {...props({ threads: [conversaSimples({ subject: null })] })} />);

    expect(screen.getByText("(Sem assunto)")).toBeInTheDocument();
  });

  it("sinaliza anexo, destaque e processo associado", () => {
    render(
      <EmailList
        {...props({
          threads: [
            conversaSimples({
              attachments: [{ filename: "simulacao.pdf" }],
              is_starred: true,
              process_id: "p-1",
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText("Proc.")).toBeInTheDocument();
    expect(screen.getByTestId("indicador-anexo")).toBeInTheDocument();
    expect(screen.getByTestId("indicador-destaque")).toBeInTheDocument();
  });

  it("marca visualmente as mensagens não lidas", () => {
    render(<EmailList {...props({ threads: [conversaSimples({ is_read: false })] })} />);

    expect(screen.getByTestId("indicador-nao-lida")).toBeInTheDocument();
  });
});

describe("EmailList — estados sem conteúdo", () => {
  it("em carregamento mostra esqueletos e nenhuma conversa", () => {
    render(<EmailList {...props({ loading: true, threads: [] })} />);

    expect(screen.getAllByTestId("esqueleto-email").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Proposta/ })).not.toBeInTheDocument();
  });

  it("sem emails mostra a mensagem que o contentor decidiu", () => {
    render(
      <EmailList
        {...props({ threads: [], totalEmails: 0, emptyMessage: "Nenhum email encontrado" })}
      />,
    );

    expect(screen.getByText("Nenhum email encontrado")).toBeInTheDocument();
  });

  it("o carregamento ganha ao estado vazio (não pisca 'sem emails')", () => {
    render(<EmailList {...props({ loading: true, threads: [], totalEmails: 0 })} />);

    expect(screen.queryByText("Sem emails nesta pasta")).not.toBeInTheDocument();
  });
});

describe("EmailList — abrir mensagens", () => {
  it("clicar na linha devolve o email ao contentor", async () => {
    const utilizador = userEvent.setup();
    const onSelectEmail = vi.fn();
    const alvo = conversaSimples({ id: "e-42", subject: "Escritura agendada" });

    render(<EmailList {...props({ threads: [alvo], onSelectEmail })} />);
    await utilizador.click(screen.getByText("Escritura agendada"));

    expect(onSelectEmail).toHaveBeenCalledTimes(1);
    expect(onSelectEmail).toHaveBeenCalledWith(expect.objectContaining({ id: "e-42" }));
  });

  it("a linha seleccionada é assinalada", () => {
    render(
      <EmailList
        {...props({
          threads: [conversaSimples({ id: "e-7" })],
          selectedEmailId: "e-7",
        })}
      />,
    );

    expect(screen.getByTestId("linha-email-e-7")).toHaveAttribute("aria-current", "true");
  });
});

describe("EmailList — conversas (Épico 5)", () => {
  const conversa = conversaComVarias([
    email({ id: "m3", subject: "Re: Proposta", sent_at: "2026-09-20T12:00:00Z" }),
    email({ id: "m2", subject: "Re: Proposta", preview: "Obrigado" }),
    email({ id: "m1", subject: "Proposta", preview: "Bom dia" }),
  ]);

  it("mostra o número de mensagens da conversa", () => {
    render(<EmailList {...props({ threads: [conversa], totalEmails: 3 })} />);

    expect(screen.getByTitle("3 mensagens nesta conversa")).toHaveTextContent("3");
  });

  it("uma conversa de uma só mensagem não tem botão de expandir", () => {
    render(<EmailList {...props({ threads: [conversaSimples()] })} />);

    expect(screen.queryByRole("button", { name: /Expandir conversa/ })).not.toBeInTheDocument();
  });

  it("expandir chama onToggleThread com a chave da conversa", async () => {
    const utilizador = userEvent.setup();
    const onToggleThread = vi.fn();

    render(<EmailList {...props({ threads: [conversa], onToggleThread })} />);
    await utilizador.click(screen.getByRole("button", { name: /Expandir conversa/ }));

    expect(onToggleThread).toHaveBeenCalledWith("t-conversa");
  });

  it("expandir NÃO abre a mensagem", async () => {
    // Guarda do desenho: são duas acções distintas, em dois botões irmãos.
    // Se a extracção aninhar os botões, este teste fica vermelho.
    const utilizador = userEvent.setup();
    const onSelectEmail = vi.fn();

    render(<EmailList {...props({ threads: [conversa], onSelectEmail })} />);
    await utilizador.click(screen.getByRole("button", { name: /Expandir conversa/ }));

    expect(onSelectEmail).not.toHaveBeenCalled();
  });

  it("conversa fechada esconde as mensagens anteriores", () => {
    render(<EmailList {...props({ threads: [conversa] })} />);

    expect(screen.queryByTestId("linha-email-m2")).not.toBeInTheDocument();
  });

  it("conversa aberta mostra as anteriores e permite abri-las", async () => {
    const utilizador = userEvent.setup();
    const onSelectEmail = vi.fn();

    render(
      <EmailList
        {...props({
          threads: [conversa],
          expandedThreads: new Set(["t-conversa"]),
          onSelectEmail,
        })}
      />,
    );

    const anteriores = screen.getByTestId("conversa-anteriores-t-conversa");
    expect(within(anteriores).getByTestId("linha-email-m2")).toBeInTheDocument();
    expect(within(anteriores).getByTestId("linha-email-m1")).toBeInTheDocument();
    // A mais recente vive na linha principal, não na lista de anteriores.
    expect(within(anteriores).queryByTestId("linha-email-m3")).not.toBeInTheDocument();

    await utilizador.click(within(anteriores).getByTestId("linha-email-m1"));
    expect(onSelectEmail).toHaveBeenCalledWith(expect.objectContaining({ id: "m1" }));
  });

  it("o botão de expandir anuncia o estado a quem usa leitor de ecrã", () => {
    const { rerender } = render(<EmailList {...props({ threads: [conversa] })} />);
    expect(screen.getByRole("button", { name: /Expandir conversa/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    rerender(
      <EmailList {...props({ threads: [conversa], expandedThreads: new Set(["t-conversa"]) })} />,
    );
    expect(screen.getByRole("button", { name: /Fechar conversa/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});

describe("EmailList — selecção múltipla", () => {
  it("fora do modo múltiplo não há 'Selecionar tudo'", () => {
    render(<EmailList {...props()} />);

    expect(screen.queryByText(/Selecionar tudo/)).not.toBeInTheDocument();
  });

  it("'Selecionar tudo' chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onSelectAll = vi.fn();

    render(<EmailList {...props({ multiSelectMode: true, onSelectAll })} />);
    await utilizador.click(screen.getByText("Selecionar tudo"));

    expect(onSelectAll).toHaveBeenCalledTimes(1);
  });

  it("com tudo seleccionado o botão passa a 'Desselecionar'", () => {
    render(
      <EmailList
        {...props({
          multiSelectMode: true,
          totalEmails: 1,
          selectedEmails: new Set(["e1"]),
        })}
      />,
    );

    expect(screen.getByText("Desselecionar")).toBeInTheDocument();
  });

  it("as linhas seleccionadas aparecem marcadas", () => {
    render(
      <EmailList
        {...props({
          multiSelectMode: true,
          selectedEmails: new Set(["e1"]),
        })}
      />,
    );

    expect(screen.getByTestId("caixa-seleccionada-e1")).toBeInTheDocument();
  });
});

describe("EmailList — paginação", () => {
  it("com uma só página não há controlos", () => {
    render(<EmailList {...props({ totalPages: 1 })} />);

    expect(screen.queryByRole("button", { name: "Seguinte" })).not.toBeInTheDocument();
  });

  it("na primeira página o 'Anterior' está desactivado", () => {
    render(<EmailList {...props({ currentPage: 1, totalPages: 3 })} />);

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
  });

  it("'Seguinte' pede a página a seguir", async () => {
    const utilizador = userEvent.setup();
    const onPageChange = vi.fn();

    render(<EmailList {...props({ currentPage: 2, totalPages: 3, onPageChange })} />);
    await utilizador.click(screen.getByRole("button", { name: "Seguinte" }));

    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("'Anterior' pede a página de trás", async () => {
    const utilizador = userEvent.setup();
    const onPageChange = vi.fn();

    render(<EmailList {...props({ currentPage: 2, totalPages: 3, onPageChange })} />);
    await utilizador.click(screen.getByRole("button", { name: "Anterior" }));

    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it("na última página o 'Seguinte' está desactivado", () => {
    render(<EmailList {...props({ currentPage: 3, totalPages: 3 })} />);

    expect(screen.getByRole("button", { name: "Seguinte" })).toBeDisabled();
  });
});

describe("EmailList — filtros activos", () => {
  it("sem filtros não mostra botões de limpar", () => {
    render(<EmailList {...props()} />);

    expect(screen.queryByRole("button", { name: "Limpar pasta" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Limpar marcador" })).not.toBeInTheDocument();
  });

  it("limpar a pasta avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onClearFolder = vi.fn();

    render(<EmailList {...props({ headerTitle: "Bancos", onClearFolder })} />);
    await utilizador.click(screen.getByRole("button", { name: "Limpar pasta" }));

    expect(onClearFolder).toHaveBeenCalledTimes(1);
  });

  it("pasta e marcador activos ao mesmo tempo têm um X CADA", async () => {
    // Regressão da extracção: os dois filtros PODEM coexistir (escolher um
    // marcador não limpa a pasta personalizada). Um só botão de limpar
    // mudaria o comportamento — obrigava a dois cliques e pela ordem errada.
    const utilizador = userEvent.setup();
    const onClearFolder = vi.fn();
    const onClearLabel = vi.fn();

    render(<EmailList {...props({ headerTitle: "Bancos", onClearFolder, onClearLabel })} />);

    await utilizador.click(screen.getByRole("button", { name: "Limpar marcador" }));
    expect(onClearLabel).toHaveBeenCalledTimes(1);
    expect(onClearFolder).not.toHaveBeenCalled();

    await utilizador.click(screen.getByRole("button", { name: "Limpar pasta" }));
    expect(onClearFolder).toHaveBeenCalledTimes(1);
  });
});
