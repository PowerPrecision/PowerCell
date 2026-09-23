/**
 * Guarda: o menu e as rotas têm de concordar sobre quem entra onde.
 *
 * O DEFEITO QUE ISTO FECHA
 *   `DashboardLayout` mostrava "Os Meus Clientes" ao perfil Diretora (o
 *   grupo "O Meu Negócio" é explicitamente dela), mas a rota
 *   `/meus-clientes` em `App.js` não tinha `diretor` nas `allowedRoles`.
 *   `ProtectedRoute` mandava para `/staff` — o utilizador clicava num item
 *   do PRÓPRIO menu e era devolvido ao Dashboard, sem explicação.
 *
 * É o pior tipo de erro de permissões: não é "não tens acesso", é o
 * produto a contradizer-se. E não dá erro nenhum — nem no build, nem no
 * eslint, nem em runtime.
 *
 * PORQUÊ SOBRE O CÓDIGO-FONTE
 *   As duas listas vivem em ficheiros diferentes e nada as liga. Um teste
 *   de comportamento teria de montar o layout e o router por cada perfil;
 *   esta afirmação cruza as duas listas directamente e diz qual divergiu.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));
const APP = readFileSync(join(AQUI, "App.js"), "utf8");
const LAYOUT = readFileSync(join(AQUI, "layouts", "DashboardLayout.js"), "utf8");

/** Mapa `path` → `allowedRoles` declarado em App.js. */
function rotasComPapeis(fonte) {
  const rotas = new Map();
  const re = /path="([^"]+)"([\s\S]{0,600}?)(?:<Route|$)/g;
  let m;
  while ((m = re.exec(fonte)) !== null) {
    const [, caminho, bloco] = m;
    const ar = bloco.match(/allowedRoles=\{\[([\s\S]*?)\]\}/);
    if (ar) {
      rotas.set(caminho, [...ar[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]));
    }
  }
  return rotas;
}

/** Hrefs que o menu mostra a um dado perfil. */
function hrefsDoPerfil(fonte, perfil) {
  // O layout declara os blocos de duas maneiras: um perfil sozinho
  // (`userRole === "diretor"`) ou vários partilhados
  // (`["consultor","intermediario"].includes(userRole)`). Ler só a
  // primeira dava zero itens para consultor/intermediário — e um teste
  // que não lê nada passa sempre.
  // Admin e CEO NÃO têm ramo `if`: o menu deles é o fall-through no fim
  // da função (`const adminGroups = [...]`). Sem isto o extractor
  // devolvia lista vazia para os dois — e como o guarda do Lote 3 só
  // iterava diretor/consultor/intermediário, a lacuna era invisível.
  const aberturas = ["admin", "ceo"].includes(perfil)
    ? ["const adminGroups = ["]
    : [
        `if (userRole === "${perfil}")`,
        ...[...fonte.matchAll(/if \(\[([^\]]*)\]\.includes\(userRole\)\)/g)]
          .filter((m) => m[1].includes(`"${perfil}"`))
          .map((m) => m[0]),
      ];

  const inicio = aberturas
    .map((abertura) => fonte.indexOf(abertura))
    .find((i) => i !== -1);
  if (inicio === undefined || inicio === -1) return [];

  const fim = fonte.indexOf("if (", inicio + 30);
  const bloco = fonte.slice(inicio, fim === -1 ? undefined : fim);

  const hrefs = new Set(
    [...bloco.matchAll(/href:\s*"([^"]+)"/g)].map((x) => x[1]),
  );

  // Grupos referenciados por nome (ex.: `meuNegocioGroup`) — as entradas
  // deles contam como visíveis para este perfil.
  const grupos = new Set(
    [...bloco.matchAll(/(\w+Group)/g)].map((x) => x[1]),
  );
  for (const grupo of grupos) {
    const i = fonte.indexOf(`const ${grupo} = {`);
    if (i === -1) continue;
    const j = fonte.indexOf("\n    };", i);
    for (const x of fonte.slice(i, j).matchAll(/href:\s*"([^"]+)"/g)) {
      hrefs.add(x[1]);
    }
  }

  // Terceira forma de declarar um item, acrescentada no Lote 5: um
  // spread condicional dentro de um grupo partilhado —
  //   ...(["admin","ceo"].includes(userRole) ? [{ href: "/x" }] : [])
  // É a maneira de um grupo comum ter uma entrada restrita. Sem ler
  // isto, o item conta como visível para TODOS os perfis que usam o
  // grupo, e o guarda acusa uma divergência que não existe.
  for (const spread of fonte.matchAll(
    /\.\.\.\(\[([^\]]*)\]\.includes\(userRole\)\s*\?([\s\S]*?):\s*\[\]\)/g,
  )) {
    const permitidos = spread[1];
    for (const x of spread[2].matchAll(/href:\s*"([^"]+)"/g)) {
      if (!permitidos.includes(`"${perfil}"`)) hrefs.delete(x[1]);
    }
  }

  return [...hrefs];
}

const ROTAS = rotasComPapeis(APP);

describe("O leitor do spread condicional", () => {
  // Contraprova do que foi acrescentado no Lote 5: o leitor novo TIRA
  // itens de perfis. Se tirasse a mais, o guarda ficava cego — passaria
  // por não ver nada, que é o pior estado possível para uma guarda.
  it("o item restrito aparece a quem o pode abrir", () => {
    assert.ok(
      hrefsDoPerfil(LAYOUT, "admin").includes("/ficheiros"),
      "o explorador global desapareceu do menu do admin",
    );
  });

  it("e desaparece de quem não o pode abrir", () => {
    for (const perfil of ["consultor", "intermediario", "diretor"]) {
      assert.ok(
        !hrefsDoPerfil(LAYOUT, perfil).includes("/ficheiros"),
        `${perfil} continua a ver o explorador global no menu`,
      );
    }
  });
});

describe("Coerência entre o menu e as rotas", () => {
  it("a extracção das rotas encontrou alguma coisa", () => {
    // Sem isto, um erro na regex daria um teste que passa sempre.
    assert.ok(ROTAS.size > 5, `só ${ROTAS.size} rotas com allowedRoles`);
    assert.ok(ROTAS.has("/meus-clientes"), "rota /meus-clientes não encontrada");
  });

  for (const perfil of ["admin", "ceo", "diretor", "consultor", "intermediario"]) {
    it(`o perfil "${perfil}" consegue abrir tudo o que o menu lhe mostra`, () => {
      const hrefs = hrefsDoPerfil(LAYOUT, perfil);
      assert.ok(hrefs.length > 0, `nenhum item de menu lido para ${perfil}`);

      const bloqueadas = hrefs
        .filter((href) => {
          const papeis = ROTAS.get(href);
          return papeis && !papeis.includes(perfil);
        })
        .map((href) => `${href} (allowedRoles: ${ROTAS.get(href).join(", ")})`);

      assert.deepEqual(
        bloqueadas,
        [],
        `O menu mostra a "${perfil}" itens que a rota recusa:\n  ` +
          bloqueadas.join("\n  ") +
          "\nOu o item sai do menu, ou o papel entra nas allowedRoles.",
      );
    });
  }

  it("Os Meus Clientes aceita os perfis com carteira", () => {
    const papeis = ROTAS.get("/meus-clientes");
    for (const perfil of ["consultor", "intermediario", "diretor"]) {
      assert.ok(papeis.includes(perfil), `${perfil} em falta em /meus-clientes`);
    }
  });
});
