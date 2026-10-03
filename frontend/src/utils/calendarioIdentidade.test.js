/**
 * De quem é o evento e para onde se vai (Lote 7, ponto 3).
 *
 * O backend devolve `client_name` desde o Pacote DQ e o ecrã mostrava-o só
 * no painel do dia, como texto morto. Estes testes afirmam as duas peças
 * separadas: o que se MOSTRA e para onde se VAI.
 */
import { describe, expect, it } from "vitest";
import {
  eEventoDeCliente,
  etiquetaDoCliente,
  resumoDoChip,
  rotaDaFicha,
  textoDaFicha,
} from "./calendarioIdentidade";

const DE_PROCESSO = {
  id: "ev1",
  title: "Escritura",
  type: "event",
  process_id: "p1",
  client_id: "c1",
  client_name: "Ana Martins",
};

const DE_CLIENTE_SEM_PROCESSO = {
  id: "ev2",
  title: "Primeira reunião",
  type: "event",
  client_id: "c9",
  client_name: "Rui Pereira",
};

const AUSENCIA = {
  id: "ev3",
  title: "Férias",
  type: "absence",
  client_name: "Ausência",
  responsible_name: "Quem Falta",
};

describe("eEventoDeCliente", () => {
  it("uma ausência não é de um cliente — é de uma pessoa", () => {
    expect(eEventoDeCliente(AUSENCIA)).toBe(false);
    for (const tipo of ["ausencia", "ausência", "ferias", "férias", "ABSENCE"]) {
      expect(eEventoDeCliente({ ...DE_PROCESSO, type: tipo })).toBe(false);
    }
  });

  it("um evento sem processo nem cliente é um evento geral", () => {
    expect(eEventoDeCliente({ id: "x", type: "event", title: "Reunião interna" }))
      .toBe(false);
  });

  it("basta o cliente, sem processo", () => {
    expect(eEventoDeCliente(DE_CLIENTE_SEM_PROCESSO)).toBe(true);
  });

  it("não rebenta com entrada vazia", () => {
    expect(eEventoDeCliente(null)).toBe(false);
    expect(eEventoDeCliente(undefined)).toBe(false);
  });
});

describe("etiquetaDoCliente", () => {
  it("devolve o nome do cliente", () => {
    expect(etiquetaDoCliente(DE_PROCESSO)).toBe("Ana Martins");
  });

  it("ignora os RECUOS que o backend escreve em client_name", () => {
    // `_enrich_calendar_rows` escreve "Evento Geral" e "Ausência" quando não
    // há processo. Mostrá-los punha «Evento Geral» debaixo de cada bloco de
    // agenda, como se fosse o nome de alguém.
    expect(etiquetaDoCliente({ ...DE_PROCESSO, client_name: "Evento Geral" })).toBe("");
    expect(etiquetaDoCliente({ ...DE_PROCESSO, client_name: "Ausência" })).toBe("");
  });

  it("uma ausência não tem etiqueta de cliente", () => {
    expect(etiquetaDoCliente(AUSENCIA)).toBe("");
  });
});

describe("rotaDaFicha", () => {
  it("prefere o PROCESSO — é onde está a documentação e a timeline", () => {
    expect(rotaDaFicha(DE_PROCESSO)).toBe("/processo/p1");
  });

  it("cai no cliente quando não há processo (o caso da Pool)", () => {
    expect(rotaDaFicha(DE_CLIENTE_SEM_PROCESSO)).toBe("/cliente/c9");
  });

  it("devolve null quando não há para onde ir", () => {
    // Quem recebe null não desenha a ligação: um link que não leva a lado
    // nenhum é pior do que texto.
    expect(rotaDaFicha(AUSENCIA)).toBeNull();
    expect(rotaDaFicha({ id: "x", type: "event", title: "Interna" })).toBeNull();
    expect(rotaDaFicha(null)).toBeNull();
  });

  it("escapa o id no caminho", () => {
    expect(rotaDaFicha({ ...DE_PROCESSO, process_id: "a/b" })).toBe("/processo/a%2Fb");
  });
});

describe("textoDaFicha", () => {
  it("diz o destino e não «ver»", () => {
    expect(textoDaFicha(DE_PROCESSO)).toBe("Abrir processo");
    expect(textoDaFicha(DE_CLIENTE_SEM_PROCESSO)).toBe("Abrir ficha do cliente");
  });
});

describe("resumoDoChip", () => {
  it("na vista de EQUIPA o cliente vem primeiro", () => {
    // Doze «Escritura» num dia não dizem de quem são.
    expect(resumoDoChip({ ...DE_PROCESSO, title: "Escritura" }, { isTeamView: true }))
      .toBe("Ana Martins · Escritura");
  });

  it("não repete o nome quando o título já o contém", () => {
    expect(
      resumoDoChip({ ...DE_PROCESSO, title: "Escritura Ana Martins" }, { isTeamView: true }),
    ).toBe("Escritura Ana Martins");
  });

  it("na agenda PESSOAL mostra só o título", () => {
    // O utilizador já sabe que é dele; o cliente aparece no painel do dia.
    expect(resumoDoChip(DE_PROCESSO, { isTeamView: false })).toBe("Escritura");
  });

  it("um evento sem cliente mostra o título", () => {
    expect(resumoDoChip(AUSENCIA, { isTeamView: true })).toBe("Férias");
  });

  it("sem título usa um recuo em vez de ficar vazio", () => {
    expect(resumoDoChip({ id: "x", type: "event" }, { isTeamView: true }))
      .toBe("Agendamento");
    expect(resumoDoChip({ id: "x", type: "event", title: "   " }, { isTeamView: true }))
      .toBe("Agendamento");
  });
});
