/**
 * Tempo real do Portal do Cliente — a lógica pura.
 *
 * As duas armadilhas que estes testes existem para fixar:
 *   1. o evento `portal_message` traz o conteúdo TRUNCADO a 200 caracteres,
 *      logo não pode ser o registo — é um sinal;
 *   2. o cliente recebe o ECO da sua própria mensagem (o backend difunde sem
 *      `exclude_user_id` nesse caminho), e a desduplicação tem de ser por
 *      **id** e não por `sender_type` — senão o titular 2 deixa de ver as
 *      mensagens do titular 1.
 */
import { describe, expect, it } from "vitest";

import {
  EVENTOS_DO_PORTAL,
  TEXTOS_DOS_MOTIVOS,
  avisoDoProgressoGov,
  construirUrlDoSocket,
  decidirDoEvento,
  mensagemJaConhecida,
} from "./portalRealtime";

describe("construirUrlDoSocket", () => {
  it("traduz http em ws e https em wss", () => {
    expect(construirUrlDoSocket("http://localhost:8001", "t1")).toBe(
      "ws://localhost:8001/api/ws/portal?token=t1",
    );
    expect(construirUrlDoSocket("https://api.exemplo.pt", "t1")).toBe(
      "wss://api.exemplo.pt/api/ws/portal?token=t1",
    );
  });

  it("um backend em https nunca produz um ws:// inseguro", () => {
    // O browser recusa um `ws://` a partir de uma página `https` com
    // "insecure WebSocket" — e isso só aparece no browser do cliente.
    const url = construirUrlDoSocket("https://api.exemplo.pt", "t1");
    expect(url.startsWith("wss://")).toBe(true);
  });

  it("apara barras finais da base", () => {
    expect(construirUrlDoSocket("http://localhost:8001///", "t1")).toBe(
      "ws://localhost:8001/api/ws/portal?token=t1",
    );
  });

  it("codifica o token na query string", () => {
    const url = construirUrlDoSocket("http://x.pt", "a b/c+d=");
    expect(url).toContain("token=a%20b%2Fc%2Bd%3D");
  });

  it("devolve null sem token — sem token o handshake é um 4002 garantido", () => {
    expect(construirUrlDoSocket("http://x.pt", null)).toBeNull();
    expect(construirUrlDoSocket("http://x.pt", "")).toBeNull();
  });

  it("devolve null sem base", () => {
    expect(construirUrlDoSocket("", "t1")).toBeNull();
    expect(construirUrlDoSocket(null, "t1")).toBeNull();
  });

  it("recusa uma base que já traga o prefixo /api (o defeito de produção)", () => {
    // O hook passava `API_BASE_URL`, que é `BACKEND_URL + "/api"`: o URL
    // saía `wss://…/api/api/ws/portal` e o socket do Portal NUNCA ligou em
    // produção. Nenhum dos testes deste ficheiro tinha visto isto porque
    // TODOS passavam uma base sem `/api` — validavam uma chamada que a
    // aplicação não faz.
    expect(construirUrlDoSocket("https://api.exemplo.pt/api", "t1")).toBeNull();
    expect(construirUrlDoSocket("https://api.exemplo.pt/api/", "t1")).toBeNull();
  });

  it("o caminho /api/ aparece UMA vez", () => {
    const url = construirUrlDoSocket("https://api.exemplo.pt", "t1");
    expect(url.match(/\/api\//g)).toHaveLength(1);
  });

  it("devolve null para uma base sem protocolo em vez de um URL inválido", () => {
    // `new WebSocket("api.exemplo.pt/...")` levanta SyntaxError — devolver
    // null deixa o polling ser o caminho, que é o degradado certo.
    expect(construirUrlDoSocket("api.exemplo.pt", "t1")).toBeNull();
    expect(construirUrlDoSocket("//api.exemplo.pt", "t1")).toBeNull();
  });
});

describe("mensagemJaConhecida — desduplicação por id", () => {
  const lista = [{ id: "m1" }, { id: "m2" }];

  it("reconhece uma mensagem que já está na lista", () => {
    expect(mensagemJaConhecida({ id: "m2" }, lista)).toBe(true);
  });

  it("não reconhece uma mensagem nova", () => {
    expect(mensagemJaConhecida({ id: "m9" }, lista)).toBe(false);
  });

  it("um evento sem id conta como novo — perder uma mensagem é pior que um GET a mais", () => {
    expect(mensagemJaConhecida({}, lista)).toBe(false);
    expect(mensagemJaConhecida({ id: null }, lista)).toBe(false);
  });

  it("aguenta lista vazia ou ausente", () => {
    expect(mensagemJaConhecida({ id: "m1" }, [])).toBe(false);
    expect(mensagemJaConhecida({ id: "m1" }, undefined)).toBe(false);
  });
});

describe("decidirDoEvento — mensagens", () => {
  const eco = {
    type: EVENTOS_DO_PORTAL.MENSAGEM,
    data: { id: "m1", sender_type: "client", content: "a minha mensagem" },
  };

  it("uma mensagem nova manda RECARREGAR e não insere o payload", () => {
    const decisao = decidirDoEvento(
      { type: EVENTOS_DO_PORTAL.MENSAGEM, data: { id: "m9", content: "x" } },
      { mensagens: [{ id: "m1" }] },
    );
    expect(decisao.recarregarMensagens).toBe(true);
    // Nada do payload entra no estado: o conteúdo vem truncado do servidor.
    expect(decisao).not.toHaveProperty("mensagens");
  });

  it("o ECO da própria mensagem não provoca recarga", () => {
    const decisao = decidirDoEvento(eco, { mensagens: [{ id: "m1" }] });
    expect(decisao.recarregarMensagens).toBe(false);
  });

  it("a mensagem de um CO-TITULAR provoca recarga, apesar de ser sender_type client", () => {
    // A armadilha: filtrar por `sender_type === "client"` calaria isto, e um
    // processo com dois titulares tem dois magic links.
    const decisao = decidirDoEvento(
      {
        type: EVENTOS_DO_PORTAL.MENSAGEM,
        data: { id: "m7", sender_type: "client", content: "sou o 2.º titular" },
      },
      { mensagens: [{ id: "m1" }] },
    );
    expect(decisao.recarregarMensagens).toBe(true);
  });

  it("a mensagem do staff provoca recarga", () => {
    const decisao = decidirDoEvento(
      {
        type: EVENTOS_DO_PORTAL.MENSAGEM,
        data: { id: "m8", sender_type: "staff", content: "Bom dia" },
      },
      { mensagens: [] },
    );
    expect(decisao.recarregarMensagens).toBe(true);
  });
});

describe("decidirDoEvento — progresso do Estado", () => {
  it("sucesso com documentos recarrega a lista e avisa", () => {
    const decisao = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { source: "auto_financas", estado: "concluido", documents_count: 3 },
    });
    expect(decisao.recarregarDocumentos).toBe(true);
    expect(decisao.aviso.tipo).toBe("sucesso");
    expect(decisao.aviso.texto).toContain("3 documentos");
    expect(decisao.aviso.texto).toContain("das Finanças");
  });

  it("sucesso com ZERO documentos avisa mas NÃO recarrega", () => {
    // Recarregar para não mostrar diferença nenhuma é um pedido a mais.
    const decisao = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { source: "auto_financas", estado: "concluido", documents_count: 0 },
    });
    expect(decisao.recarregarDocumentos).toBe(false);
    expect(decisao.aviso.tipo).toBe("sucesso");
  });

  it("um documento usa o singular", () => {
    const { aviso } = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { source: "auto_financas", estado: "concluido", documents_count: 1 },
    });
    expect(aviso.texto).toContain("1 documento ");
    expect(aviso.texto).not.toContain("documentos");
  });

  it("distingue a Segurança Social das Finanças", () => {
    const { aviso } = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { source: "auto_seguranca_social", estado: "concluido", documents_count: 2 },
    });
    expect(aviso.texto).toContain("da Segurança Social");
  });

  it("uma falha nunca recarrega documentos", () => {
    const decisao = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { source: "auto_financas", estado: "falhou", motivo: "indisponivel" },
    });
    expect(decisao.recarregarDocumentos).toBe(false);
    expect(decisao.aviso.tipo).toBe("erro");
  });

  it.each([
    "credenciais_invalidas",
    "confirmacao_necessaria",
    "confirmacao_expirada",
    "confirmacao_incorreta",
    "indisponivel",
  ])("o motivo %s tem texto próprio em pt-PT", (motivo) => {
    const { aviso } = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { estado: "falhou", motivo },
    });
    expect(aviso.texto).toBe(TEXTOS_DOS_MOTIVOS[motivo]);
    expect(aviso.texto.length).toBeGreaterThan(20);
  });

  it("um motivo DESCONHECIDO cai no genérico e nunca aparece cru", () => {
    // O backend já colapsa os erros internos, mas um motivo novo não pode
    // aparecer como identificador técnico no ecrã de um cliente.
    const { aviso } = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { estado: "falhou", motivo: "motivo_novo_do_backend" },
    });
    expect(aviso.texto).toBe(TEXTOS_DOS_MOTIVOS.indisponivel);
    expect(aviso.texto).not.toContain("motivo_novo_do_backend");
  });

  it("uma falha sem motivo também cai no genérico", () => {
    const { aviso } = decidirDoEvento({
      type: EVENTOS_DO_PORTAL.PROGRESSO_GOV,
      data: { estado: "falhou" },
    });
    expect(aviso.texto).toBe(TEXTOS_DOS_MOTIVOS.indisponivel);
  });

  it("avisoDoProgressoGov é usável isoladamente", () => {
    expect(avisoDoProgressoGov({ estado: "concluido", documents_count: 5 }).tipo).toBe(
      "sucesso",
    );
  });
});

describe("decidirDoEvento — tudo o resto não tem efeito", () => {
  it.each([
    "process_updated",
    "process_status_changed",
    "document_uploaded",
    "new_chat_message",
    "new_email",
    "task_progress",
    "relatorio_de_risco_interno",
  ])("o evento interno %s é ignorado", (tipo) => {
    const decisao = decidirDoEvento({ type: tipo, data: { qualquer: "coisa" } });
    expect(decisao).toEqual({
      recarregarMensagens: false,
      recarregarDocumentos: false,
      aviso: null,
    });
  });

  it("um envelope malformado não rebenta", () => {
    for (const envelope of [null, undefined, {}, { type: null }, { data: {} }]) {
      expect(decidirDoEvento(envelope)).toEqual({
        recarregarMensagens: false,
        recarregarDocumentos: false,
        aviso: null,
      });
    }
  });

  it("estes eventos nem chegam ao cliente — isto é a segunda linha", () => {
    // O servidor retém-nos por lista de permissão
    // (`ws_client_identity.EVENTOS_PERMITIDOS_AO_CLIENTE`). Um handler para
    // eles aqui seria código morto que sugere que chegam; o que existe é a
    // ausência de efeito, e é isso que estes testes fixam.
    expect(Object.values(EVENTOS_DO_PORTAL)).toEqual([
      "portal_message",
      "portal_gov_progress",
    ]);
  });
});
