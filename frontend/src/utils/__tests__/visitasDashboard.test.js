/**
 * O quadro de Visitas: a forma, as contagens e as regras de navegação.
 *
 * O DEFEITO QUE ESTE MÓDULO FECHA (Lote 9, Fase B)
 * ================================================
 * A `VisitsPage` tinha `useState([])` — um ARRAY — e o endpoint
 * `/visits/kanban` devolve um OBJECTO com quatro colunas. No primeiro
 * render `visits.solicitadas` é `undefined`, e só um `|| []` por coluna
 * impedia o `.filter` de rebentar; o `total` vinha do servidor e
 * contradizia o ecrã depois de uma pesquisa em memória.
 *
 * É a forma do `KanbanBoard` da D-20, e as regras são as mesmas:
 * `Array.isArray` nunca `|| []`, a forma normaliza-se UMA vez, e as
 * contagens DERIVAM das listas.
 */
import { describe, expect, it } from "vitest";

import {
  COLUNAS,
  QUADRO_VAZIO,
  colunaDoEstado,
  dadosDaIA,
  estadoDaExtraccao,
  extraccaoEmCurso,
  filtrarQuadro,
  linhasDaTabela,
  normalizarQuadro,
  resumoDoQuadro,
  rotaDaFicha,
  temDadosDaIA,
  textoDaFicha,
  tituloDoImovel,
  visitaCasaComPesquisa,
} from "../visitasDashboard";

const visita = (extra = {}) => ({
  id: "v1",
  status: "agendada",
  property_title: "T2 em Leiria",
  client_name: "Ana Martins",
  process_id: "proc-1",
  client_id: "proc-1",
  scheduled_date: "2026-11-20T15:00:00Z",
  scraped_url: "https://www.idealista.pt/imovel/1/",
  scraper_status: "completed",
  scraped_price: 185000,
  scraped_typology: "T2",
  scraped_area: 95,
  scraped_estado: "usado",
  ...extra,
});

describe("normalizarQuadro", () => {
  it("devolve as quatro colunas mesmo sem dados nenhuns", () => {
    const quadro = normalizarQuadro(undefined);
    COLUNAS.forEach((coluna) => {
      expect(Array.isArray(quadro[coluna])).toBe(true);
    });
  });

  it("um OBJECTO em vez de um array não vira a lista", () => {
    // `|| []` devolvia o objecto (é truthy) e o erro mudava de sítio em
    // vez de desaparecer — só `Array.isArray` distingue.
    const quadro = normalizarQuadro({ solicitadas: { 0: visita() } });
    expect(quadro.solicitadas).toEqual([]);
  });

  it("aceita também um ARRAY e distribui pelo estado", () => {
    // `/visits` devolve uma lista e `/visits/kanban` um objecto: a página
    // não tem de saber de que endpoint vieram os dados.
    const quadro = normalizarQuadro([
      visita({ id: "a", status: "solicitada" }),
      visita({ id: "b", status: "agendada" }),
      visita({ id: "c", status: "recusada" }),
    ]);
    expect(quadro.solicitadas.map((v) => v.id)).toEqual(["a"]);
    expect(quadro.agendadas.map((v) => v.id)).toEqual(["b"]);
    expect(quadro.canceladas.map((v) => v.id)).toEqual(["c"]);
  });

  it("o QUADRO_VAZIO tem a forma que o estado inicial precisa", () => {
    expect(resumoDoQuadro(QUADRO_VAZIO).total).toBe(0);
    expect(() => linhasDaTabela(QUADRO_VAZIO)).not.toThrow();
  });

  it("uma coluna desconhecida não entra no quadro", () => {
    const quadro = normalizarQuadro({ inventada: [visita()] });
    expect(Object.keys(quadro).sort()).toEqual([...COLUNAS].sort());
  });
});

describe("colunaDoEstado", () => {
  it("recusada vive com as canceladas", () => {
    expect(colunaDoEstado("recusada")).toBe("canceladas");
  });

  it("aceita a grafia com acento", () => {
    expect(colunaDoEstado("concluída")).toBe("concluidas");
    expect(colunaDoEstado("concluida")).toBe("concluidas");
  });

  it("um estado desconhecido não desaparece do quadro", () => {
    // Cair numa coluna é melhor do que a linha evaporar-se: uma visita
    // que desaparece não produz erro nenhum.
    expect(COLUNAS).toContain(colunaDoEstado("inventado"));
  });
});

describe("resumoDoQuadro", () => {
  it("o total DERIVA das listas e não do servidor", () => {
    const quadro = {
      solicitadas: [visita({ id: "a" })],
      agendadas: [visita({ id: "b" }), visita({ id: "c" })],
      total: 99, // o que o servidor dizia
    };
    const resumo = resumoDoQuadro(quadro);
    expect(resumo.total).toBe(3);
    expect(resumo.solicitadas).toBe(1);
    expect(resumo.agendadas).toBe(2);
  });

  it("depois de uma pesquisa o total acompanha o ecrã", () => {
    const quadro = {
      agendadas: [
        visita({ id: "a", property_title: "T2 em Leiria" }),
        visita({ id: "b", property_title: "T3 no Porto" }),
      ],
      total: 2,
    };
    const filtrado = filtrarQuadro(quadro, "porto");
    expect(resumoDoQuadro(filtrado).total).toBe(1);
  });
});

describe("filtrarQuadro", () => {
  it("sem termo devolve tudo, com a forma normalizada", () => {
    const quadro = filtrarQuadro({ agendadas: [visita()] }, "");
    expect(quadro.agendadas).toHaveLength(1);
    expect(quadro.solicitadas).toEqual([]);
  });

  it("procura nos campos do anúncio e não só no título", () => {
    expect(visitaCasaComPesquisa(visita({ scraped_estado: "remodelado" }), "remodel")).toBe(true);
    expect(visitaCasaComPesquisa(visita(), "leiria")).toBe(true);
    expect(visitaCasaComPesquisa(visita(), "nada disto")).toBe(false);
  });

  it("procura também no scraped_data dos registos ANTIGOS", () => {
    // Nada se migra: uma visita anterior a este lote só tem o
    // `scraped_data`, e deixar de a encontrar era perder histórico.
    const antiga = {
      id: "velha",
      status: "agendada",
      scraped_data: { title: "Moradia em Óbidos", location: "Óbidos" },
    };
    expect(visitaCasaComPesquisa(antiga, "óbidos")).toBe(true);
  });

  it("um campo ausente não rebenta a pesquisa", () => {
    expect(visitaCasaComPesquisa({}, "x")).toBe(false);
    expect(visitaCasaComPesquisa(null, "x")).toBe(false);
  });
});

describe("estadoDaExtraccao", () => {
  it("sem URL não há extracção nenhuma a mostrar", () => {
    // Um ícone de relógio numa visita criada à mão dizia que o sistema
    // estava a trabalhar quando não estava.
    expect(estadoDaExtraccao(visita({ scraped_url: "", scraper_status: "pending" })))
      .toBe("sem_url");
  });

  it("distingue os cinco estados", () => {
    expect(estadoDaExtraccao(visita({ scraper_status: "pending" }))).toBe("pendente");
    expect(estadoDaExtraccao(visita({ scraper_status: "completed" }))).toBe("ok");
    expect(estadoDaExtraccao(visita({ scraper_status: "sem_dados" }))).toBe("sem_dados");
    expect(estadoDaExtraccao(visita({ scraper_status: "error" }))).toBe("erro");
  });

  it("sem_dados NÃO mantém o polling vivo", () => {
    // O veredicto novo não é «pendente»: tratá-lo como tal fazia a página
    // recarregar de 3 em 3 segundos durante um minuto, para sempre.
    const quadro = { agendadas: [visita({ scraper_status: "sem_dados" })] };
    expect(extraccaoEmCurso(quadro)).toBe(false);
  });

  it("uma extracção pendente mantém o polling", () => {
    const quadro = { solicitadas: [visita({ scraper_status: "pending" })] };
    expect(extraccaoEmCurso(quadro)).toBe(true);
  });
});

describe("dadosDaIA", () => {
  it("lê os campos de topo que este lote criou", () => {
    const dados = dadosDaIA(visita());
    expect(dados.preco).toBe(185000);
    expect(dados.tipologia).toBe("T2");
    expect(dados.area).toBe(95);
    expect(dados.estado).toBe("usado");
  });

  it("cai no scraped_data dos registos ANTERIORES", () => {
    const antiga = {
      scraped_data: {
        price: 250000,
        typology: "T3",
        area: 120,
        location: "Porto",
        raw_data: { estado: "novo" },
      },
    };
    const dados = dadosDaIA(antiga);
    expect(dados.preco).toBe(250000);
    expect(dados.tipologia).toBe("T3");
    expect(dados.estado).toBe("novo");
    expect(dados.localizacao).toBe("Porto");
  });

  it("um preço ZERO é um valor e não uma ausência", () => {
    // `?? ` e não `||`: com `||` o zero virava `null` e a célula dizia
    // «—» em vez de «0 €» (a armadilha do `|| 30` do Kanban).
    expect(dadosDaIA(visita({ scraped_price: 0 })).preco).toBe(0);
    expect(temDadosDaIA(visita({ scraped_price: 0 }))).toBe(true);
  });

  it("sem dados nenhuns responde que não tem", () => {
    expect(temDadosDaIA({ id: "x" })).toBe(false);
  });
});

describe("rotaDaFicha", () => {
  it("prefere o PROCESSO", () => {
    expect(rotaDaFicha(visita())).toBe("/processo/proc-1");
    expect(textoDaFicha(visita())).toBe("Abrir processo");
  });

  it("cai no cliente para quem vive na Pool sem processo", () => {
    const sem = visita({ process_id: "", client_id: "cli-9" });
    expect(rotaDaFicha(sem)).toBe("/cliente/cli-9");
    expect(textoDaFicha(sem)).toBe("Abrir ficha do cliente");
  });

  it("sem id nenhum devolve null — e quem recebe null não desenha o link", () => {
    expect(rotaDaFicha({ client_name: "Alguém" })).toBeNull();
  });

  it("concorda com a regra do CALENDÁRIO para a mesma entrada", async () => {
    // Duas cópias de uma regra de navegação divergem, e a que divergir
    // leva a um 404. O oráculo é a função de PRODUÇÃO do calendário,
    // nunca uma terceira escrita no teste.
    const calendario = await import("../calendarioIdentidade");
    const casos = [
      { process_id: "p", client_id: "c", client_name: "X" },
      { process_id: "", client_id: "c", client_name: "X" },
    ];
    casos.forEach((caso) => {
      expect(rotaDaFicha(caso)).toBe(calendario.rotaDaFicha(caso));
    });
  });

  it("o id vai escapado para o URL", () => {
    expect(rotaDaFicha({ process_id: "a/b" })).toBe("/processo/a%2Fb");
  });
});

describe("tituloDoImovel", () => {
  it("usa o título lido pela IA", () => {
    expect(tituloDoImovel(visita())).toBe("T2 em Leiria");
  });

  it("cai no URL legível quando a extracção ainda não correu", () => {
    const sem = visita({ property_title: "", scraped_data: undefined });
    expect(tituloDoImovel(sem)).toBe("www.idealista.pt/imovel/1/");
  });

  it("nunca devolve vazio", () => {
    expect(tituloDoImovel({})).toBe("Imóvel sem título");
  });
});

describe("linhasDaTabela", () => {
  it("põe os PEDIDOS primeiro, porque são os que precisam de acção", () => {
    // Ordenar por data punha os pedidos (que não têm data) no fim, onde
    // ninguém os vê — e um pedido que ninguém vê é a forma de defeito
    // desta casa.
    const quadro = {
      concluidas: [visita({ id: "feita", status: "concluida" })],
      agendadas: [visita({ id: "marcada", status: "agendada" })],
      solicitadas: [visita({ id: "pedida", status: "solicitada", scheduled_date: null })],
    };
    expect(linhasDaTabela(quadro).map((l) => l.id)).toEqual([
      "pedida", "marcada", "feita",
    ]);
  });

  it("dentro da mesma coluna ordena por data", () => {
    const quadro = {
      agendadas: [
        visita({ id: "tarde", scheduled_date: "2026-12-01T10:00:00Z" }),
        visita({ id: "cedo", scheduled_date: "2026-11-01T10:00:00Z" }),
      ],
    };
    expect(linhasDaTabela(quadro).map((l) => l.id)).toEqual(["cedo", "tarde"]);
  });

  it("não perde linhas nem as duplica", () => {
    const quadro = {
      solicitadas: [visita({ id: "a" })],
      agendadas: [visita({ id: "b" })],
      concluidas: [visita({ id: "c" })],
      canceladas: [visita({ id: "d" })],
    };
    const ids = linhasDaTabela(quadro).map((l) => l.id);
    expect(ids).toHaveLength(4);
    expect(new Set(ids).size).toBe(4);
  });
});
