/**
 * O Calendário Geral MONTADO (Lote 7, ponto 3).
 *
 * A auditoria aos calendários pediu três respostas, e duas são de UI:
 * «os eventos mostram claramente a qual cliente pertencem?» e «permitem
 * navegar para a ficha desse cliente?». As duas eram NÃO: o chip da grelha
 * mostrava `[Responsável] Título` e o nome do cliente aparecia só no painel
 * do dia, como texto morto. Não havia como chegar à ficha.
 *
 * O `GlobalCalendar` é o REAL — falseá-lo tornava o teste inútil, porque é
 * nele que o chip e a ligação vivem.
 *
 * A FORMA DOS DADOS É A REAL, lida em
 * `services/deadlines_api_calendar._enrich_calendar_rows`: cada linha traz
 * `type`, `all_day`, `end_date`, `client_name`, `client_id`, `client_email`,
 * `process_status`, `responsible_id`, `responsible_name` e os campos do
 * próprio prazo. Os recuos `"Evento Geral"` e `"Ausência"` em `client_name`
 * são escritos pelo SERVIDOR — estão aqui porque é preciso provar que o ecrã
 * não os mostra como se fossem o nome de alguém.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("../../components/admin/CreateEventDialog", () => ({
  default: ({ open }) => (open ? <div data-testid="dialogo-evento" /> : null),
}));

const navegar = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => navegar,
}));

let papelActivo = "diretor";
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", name: "Quem Vê A Agenda", role: "consultor" },
    effectiveRole: papelActivo,
  }),
}));

vi.mock("../../services/api", () => ({
  getCalendarDeadlines: vi.fn(),
  getProcesses: vi.fn(),
  getStaffUsers: vi.fn(),
  createDeadline: vi.fn(),
  updateDeadline: vi.fn(),
  deleteDeadline: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import CalendarPage from "../CalendarPage";
import * as api from "../../services/api";

const HOJE = new Date();
const chave = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
const AMANHA = new Date(HOJE.getFullYear(), HOJE.getMonth(), HOJE.getDate() + 1);

const EVENTOS = [
  {
    id: "ev1",
    title: "Escritura",
    description: "Notário às 10h",
    type: "event",
    due_date: chave(AMANHA),
    end_date: chave(AMANHA),
    all_day: true,
    priority: "high",
    completed: false,
    process_id: "p1",
    client_id: "c1",
    client_name: "Ana Martins",
    client_email: "ana@exemplo.pt",
    process_status: "analise",
    responsible_id: "u2",
    responsible_name: "Outro Consultor",
    assigned_user_ids: ["u2"],
  },
  {
    id: "ev2",
    title: "Primeira reunião",
    type: "event",
    due_date: chave(AMANHA),
    all_day: true,
    priority: "medium",
    completed: false,
    // Cliente da Pool: sem processo. É quem vive sozinho na raiz documental
    // e quem o calendário tem de conseguir alcançar pela ficha do cliente.
    client_id: "c9",
    client_name: "Rui Pereira",
    responsible_id: "u1",
    responsible_name: "Quem Vê A Agenda",
    assigned_user_ids: ["u1"],
  },
  {
    id: "ev3",
    title: "Férias",
    type: "absence",
    due_date: chave(AMANHA),
    all_day: true,
    priority: "low",
    completed: false,
    // O SERVIDOR escreve este recuo quando não há processo.
    client_name: "Ausência",
    responsible_id: "u2",
    responsible_name: "Outro Consultor",
    assigned_user_ids: ["u2"],
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  papelActivo = "diretor";
  api.getCalendarDeadlines.mockResolvedValue({ data: EVENTOS });
  api.getProcesses.mockResolvedValue({ data: { items: [] } });
  api.getStaffUsers.mockResolvedValue({ data: [] });
});

describe("CalendarPage — montar e sobreviver", () => {
  it("monta e mostra as marcações futuras", async () => {
    render(<CalendarPage />);
    expect(await screen.findByTestId("calendar-page")).toBeInTheDocument();
    await waitFor(() => expect(api.getCalendarDeadlines).toHaveBeenCalled());
  });

  it("não deixa nenhum erro no render escapar para a consola", async () => {
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<CalendarPage />);
    await screen.findByTestId("calendar-filters");
    expect(espia).not.toHaveBeenCalled();
    espia.mockRestore();
  });

  it("sobrevive a uma resposta que não é uma lista", async () => {
    // Um 403 ou um envelope inesperado não pode deixar a página em branco.
    api.getCalendarDeadlines.mockResolvedValue({ data: { detail: "nope" } });
    render(<CalendarPage />);
    expect(await screen.findByTestId("calendar-page")).toBeInTheDocument();
  });

  it("sobrevive a um erro do servidor", async () => {
    api.getCalendarDeadlines.mockRejectedValue({
      response: { status: 500, data: { detail: "boom" } },
    });
    render(<CalendarPage />);
    expect(await screen.findByTestId("calendar-page")).toBeInTheDocument();
  });
});

describe("CalendarPage — identidade visual: de quem é o evento", () => {
  it("na vista de EQUIPA o chip diz o nome do cliente", async () => {
    // Era `[Responsável] Título`: doze «Escritura» num dia não se
    // distinguem, e o responsável responde «quem trata», não «de quem é».
    render(<CalendarPage />);
    await waitFor(() => expect(api.getCalendarDeadlines).toHaveBeenCalled());
    const chips = await screen.findAllByTestId("calendar-event-chip");
    const textos = chips.map((c) => c.textContent).join(" | ");
    expect(textos).toContain("Ana Martins");
  });

  it("na agenda PESSOAL o chip não repete o cliente", async () => {
    // O utilizador já sabe que é dele; o cliente aparece no painel do dia.
    papelActivo = "consultor";
    render(<CalendarPage />);
    await waitFor(() => expect(api.getCalendarDeadlines).toHaveBeenCalled());
    const chips = await screen.findAllByTestId("calendar-event-chip");
    const textos = chips.map((c) => c.textContent).join(" | ");
    expect(textos).toContain("Escritura");
    expect(textos).not.toContain("Ana Martins · Escritura");
  });

  it("a lista «Próximas marcações» mostra o cliente de cada evento", async () => {
    render(<CalendarPage />);
    expect(await screen.findByText("Ana Martins")).toBeInTheDocument();
    expect(screen.getByText("Rui Pereira")).toBeInTheDocument();
  });

  it("NÃO mostra os recuos do servidor como se fossem um cliente", async () => {
    // `_enrich_calendar_rows` escreve "Ausência" e "Evento Geral" em
    // `client_name`. Mostrá-los punha «Ausência» onde devia estar um nome.
    render(<CalendarPage />);
    await screen.findByText("Ana Martins");
    const linhas = screen.getAllByRole("listitem");
    const textoDaAusencia = linhas
      .map((l) => l.textContent)
      .find((t) => t.includes("Férias"));
    expect(textoDaAusencia).toBeDefined();
    // O crachá "Ausência" é legítimo; o que não pode é aparecer como nome
    // do cliente, i.e. sem o evento ter cliente nenhum.
    expect(textoDaAusencia).not.toContain("Abrir");
  });
});

describe("CalendarPage — navegar para a ficha", () => {
  it("abre o PROCESSO a partir de um evento com processo", async () => {
    const utilizador = userEvent.setup();
    render(<CalendarPage />);
    await screen.findByText("Ana Martins");
    const botoes = screen.getAllByTestId("proxima-abrir-ficha");
    await utilizador.click(botoes[0]);
    await waitFor(() => expect(navegar).toHaveBeenCalledWith("/processo/p1"));
  });

  it("abre a FICHA DO CLIENTE quando não há processo (o caso da Pool)", async () => {
    const utilizador = userEvent.setup();
    render(<CalendarPage />);
    const linha = (await screen.findByText("Rui Pereira")).closest("li");
    await utilizador.click(
      within(linha).getByTestId("proxima-abrir-ficha"),
    );
    await waitFor(() => expect(navegar).toHaveBeenCalledWith("/cliente/c9"));
  });

  it("uma ausência NÃO tem botão de abrir ficha", async () => {
    // Contraprova: desenhar o botão sempre também passava os dois acima, e
    // um link que não leva a lado nenhum é pior do que texto.
    render(<CalendarPage />);
    await screen.findByText("Ana Martins");
    const linhas = screen.getAllByRole("listitem");
    const daAusencia = linhas.find((l) => l.textContent.includes("Férias"));
    expect(
      within(daAusencia).queryByTestId("proxima-abrir-ficha"),
    ).not.toBeInTheDocument();
  });
});
