/**
 * O Quadro de Visitas MONTADO (Lote 9, Fase B — a regra da D-20).
 *
 * Esta página de 1100+ linhas nunca tinha sido montada num teste. É a
 * regra do `WebmailPage`, da `ProcessesPage` e do Kanban: nem o eslint,
 * nem o build, nem os testes de componente avaliam o render, e foi
 * exactamente por aqui que a `VisitsPage` guardava um defeito de forma —
 * `useState([])` para um endpoint que devolve um OBJECTO.
 *
 * Daí o primeiro teste ser o mais estúpido possível: montar e sobreviver.
 *
 * A FORMA DOS DADOS É A REAL, lida no backend antes de escrever isto:
 * `GET /visits/kanban` devolve
 * `{solicitadas, agendadas, concluidas, canceladas, total}`
 * (`services/visit_kanban_get.run_get_visits_kanban`) e cada visita traz
 * os campos de topo que este lote criou (`scraped_price`,
 * `scraped_typology`, `scraped_area`, `scraped_estado`) mais o
 * `scraped_data` completo. Um mock com a forma inventada é pior do que
 * nenhum — é a armadilha do `/portal/status` e do `{config, fields}`.
 *
 * O `VisitasTable` é o REAL: falseá-lo tornava o teste inútil, porque o
 * que falta cobrir é a ligação página ↔ tabela.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children, title }) => (
    <div data-testid="layout" data-title={title}>{children}</div>
  ),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", name: "Quem Vê", role: "consultor" },
    token: "t",
  }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import VisitsPage from "../VisitsPage";

const PEDIDO_DO_PORTAL = {
  id: "v-pedido",
  status: "solicitada",
  property_title: "T3 em Cascais com vista mar",
  client_name: "Ana Martins",
  process_id: "proc-1",
  client_id: "proc-1",
  scheduled_date: null,
  scraped_url: "https://www.idealista.pt/imovel/111/",
  scraper_status: "completed",
  scraped_price: 420000,
  scraped_typology: "T3",
  scraped_area: 140,
  scraped_estado: "remodelado",
  property_address: { municipality: "Cascais", district: "" },
  // LOTE 10 — quem anuncia, nos campos de TOPO.
  agency_name: "Predial Atlântico",
  agent_name: "Marta Nunes",
  agent_phone: "912345678",
  agent_email: "marta.nunes@predial-atlantico.pt",
  scraped_data: { source: "idealista", location: "Cascais" },
};

const AGENDADA = {
  id: "v-agendada",
  status: "agendada",
  property_title: "T2 em Leiria",
  client_name: "Bruno Dias",
  process_id: "proc-2",
  client_id: "proc-2",
  consultor_name: "Rui Consultor",
  scheduled_date: "2026-11-20T15:00:00Z",
  scraped_url: "https://www.imovirtual.com/anuncio/222/",
  scraper_status: "completed",
  scraped_price: 185000,
  scraped_typology: "T2",
  // O caminho LEGADO: uma visita extraída antes dos campos de topo
  // existirem. Nada se migra, logo tem de continuar a ver-se.
  scraped_data: {
    consultant: {
      agency_name: "Remax Leiria",
      name: "Rui Agente",
      phone: "931111111",
    },
  },
};

function quadro(extra = {}) {
  return {
    solicitadas: [PEDIDO_DO_PORTAL],
    agendadas: [AGENDADA],
    concluidas: [],
    canceladas: [],
    total: 2,
    ...extra,
  };
}

function prepararFetch(respostaDoQuadro = quadro()) {
  globalThis.fetch = vi.fn((url) => {
    const alvo = String(url);
    if (alvo.includes("/visits/kanban")) {
      return Promise.resolve({ ok: true, json: async () => respostaDoQuadro });
    }
    // `fetchFormData` pede imóveis, processos e staff para o diálogo.
    return Promise.resolve({ ok: true, json: async () => [] });
  });
}

function montar() {
  return render(
    <MemoryRouter>
      <VisitsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  prepararFetch();
});

describe("montar e sobreviver", () => {
  it("a página monta e mostra o título", async () => {
    montar();
    expect(await screen.findByTestId("layout")).toHaveAttribute(
      "data-title",
      "Quadro de Visitas"
    );
  });

  it("pede o quadro ao endpoint certo", async () => {
    montar();
    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([u]) => String(u).includes("/visits/kanban"))
      ).toBe(true)
    );
  });
});

describe("a tabela é a vista por omissão", () => {
  it("mostra uma linha por visita", async () => {
    montar();
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByText("T3 em Cascais com vista mar")).toBeInTheDocument();
    expect(screen.getByText("T2 em Leiria")).toBeInTheDocument();
  });

  it("os dados que a IA leu aparecem na linha", async () => {
    // Os seis campos pedidos: preço, tipologia, área, estado, localização
    // e o URL original. O `estado` é o que se perdia (D-23).
    montar();
    await screen.findByRole("table");
    expect(screen.getByText("T3")).toBeInTheDocument();
    expect(screen.getByText("140 m²")).toBeInTheDocument();
    expect(screen.getByText("remodelado")).toBeInTheDocument();
    expect(screen.getByText("Cascais")).toBeInTheDocument();
    // O preço vai formatado em euros, sem casas decimais.
    expect(screen.getByText(/420\s?000/)).toBeInTheDocument();
  });

  it("o anúncio original é alcançável", async () => {
    montar();
    await screen.findByRole("table");
    const ligacoes = screen.getAllByRole("link", { name: /ver anúncio/i });
    expect(ligacoes[0]).toHaveAttribute(
      "href",
      "https://www.idealista.pt/imovel/111/"
    );
    expect(ligacoes[0]).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("o PEDIDO do Portal aparece antes da visita já agendada", async () => {
    // Ordenar por data punha os pedidos (sem data) no fim, onde ninguém
    // os vê — e um pedido que ninguém vê é a forma de defeito desta casa.
    montar();
    const tabela = await screen.findByRole("table");
    const linhas = within(tabela).getAllByRole("row").slice(1);
    expect(linhas[0]).toHaveTextContent("T3 em Cascais");
    expect(linhas[1]).toHaveTextContent("T2 em Leiria");
  });
});

describe("a ligação ao cliente", () => {
  it("o nome do cliente leva ao PROCESSO", async () => {
    montar();
    await screen.findByRole("table");
    expect(screen.getByRole("link", { name: "Ana Martins" })).toHaveAttribute(
      "href",
      "/processo/proc-1"
    );
  });

  it("sem destino o nome fica TEXTO e não um link morto", async () => {
    prepararFetch(
      quadro({
        solicitadas: [
          { ...PEDIDO_DO_PORTAL, process_id: "", client_id: "" },
        ],
        agendadas: [],
        total: 1,
      })
    );
    montar();
    await screen.findByRole("table");
    expect(screen.getByText("Ana Martins")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Ana Martins" })
    ).not.toBeInTheDocument();
  });
});

describe("o estado da extracção", () => {
  it("diz que está a ler o anúncio enquanto a extracção corre", async () => {
    prepararFetch(
      quadro({
        solicitadas: [{ ...PEDIDO_DO_PORTAL, scraper_status: "pending" }],
        agendadas: [],
        total: 1,
      })
    );
    montar();
    expect(await screen.findByText(/a ler o anúncio/i)).toBeInTheDocument();
  });

  it("um anúncio que respondeu VAZIO diz-se — não finge sucesso", async () => {
    // O terceiro veredicto. Antes contava como `completed` e a linha
    // ficava sem dados e sem explicação.
    prepararFetch(
      quadro({
        solicitadas: [
          {
            ...PEDIDO_DO_PORTAL,
            scraper_status: "sem_dados",
            scraped_price: null,
            scraped_typology: "",
            scraped_area: null,
            scraped_estado: "",
            property_address: null,
            scraped_data: {},
          },
        ],
        agendadas: [],
        total: 1,
      })
    );
    montar();
    expect(await screen.findByText(/anúncio sem dados/i)).toBeInTheDocument();
  });

  it("uma falha de leitura diz-se", async () => {
    prepararFetch(
      quadro({
        solicitadas: [{ ...PEDIDO_DO_PORTAL, scraper_status: "error" }],
        agendadas: [],
        total: 1,
      })
    );
    montar();
    expect(await screen.findByText(/não consegui ler/i)).toBeInTheDocument();
  });

  it("uma visita sem URL não mostra estado de extracção nenhum", async () => {
    // Um relógio numa visita criada à mão dizia que o sistema estava a
    // trabalhar quando não estava.
    prepararFetch(
      quadro({
        solicitadas: [],
        agendadas: [
          { ...AGENDADA, scraped_url: "", scraper_status: "pending" },
        ],
        total: 1,
      })
    );
    montar();
    await screen.findByRole("table");
    expect(screen.queryByText(/a ler o anúncio/i)).not.toBeInTheDocument();
  });
});

describe("a forma dos dados do servidor", () => {
  it("uma resposta sem colunas nenhumas não rebenta a página", async () => {
    // Era o defeito: `useState([])` + `visits.solicitadas` undefined.
    //
    // A ESPERA é sobre o estado vazio e não sobre o `layout`: o `layout`
    // existe desde o primeiro render (envolve também "A carregar
    // visitas...") e `findByTestId` resolve-o nesse estado intermédio,
    // deixando o `getByText` que vinha a seguir a correr contra o ecrã
    // de carregamento. Passava numa máquina rápida e falhava no CI
    // carregado — a lição do `WebmailCompanyTabs`, aqui do lado do
    // teste: o "Sem visitas" só existe quando tem o que dizer, logo a
    // PRESENÇA dele é a afirmação e é nela que se espera.
    prepararFetch({ total: 0 });
    montar();
    expect(await screen.findByText(/sem visitas/i)).toBeInTheDocument();
    expect(screen.queryByText(/a carregar visitas/i)).not.toBeInTheDocument();
  });

  it("enquanto carrega mostra o carregamento e NÃO o estado vazio", async () => {
    // A contraprova do teste acima: sem ela, trocar o estado vazio por
    // um render imediato tornava a espera supérflua sem ninguém notar.
    // Três estados (a carregar / vazio / com dados) são três condições,
    // e o do meio tem de ser distinguível dos outros dois.
    // Só o pedido do QUADRO fica pendurado: os outros (`fetchFormData`)
    // respondem logo, senão o `resolver` era o do último pedido feito.
    let resolverOQuadro;
    globalThis.fetch = vi.fn((url) => {
      if (String(url).includes("/visits/kanban")) {
        return new Promise((r) => {
          resolverOQuadro = () => r({ ok: true, json: async () => ({ total: 0 }) });
        });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    });
    montar();
    expect(await screen.findByText(/a carregar visitas/i)).toBeInTheDocument();
    expect(screen.queryByText(/sem visitas/i)).not.toBeInTheDocument();

    resolverOQuadro();
    expect(await screen.findByText(/sem visitas/i)).toBeInTheDocument();
  });

  it("uma resposta em ARRAY também é entendida", async () => {
    prepararFetch([PEDIDO_DO_PORTAL, AGENDADA]);
    montar();
    await screen.findByRole("table");
    expect(screen.getByText("T3 em Cascais com vista mar")).toBeInTheDocument();
  });

  it("uma coluna que venha como OBJECTO não vira lista", async () => {
    // `|| []` devolvia o objecto (truthy) e o `.filter` rebentava noutro
    // sítio — só `Array.isArray` distingue.
    prepararFetch(quadro({ solicitadas: { 0: PEDIDO_DO_PORTAL } }));
    montar();
    await screen.findByRole("table");
    expect(
      screen.queryByText("T3 em Cascais com vista mar")
    ).not.toBeInTheDocument();
    expect(screen.getByText("T2 em Leiria")).toBeInTheDocument();
  });
});

describe("as contagens e a pesquisa", () => {
  it("os números do topo DERIVAM da lista e não do servidor", async () => {
    // O servidor diz `total: 999`; o ecrã mostra duas visitas.
    prepararFetch(quadro({ total: 999 }));
    montar();
    await screen.findByRole("table");
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });

  it("a pesquisa filtra a tabela", async () => {
    montar();
    await screen.findByRole("table");
    const campo = screen.getByPlaceholderText(/pesquisar/i);
    await userEvent.type(campo, "Leiria");
    await waitFor(() =>
      expect(
        screen.queryByText("T3 em Cascais com vista mar")
      ).not.toBeInTheDocument()
    );
    expect(screen.getByText("T2 em Leiria")).toBeInTheDocument();
  });
});

describe("o alternador de vista", () => {
  it("o quadro por estado continua alcançável", async () => {
    // Uma funcionalidade que estorva uma regra nova muda-se de sítio,
    // não se apaga.
    montar();
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "Quadro" }));
    await waitFor(() =>
      expect(screen.queryByRole("table")).not.toBeInTheDocument()
    );
    expect(screen.getByText("T2 em Leiria")).toBeInTheDocument();
  });

  it("o cartão do quadro também mostra a quem ligar", async () => {
    // A tabela é a vista por omissão, logo um teste que não troque de
    // vista NUNCA monta o `VisitCard` — e foi por páginas nunca montadas
    // que esta casa descobriu os defeitos do `WebmailPage` e da própria
    // `VisitsPage`.
    montar();
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "Quadro" }));
    await waitFor(() =>
      expect(screen.queryByRole("table")).not.toBeInTheDocument()
    );

    expect(screen.getByText("Predial Atlântico")).toBeInTheDocument();
    expect(screen.getByText("Marta Nunes")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /912 345 678/ })
    ).toHaveAttribute("href", "tel:+351912345678");
  });
});

describe("agendar um pedido do Portal", () => {
  it("o botão Agendar existe na linha do pedido e não na agendada", async () => {
    montar();
    const tabela = await screen.findByRole("table");
    const linhas = within(tabela).getAllByRole("row").slice(1);
    expect(
      within(linhas[0]).getByRole("button", { name: "Agendar" })
    ).toBeInTheDocument();
    expect(
      within(linhas[1]).queryByRole("button", { name: "Agendar" })
    ).not.toBeInTheDocument();
  });

  it("clicar em Agendar abre o diálogo de agendamento", async () => {
    montar();
    await screen.findByRole("table");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Agendar" }));
    // O diálogo é o do PORTAL (`ScheduleFromPortalDialog`): é a ligação
    // página ↔ tabela que este teste existe para provar, e um
    // `findByText` do título do imóvel encontraria a linha da tabela
    // também — ambíguo, e a provar outra coisa.
    const dialogo = await screen.findByRole("dialog");
    expect(dialogo).toHaveTextContent(/T3 em Cascais/i);
  });
});


describe("a coluna da agência e do comercial (LOTE 10)", () => {
  it("mostra a agência e o comercial de quem anuncia", async () => {
    // A pergunta que o consultor faz primeiro: «a quem ligo para marcar
    // a partilha?». A resposta já existia no sistema e não chegava ao
    // ecrã — é por isso que este teste monta a PÁGINA e não a célula.
    montar();
    const tabela = await screen.findByRole("table");

    expect(within(tabela).getByText("Predial Atlântico")).toBeInTheDocument();
    expect(within(tabela).getByText("Marta Nunes")).toBeInTheDocument();
  });

  it("a coluna existe no cabeçalho", async () => {
    montar();
    const tabela = await screen.findByRole("table");
    expect(
      within(tabela).getByRole("columnheader", { name: /agência \/ comercial/i })
    ).toBeInTheDocument();
  });

  it("o telefone é uma ligação `tel:` que marca", async () => {
    montar();
    const tabela = await screen.findByRole("table");

    const ligacao = within(tabela).getByRole("link", { name: /912 345 678/ });
    expect(ligacao).toHaveAttribute("href", "tel:+351912345678");
  });

  it("o email é uma ligação `mailto:`", async () => {
    montar();
    const tabela = await screen.findByRole("table");

    const ligacao = within(tabela).getByRole("link", {
      name: /marta\.nunes@predial-atlantico\.pt/i,
    });
    expect(ligacao).toHaveAttribute(
      "href",
      "mailto:marta.nunes@predial-atlantico.pt"
    );
  });

  it("uma visita ANTERIOR mostra o contacto que tem no `scraped_data`", async () => {
    montar();
    const tabela = await screen.findByRole("table");

    expect(within(tabela).getByText("Remax Leiria")).toBeInTheDocument();
    expect(within(tabela).getByText("Rui Agente")).toBeInTheDocument();
    expect(
      within(tabela).getByRole("link", { name: /931 111 111/ })
    ).toHaveAttribute("href", "tel:+351931111111");
  });

  it("sem contacto nenhum a célula diz «—» e não desenha ligações", async () => {
    prepararFetch(
      quadro({
        solicitadas: [
          {
            id: "v-sem-contacto",
            status: "solicitada",
            property_title: "Imóvel sem anunciante",
            client_name: "Carla Sousa",
            scraped_url: "https://www.exemplo.pt/x",
            scraper_status: "completed",
          },
        ],
        agendadas: [],
      })
    );
    montar();
    const tabela = await screen.findByRole("table");
    await within(tabela).findByText("Imóvel sem anunciante");

    // Nenhum `tel:` na tabela: sem número não se desenha a ligação.
    const telefones = within(tabela)
      .queryAllByRole("link")
      .filter((a) => String(a.getAttribute("href")).startsWith("tel:"));
    expect(telefones).toEqual([]);
  });

  it("a central da agência aparece ROTULADA quando não há directo", async () => {
    // Sem o rótulo, o consultor liga à recepção convencido de que fala
    // com quem vende o imóvel.
    prepararFetch(
      quadro({
        solicitadas: [
          {
            id: "v-so-central",
            status: "solicitada",
            property_title: "T1 em Aveiro",
            client_name: "Dora Pinto",
            scraped_url: "https://www.exemplo.pt/y",
            scraper_status: "completed",
            agency_name: "Imobiliária Central",
            agency_phone: "234567890",
          },
        ],
        agendadas: [],
      })
    );
    montar();
    const tabela = await screen.findByRole("table");

    const ligacao = within(tabela).getByRole("link", { name: /central/i });
    expect(ligacao).toHaveAttribute("href", "tel:+351234567890");
    expect(ligacao).toHaveTextContent("(central)");
  });

  it("a pesquisa encontra a visita pela agência", async () => {
    // A coluna não pode ser visível e não pesquisável.
    montar();
    await screen.findByRole("table");

    const caixa = screen.getByPlaceholderText(/pesquisar/i);
    await userEvent.type(caixa, "Predial");

    await waitFor(() => {
      const tabela = screen.getByRole("table");
      expect(within(tabela).getByText("Predial Atlântico")).toBeInTheDocument();
      expect(within(tabela).queryByText("Remax Leiria")).not.toBeInTheDocument();
    });
  });
});
