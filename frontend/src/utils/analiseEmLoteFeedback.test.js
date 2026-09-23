/**
 * "VLM no Escuro" — a análise em lote nunca podia acabar em silêncio
 * (Lote 5, Prioridade 0).
 *
 * O SINTOMA: clicar em "Analisar Documentos", ver a barra correr, ver um
 * toast VERDE ("Análise completa! 3 documento(s) processado(s)") e o
 * Diálogo de Revisão Humana nunca abrir. Nada para reportar ao suporte.
 *
 * PORQUE É QUE O VERDE MENTIA: `documents_count` conta os documentos
 * ENVIADOS. Com a chave da OpenAI em falta ou a quota esgotada, os três
 * documentos falham um a um dentro do ciclo do analisador, o agregado
 * volta vazio e a contagem continua a dizer "3". O `extracted_data`
 * chegava como `{}` — e `{}` é truthy em JavaScript, por isso o teste
 * `if (result.extracted_data)` deixava passar o caso vazio.
 *
 * A REGRA: há três desfechos e cada um tem a sua palavra. Concluída com
 * dados (abre o diálogo), concluída sem nada a preencher (aviso, não
 * sucesso) e falhada (erro com o motivo). Um quarto desfecho — o
 * silêncio — não existe.
 */
import { describe, expect, it } from "vitest";

import { resumirAnaliseEmLote } from "./analiseEmLoteFeedback";

describe("resumirAnaliseEmLote — a IA nem chegou a ler", () => {
  it("todos os documentos falhados é ERRO, não sucesso", () => {
    const r = resumirAnaliseEmLote({
      documentsCount: 3,
      documentsSucceeded: 0,
      documentsFailed: [
        { file_name: "irs.pdf", error: "Chave de API não configurada" },
        { file_name: "recibo.pdf", error: "Chave de API não configurada" },
        { file_name: "cc.pdf", error: "Chave de API não configurada" },
      ],
    });
    expect(r.tipo).toBe("erro");
    expect(r.texto).toContain("3");
  });

  it("o motivo da falha chega ao utilizador", () => {
    // Sem isto o consultor não tem nada para dizer a quem o pode
    // resolver — que é, precisamente, o que "no escuro" quer dizer.
    const r = resumirAnaliseEmLote({
      documentsCount: 1,
      documentsSucceeded: 0,
      documentsFailed: [{ file_name: "irs.pdf", error: "Quota esgotada" }],
    });
    expect(r.texto).toContain("Quota esgotada");
  });

  it("uma falha parcial avisa e não celebra", () => {
    const r = resumirAnaliseEmLote({
      documentsCount: 3,
      documentsSucceeded: 2,
      documentsFailed: [{ file_name: "cc.pdf", error: "Formato não suportado" }],
    });
    expect(r.tipo).toBe("aviso");
    expect(r.texto).toContain("cc.pdf");
  });
});

describe("resumirAnaliseEmLote — leu mas não trouxe nada", () => {
  it("sem campos para rever é AVISO", () => {
    // O caso que ficava mudo: a IA correu, não reconheceu nada de útil,
    // `prepararRevisaoDaExtraccao` devolveu null e o diálogo não abriu.
    const r = resumirAnaliseEmLote({
      documentsCount: 2,
      documentsSucceeded: 2,
      documentsFailed: [],
      temRevisao: false,
    });
    expect(r.tipo).toBe("aviso");
    expect(r.texto.length).toBeGreaterThan(0);
  });

  it("com campos para rever é SUCESSO", () => {
    const r = resumirAnaliseEmLote({
      documentsCount: 2,
      documentsSucceeded: 2,
      documentsFailed: [],
      temRevisao: true,
    });
    expect(r.tipo).toBe("sucesso");
    expect(r.texto).toContain("2");
  });
});

describe("resumirAnaliseEmLote — degradação graciosa", () => {
  it("uma resposta antiga sem os campos novos não parte", () => {
    // O backend pode estar num deploy anterior: sem
    // `documents_succeeded`, vale o que sempre valeu (`documents_count`).
    const r = resumirAnaliseEmLote({ documentsCount: 2, temRevisao: true });
    expect(r.tipo).toBe("sucesso");
  });

  it("sem argumentos nenhuns devolve sempre uma mensagem", () => {
    const r = resumirAnaliseEmLote();
    expect(r.tipo).toBeTruthy();
    expect(typeof r.texto).toBe("string");
    expect(r.texto.length).toBeGreaterThan(0);
  });

  it("nunca devolve um tipo fora dos três desfechos", () => {
    // Contraprova do desenho: o silêncio não é um valor possível.
    const casos = [
      { documentsCount: 0 },
      { documentsCount: 1, documentsSucceeded: 1, temRevisao: false },
      { documentsCount: 1, documentsSucceeded: 0, documentsFailed: [{}] },
    ];
    for (const caso of casos) {
      expect(["sucesso", "aviso", "erro"]).toContain(resumirAnaliseEmLote(caso).tipo);
    }
  });
});
