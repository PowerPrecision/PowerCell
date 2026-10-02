/**
 * O lote em envio tem NOMES (Lote 3, ponto 4).
 *
 * O DEFEITO
 * O Portal mostrava `2/5` durante o envio e, no fim, «2 erros no último
 * envio». Nunca um nome de ficheiro. Duas perdas concretas:
 *
 *   1. Durante o envio, um `2/5` não diz QUAL é o segundo.
 *   2. No fim, `errors[0].error` mostra a mensagem do PRIMEIRO erro e o
 *      cliente que envia 5 e tem 2 a falhar não sabe quais repetir.
 *
 * E do lado do servidor faltava o array: das TRÊS serializações do
 * `/portal/status`, só `received_docs` levava `attached_files` — pelo que
 * um pedido ainda incompleto mostrava lista nenhuma e o único nome no ecrã
 * era o campo `filename` de topo, ou seja O ÚLTIMO.
 */
import { describe, expect, it } from "vitest";

import {
  A_ENVIAR,
  A_ESPERA,
  ENVIADO,
  FALHOU,
  concluidos,
  criarLote,
  enviados,
  etiquetaDeProgresso,
  falhados,
  listaUnificada,
  marcar,
  resumirLote,
  terminado,
} from "./portalUploadStaging";

const ficheiro = (nome, size = 1024) => ({ name: nome, size });

describe("Criar o lote", () => {
  it("guarda o nome de TODOS os ficheiros, não só do último", () => {
    const lote = criarLote([ficheiro("cc.pdf"), ficheiro("irs.pdf"), ficheiro("recibo.pdf")]);
    expect(lote.map((i) => i.nome)).toEqual(["cc.pdf", "irs.pdf", "recibo.pdf"]);
  });

  it("começa tudo à espera", () => {
    const lote = criarLote([ficheiro("a.pdf"), ficheiro("b.pdf")]);
    expect(lote.every((i) => i.estado === A_ESPERA)).toBe(true);
  });

  it("dois ficheiros com o MESMO nome continuam a ser dois", () => {
    // Selecção legítima (pastas diferentes). A chave é a posição, não o nome.
    const lote = criarLote([ficheiro("cc.pdf"), ficheiro("cc.pdf")]);
    expect(lote).toHaveLength(2);
    expect(lote[0].id).not.toBe(lote[1].id);
  });

  it("não guarda o objecto File", () => {
    // Manter a referência prendia os bytes em memória depois do envio.
    const f = ficheiro("grande.pdf", 50_000_000);
    const [item] = criarLote([f]);
    expect(Object.values(item)).not.toContain(f);
    expect(item.tamanho).toBe(50_000_000);
  });

  it("uma selecção vazia dá um lote vazio", () => {
    expect(criarLote([])).toEqual([]);
    expect(criarLote(null)).toEqual([]);
    expect(criarLote(undefined)).toEqual([]);
  });

  it("aceita uma FileList (array-like)", () => {
    const fileListFalsa = { 0: ficheiro("a.pdf"), 1: ficheiro("b.pdf"), length: 2 };
    expect(criarLote(fileListFalsa).map((i) => i.nome)).toEqual(["a.pdf", "b.pdf"]);
  });
});

describe("Marcar o progresso por ficheiro", () => {
  it("marca só o ficheiro indicado", () => {
    const lote = criarLote([ficheiro("a.pdf"), ficheiro("b.pdf")]);
    const depois = marcar(lote, 1, A_ENVIAR);
    expect(depois[0].estado).toBe(A_ESPERA);
    expect(depois[1].estado).toBe(A_ENVIAR);
  });

  it("não muta o lote original", () => {
    const lote = criarLote([ficheiro("a.pdf")]);
    marcar(lote, 0, ENVIADO);
    expect(lote[0].estado).toBe(A_ESPERA);
  });

  it("guarda o erro NO ficheiro que falhou", () => {
    const lote = marcar(criarLote([ficheiro("a.pdf")]), 0, FALHOU, "ficheiro demasiado grande");
    expect(lote[0].erro).toBe("ficheiro demasiado grande");
  });
});

describe("Contagens", () => {
  const lote = [
    { nome: "a.pdf", estado: ENVIADO },
    { nome: "b.pdf", estado: FALHOU, erro: "erro b" },
    { nome: "c.pdf", estado: A_ENVIAR },
    { nome: "d.pdf", estado: A_ESPERA },
  ];

  it("concluídos conta enviados E falhados", () => {
    expect(concluidos(lote)).toBe(2);
  });

  it("falhados devolve os ficheiros, com nome", () => {
    expect(falhados(lote).map((i) => i.nome)).toEqual(["b.pdf"]);
  });

  it("enviados idem", () => {
    expect(enviados(lote).map((i) => i.nome)).toEqual(["a.pdf"]);
  });

  it("terminado só quando acabam todos", () => {
    expect(terminado(lote)).toBe(false);
    expect(terminado([{ estado: ENVIADO }, { estado: FALHOU }])).toBe(true);
  });

  it("um lote vazio não está terminado", () => {
    // Senão o resumo aparecia antes de haver envio nenhum.
    expect(terminado([])).toBe(false);
  });
});

describe("O resumo NOMEIA o que falhou", () => {
  it("tudo bem: diz quantos", () => {
    const lote = [{ nome: "a.pdf", estado: ENVIADO }, { nome: "b.pdf", estado: ENVIADO }];
    expect(resumirLote(lote)).toEqual({ tipo: "sucesso", texto: "2 ficheiros enviados." });
  });

  it("um só ficheiro fala no singular", () => {
    expect(resumirLote([{ nome: "a.pdf", estado: ENVIADO }]).texto).toBe("1 ficheiro enviado.");
  });

  it("falhou tudo: diz os NOMES e não «2 erros»", () => {
    const lote = [
      { nome: "cc.pdf", estado: FALHOU, erro: "rede" },
      { nome: "irs.pdf", estado: FALHOU, erro: "rede" },
    ];
    const r = resumirLote(lote);
    expect(r.tipo).toBe("erro");
    expect(r.texto).toContain("cc.pdf");
    expect(r.texto).toContain("irs.pdf");
    // A mensagem técnica fica disponível, mas não é o texto principal.
    expect(r.detalhe).toBe("rede");
  });

  it("parcial: diz quantos foram E quais falharam", () => {
    const lote = [
      { nome: "ok.pdf", estado: ENVIADO },
      { nome: "mau.pdf", estado: FALHOU, erro: "grande" },
    ];
    const r = resumirLote(lote);
    expect(r.tipo).toBe("parcial");
    expect(r.texto).toContain("1 enviado");
    expect(r.texto).toContain("mau.pdf");
  });

  it("com muitos falhados, nomeia os primeiros e conta os restantes", () => {
    // Trinta nomes numa linha não é informação, é ruído.
    const lote = Array.from({ length: 6 }, (_, i) => ({
      nome: `f${i}.pdf`,
      estado: FALHOU,
      erro: "x",
    }));
    const r = resumirLote(lote, { maximoDeNomes: 2 });
    expect(r.texto).toContain("f0.pdf");
    expect(r.texto).toContain("f1.pdf");
    expect(r.texto).toContain("+4");
    expect(r.texto).not.toContain("f5.pdf");
  });

  it("não resume um lote que ainda está a correr", () => {
    // Um resumo a meio lê-se como resultado final.
    expect(resumirLote([{ nome: "a", estado: A_ENVIAR }])).toBeNull();
  });

  it("nem um lote vazio", () => {
    expect(resumirLote([])).toBeNull();
    expect(resumirLote(null)).toBeNull();
  });
});

describe("A etiqueta de progresso", () => {
  it("com um ficheiro mostra a percentagem", () => {
    expect(etiquetaDeProgresso(criarLote([ficheiro("a.pdf")]), 42)).toBe("42%");
  });

  it("com vários mostra a contagem", () => {
    const lote = marcar(criarLote([ficheiro("a"), ficheiro("b"), ficheiro("c")]), 0, ENVIADO);
    expect(etiquetaDeProgresso(lote, 10)).toBe("2/3");
  });

  it("nunca passa do total", () => {
    // O "+1" do ficheiro em curso não pode anunciar 4/3 no último.
    let lote = criarLote([ficheiro("a"), ficheiro("b")]);
    lote = marcar(marcar(lote, 0, ENVIADO), 1, ENVIADO);
    expect(etiquetaDeProgresso(lote, 100)).toBe("2/2");
  });
});

describe("Uma só lista no ecrã", () => {
  const anexados = [
    { file_id: "1", filename: "cc.pdf", file_size: 2048, s3_path: "x/cc.pdf" },
  ];

  it("junta os do servidor com os do lote", () => {
    const lote = criarLote([ficheiro("irs.pdf")]);
    const lista = listaUnificada(anexados, lote);
    expect(lista.map((i) => i.nome)).toEqual(["cc.pdf", "irs.pdf"]);
  });

  it("não mostra o mesmo ficheiro duas vezes quando termina", () => {
    // Enviado no lote E já devolvido pelo refetch: duas listas lado a lado
    // mostravam-no duas vezes no instante da transição.
    const lote = marcar(criarLote([ficheiro("cc.pdf")]), 0, ENVIADO);
    expect(listaUnificada(anexados, lote)).toHaveLength(1);
  });

  it("mas um ficheiro do lote que FALHOU continua à vista", () => {
    // É o que o cliente precisa de ver para repetir.
    const lote = marcar(criarLote([ficheiro("cc.pdf")]), 0, FALHOU, "rede");
    const lista = listaUnificada(anexados, lote);
    expect(lista).toHaveLength(2);
    expect(lista[1].estado).toBe(FALHOU);
  });

  it("marca quem já está no servidor", () => {
    const lista = listaUnificada(anexados, []);
    expect(lista[0].noServidor).toBe(true);
    expect(lista[0].s3_path).toBe("x/cc.pdf");
  });

  it("sem nada devolve lista vazia", () => {
    expect(listaUnificada(null, null)).toEqual([]);
    expect(listaUnificada([], [])).toEqual([]);
  });
});
