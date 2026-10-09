/**
 * O separador activo escolhe UMA secção — a página montada a sério.
 *
 * Erro de produção: abrir "Limiares de SLA" deixava o ecrã em BRANCO, com a
 * pilha a apontar para o `ConfigSection` (o cartão genérico), não para a
 * secção nova. A causa é uma lista de EXCLUSÃO no render:
 *
 *     {activeTab !== "document_recipients" && activeTab !== "maintenance"
 *       && … && activeTab !== "changelog" && <ConfigSection … />}
 *
 * Uma lista negativa faz cada separador NOVO entrar por omissão no cartão
 * genérico. O `dashboard_slas` não estava lá, logo renderizava-se a par da
 * secção dedicada, com `section={fields["dashboard_slas"]}` — `undefined` —
 * e o `ConfigSection` rebenta em `section.title`.
 *
 * É a mesma forma do "Menu e rotas têm de concordar": a informação está em
 * dois sítios (a lista de exclusão e os `activeTab === …`) e divergem sem dar
 * erro. Hoje é um REGISTO positivo, ponto único: um separador é dedicado ou
 * genérico, nunca os dois, e acrescentar um obriga a decidir.
 *
 * Este teste monta a PÁGINA. O da secção (`SlaThresholdsSection.test.jsx`)
 * passava com o defeito presente, porque montava só a folha — é a regra do
 * `WebmailPage`, e falhei-a ao acrescentar o separador.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t",
    user: { id: "u1", name: "Admin", role: "admin" },
    effectiveCompanyId: "default",
  }),
}));

vi.mock("../../services/api", () => ({
  // Forma REAL de `GET /system-config/companies`: `{companies, total}`.
  getSystemConfigCompanies: vi.fn(async () => ({ data: { companies: [], total: 0 } })),
  getSystemConfig: vi.fn(async () => ({
    data: { config: { dashboard_slas: { enabled: true, novo: 7, analise: 15, aprovado: 30 } } },
  })),
  updateSystemConfigSection: vi.fn(async () => ({ data: {} })),
}));

import SystemConfigPage, {
  SECCOES_DEDICADAS,
  SECCOES_NA_NAVEGACAO,
} from "../SystemConfigPage";

// A forma REAL de `GET /api/system-config` (ver `run_get_config`):
// `{config, fields}` — e NÃO a configuração no topo. Foi assumi-la errada que
// produziu o segundo defeito desta iteração.
const RESPOSTA_REAL = {
  config: {
    storage: { provider: "s3" },
    dashboard_slas: { enabled: true, novo: 7, analise: 15, aprovado: 30 },
  },
  fields: {
    storage: {
      title: "Armazenamento",
      description: "Provedor de ficheiros",
      fields: [{ key: "provider", label: "Provedor", type: "text" }],
    },
  },
};

function montar(tab) {
  return render(
    <MemoryRouter initialEntries={[`/configuracoes?tab=${tab}`]}>
      <SystemConfigPage embedded />
    </MemoryRouter>,
  );
}

describe("SystemConfigPage — o separador activo escolhe UMA secção", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => RESPOSTA_REAL,
      })),
    );
  });

  it("o separador dos SLAs mostra a secção dedicada", async () => {
    montar("dashboard_slas");
    expect(await screen.findByTestId("sla-thresholds-section")).toBeTruthy();
  });

  it("e NÃO renderiza o cartão genérico por cima", async () => {
    // Era isto que rebentava: o genérico recebia `section: undefined` e
    // morria em `section.title`, levando a página inteira.
    montar("dashboard_slas");
    await screen.findByTestId("sla-thresholds-section");
    expect(screen.queryByTestId("config-section-generica")).toBeNull();
  });

  it("um separador genérico continua a mostrar o cartão genérico", async () => {
    // Contraprova: sem ela, bastava deixar de renderizar o `ConfigSection`
    // para este ficheiro passar todo.
    montar("storage");
    const cartao = await screen.findByTestId("config-section-generica");
    // Dentro do CARTÃO: "Armazenamento" também é o rótulo do botão de
    // navegação, e um `getByText` global casava com os dois.
    expect(cartao.textContent).toContain("Armazenamento");
    expect(cartao.textContent).toContain("Provedor de ficheiros");
    expect(screen.queryByTestId("sla-thresholds-section")).toBeNull();
  });

  it("um `?tab=` desconhecido diz-se, em vez de deixar a área vazia", async () => {
    // O separador vem do URL (`searchParams.get("tab")`), logo um favorito
    // antigo pode pedir uma secção que já não existe. Antes, isso entrava no
    // cartão genérico com `section: undefined` — o mesmo crash, por outra
    // porta, e esta é controlada por quem visita.
    montar("uma_seccao_que_nunca_existiu");

    expect(await screen.findByTestId("config-seccao-desconhecida")).toBeTruthy();
    expect(screen.queryByTestId("config-section-generica")).toBeNull();
  });

  it("nenhuma secção dedicada aparece também na navegação genérica", async () => {
    // A navegação é `Object.keys(fields)`. Uma chave que esteja nos DOIS
    // sítios dava um separador que o registo intercepta e o genérico nunca
    // mostra — o defeito ao contrário, silencioso.
    const { SECCOES_DEDICADAS } = await import("../SystemConfigPage");
    const dedicadas = Object.keys(SECCOES_DEDICADAS);

    expect(dedicadas).toContain("dashboard_slas");
    for (const chave of dedicadas) {
      expect(
        Object.keys(RESPOSTA_REAL.fields),
        `"${chave}" é dedicada e não pode ter metadados de campos`,
      ).not.toContain(chave);
    }
  });

  it("os valores gravados chegam ao ecrã — não as omissões", async () => {
    // Terceiro defeito: a secção lia `res.data.dashboard_slas` em vez de
    // `res.data.config.dashboard_slas`, logo mostrava sempre 7/15/30 fossem
    // quais fossem os valores gravados.
    const api = await import("../../services/api");
    api.getSystemConfig.mockResolvedValue({
      data: {
        config: { dashboard_slas: { enabled: false, novo: 3, analise: 21, aprovado: 45 } },
      },
    });

    montar("dashboard_slas");

    await waitFor(() => {
      expect(screen.getByTestId("sla-novo")).toHaveValue("3");
    });
    expect(screen.getByTestId("sla-analise")).toHaveValue("21");
    expect(screen.getByTestId("sla-aprovado")).toHaveValue("45");
    expect(screen.getByTestId("sla-enabled")).toHaveAttribute("aria-checked", "false");
  });
});

// ====================================================================
// As TRÊS navegações derivam do mesmo registo (Lote 6, ponto 1)
// ====================================================================
// O separador "Limiares de SLA" existia só na barra lateral (`lg:block`).
// Num ecrã estreito — onde só vivem o `<Select>` e a fila de chips — ele
// DESAPARECIA. Não era overflow: a fila já rolava; um item que não é
// renderizado não se alcança com scroll nenhum.
//
// Estes testes afirmam sobre o REGISTO e sobre o que é renderizado, e
// falham por omissão para qualquer secção nova que fique fora de uma das
// navs — o que os três blocos escritos à mão nunca conseguiriam garantir.
describe("a navegação das secções dedicadas", () => {
  it("toda a secção oferecida na nav tem componente em SECCOES_DEDICADAS", () => {
    for (const { key } of SECCOES_NA_NAVEGACAO) {
      expect(SECCOES_DEDICADAS[key]).toBeTruthy();
    }
  });

  it("os Limiares de SLA estão na lista (contraprova do registo)", () => {
    // Sem esta âncora, um registo VAZIO passaria o teste de cima.
    expect(SECCOES_NA_NAVEGACAO.map((s) => s.key)).toContain("dashboard_slas");
    expect(SECCOES_NA_NAVEGACAO.length).toBeGreaterThanOrEqual(5);
  });

  it("cada secção da nav é renderizada nas duas superfícies (lateral e chips)", async () => {
    // O jsdom não aplica media queries de Tailwind, pelo que AMBAS as
    // navegações existem na árvore. É exactamente isso que permite
    // verificá-las: cada secção tem de ter o botão da barra lateral E o
    // chip do ecrã estreito.
    montar("storage");
    await waitFor(() => expect(screen.getByTestId("nav-dashboard-slas")).toBeInTheDocument());

    for (const { key } of SECCOES_NA_NAVEGACAO) {
      const sufixo = key.replace(/_/g, "-");
      expect(screen.getByTestId(`nav-${sufixo}`)).toBeInTheDocument();
      expect(screen.getByTestId(`chip-${sufixo}`)).toBeInTheDocument();
    }
  });

  it("o chip do ecrã estreito abre a secção", async () => {
    montar("storage");
    await waitFor(() => expect(screen.getByTestId("chip-dashboard-slas")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("chip-dashboard-slas"));

    await waitFor(() =>
      expect(screen.getByTestId("sla-thresholds-section")).toBeInTheDocument(),
    );
  });
});
