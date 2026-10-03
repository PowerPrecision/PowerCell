/**
 * A LIGAÇÃO dos botões fantasma (Lote 6, ponto 3).
 *
 * O comportamento está provado no teste do `BotaoComPermissao` e nas regras
 * puras do `utils/capacidades`. O que falta provar é que os ecrãs REAIS passam
 * por lá — sem isto, o componente é correcto e o botão continua a aparecer a
 * quem não pode, que é exactamente o defeito relatado.
 *
 * PORQUE É UMA GUARDA SOBRE A FONTE E NÃO UM RENDER
 * =================================================
 * A Pool TEM teste montado (`ClientRegistrationsPage.poolAccoes`), porque já
 * tinha o arnês. Montar a `ProcessesPage` e a `KanbanPage` é um trabalho
 * próprio (fetchers, filtros, Kanban com medição de elementos) e fica
 * registado como tal; entretanto, a pergunta "este botão passa pelo gate?" é
 * respondível pela fonte com precisão — e com a CONTRAPROVA ao lado: que não
 * sobrou nenhum `<Button>` cru com o mesmo rótulo, e que o papel usado é o
 * EFECTIVO e não o do JWT.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, it, expect } from "vitest";

// `import.meta.url` e não `__dirname`: o projecto é ESM e o `__dirname` não
// existe — o ESLint apanhou-o com `no-undef`, que neste repositório é ERRO e
// bloqueia o CI.
const AQUI = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(AQUI, "..", "..");

const ECRAS = [
  { ficheiro: "pages/ProcessesPage.js", nome: "Listagem de Processos" },
  { ficheiro: "pages/KanbanPage.js", nome: "Kanban" },
];

const ROTULOS_GUARDADOS = ["Novo Processo", "Exportar Excel"];

/**
 * O ficheiro SEM comentários.
 *
 * Isto não é zelo: a primeira versão desta guarda ficou vermelha por ler o
 * comentário que eu próprio escrevi a explicar o gate ANTIGO
 * (`userRole !== "indexacao"`). Uma guarda que leia comentários proíbe a
 * explicação do defeito que previne, e a saída óbvia quando fica vermelha é
 * apagar a explicação — exactamente o contrário do que se quer. É a mesma
 * regra do `helpers_fonte.py` do backend, do lado do JS.
 *
 * O corte do `//` é por linha e sobre o texto APARADO, para não decapitar um
 * `https://` dentro de uma string.
 */
const semComentarios = (texto) =>
  texto
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((linha) => !linha.trim().startsWith("//"))
    .join("\n");

const fonte = (ficheiro) =>
  semComentarios(fs.readFileSync(path.join(RAIZ, ficheiro), "utf-8"));

/**
 * Os blocos `<Tag ...>…</Tag>` de um componente, com aninhamento do MESMO
 * nome tratado. Um `indexOf` simples do fecho dava o bloco errado quando há
 * dois botões seguidos.
 */
function blocosDe(texto, tag) {
  const blocos = [];
  const abre = new RegExp(`<${tag}[\\s>]`, "g");
  let m;
  while ((m = abre.exec(texto)) !== null) {
    let i = m.index;
    let profundidade = 0;
    let fim = -1;
    const passo = new RegExp(`<${tag}[\\s>]|</${tag}>`, "g");
    passo.lastIndex = i;
    let t;
    while ((t = passo.exec(texto)) !== null) {
      if (t[0].startsWith(`</`)) {
        profundidade -= 1;
        if (profundidade === 0) {
          fim = t.index + t[0].length;
          break;
        }
      } else {
        profundidade += 1;
      }
    }
    if (fim > i) {
      blocos.push(texto.slice(i, fim));
      abre.lastIndex = fim;
    }
  }
  return blocos;
}

describe("os ecrãs passam pelo gate de permissões", () => {
  it.each(ECRAS)("$nome importa o botão com permissão", ({ ficheiro }) => {
    expect(fonte(ficheiro)).toContain(
      'import BotaoComPermissao from "../components/shared/BotaoComPermissao"'
    );
  });

  it.each(ECRAS)("$nome: os rótulos guardados vivem num BotaoComPermissao", ({ ficheiro }) => {
    const texto = fonte(ficheiro);
    const guardados = blocosDe(texto, "BotaoComPermissao").join("\n");
    for (const rotulo of ROTULOS_GUARDADOS) {
      expect(guardados).toContain(rotulo);
    }
  });

  it.each(ECRAS)("$nome: CONTRAPROVA — nenhum <Button> cru com esses rótulos", ({ ficheiro }) => {
    // Sem esta, acrescentar o componente ao lado do botão antigo satisfazia o
    // teste acima e o botão continuava a aparecer.
    const crus = blocosDe(fonte(ficheiro), "Button").join("\n");
    for (const rotulo of ROTULOS_GUARDADOS) {
      expect(crus).not.toContain(rotulo);
    }
  });

  it.each(ECRAS)("$nome: o papel é o EFECTIVO, nunca o do JWT", ({ ficheiro }) => {
    // É a lição do `history._is_stealth_user` e do botão de eliminar cliente:
    // a porta do servidor lê o papel efectivo, e um gate pelo cargo base dá as
    // duas respostas erradas.
    for (const bloco of blocosDe(fonte(ficheiro), "BotaoComPermissao")) {
      expect(bloco).toContain("papel={effectiveRole}");
      expect(bloco).not.toContain("papel={user.role}");
      expect(bloco).not.toContain('papel={user?.role}');
    }
  });

  it.each(ECRAS)("$nome: cada botão guardado declara uma capacidade", ({ ficheiro }) => {
    for (const bloco of blocosDe(fonte(ficheiro), "BotaoComPermissao")) {
      expect(bloco).toMatch(/capacidade=\{[A-Z_]+\}/);
    }
  });
});

describe("a Pool usa um registo POSITIVO, não uma lista de exclusão", () => {
  const POOL = "pages/ClientRegistrationsPage.js";

  it("o gate deriva de `podeFazer`", () => {
    expect(fonte(POOL)).toContain("podeFazer(user, CRIAR_PROCESSO, papelActivo)");
  });

  it("CONTRAPROVA — a exclusão escrita à mão desapareceu", () => {
    // `userRole !== "indexacao"` tinha dois defeitos: um perfil novo sem
    // direito a criar processos passava a ver o botão (a exclusão não o
    // conhece) e o papel lido era o do JWT.
    expect(fonte(POOL)).not.toContain('userRole !== "indexacao"');
  });
});

describe("o removedor de comentários lê mesmo", () => {
  it("corta um comentário de bloco e um de linha", () => {
    expect(semComentarios("/* x */\ncodigo\n// y\n")).not.toContain("x");
    expect(semComentarios("/* x */\ncodigo\n// y\n")).not.toContain("y");
    expect(semComentarios("/* x */\ncodigo\n// y\n")).toContain("codigo");
  });

  it("NÃO decapita um URL dentro de uma string", () => {
    expect(semComentarios('const u = "https://a.pt";')).toContain("https://a.pt");
  });
});

describe("o leitor de blocos lê mesmo", () => {
  it("apanha blocos irmãos sem os colar", () => {
    const texto = "<A x>um</A>\n<A y>dois</A>";
    expect(blocosDe(texto, "A")).toHaveLength(2);
    expect(blocosDe(texto, "A")[0]).toContain("um");
    expect(blocosDe(texto, "A")[1]).toContain("dois");
  });

  it("apanha aninhamento do mesmo nome", () => {
    const blocos = blocosDe("<A p><A q>dentro</A></A>", "A");
    expect(blocos[0]).toBe("<A p><A q>dentro</A></A>");
  });

  it("devolve vazio quando a tag não existe", () => {
    expect(blocosDe("<B/>", "A")).toEqual([]);
  });
});
