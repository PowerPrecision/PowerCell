/**
 * Guarda: o gestor de ficheiros S3 tem de falar pelo cliente Axios.
 *
 * O MESMO INCIDENTE, QUARTA INSTÂNCIA (2026-09-21 → Set 2026).
 *   `S3FileManager` fazia 25 chamadas `fetch` cruas. Todas levavam o
 *   `Authorization` escrito à mão; TRÊS levavam também o `X-Active-Role`
 *   (sinal de que alguém já tinha tropeçado nisto); e NENHUMA levava o
 *   `X-Company-Id`.
 *
 *   Sem `X-Company-Id`, `get_active_company_id_async` cai em `user.company`
 *   — que é o NOME da empresa, não o id. Sem `X-Active-Role`, o backend
 *   resolve o papel pelo JWT e um utilizador multi-perfil leva 403 nas
 *   ferramentas de IA no perfil errado, apesar de as ver no ecrã.
 *
 *   O interceptor que injecta os dois vive no cliente Axios. É por isso que
 *   a regra do projecto não admite excepções: qualquer chamada que dependa
 *   de contexto de empresa ou papel vai por `api`, nunca por `fetch`.
 *
 * Este ficheiro afirma sobre o CÓDIGO-FONTE de propósito: um teste de
 * comportamento com o transporte falseado não vê a diferença entre um
 * `fetch` e um `api.get` — e a diferença é exactamente o ponto.
 *
 * Correr com: yarn test (Vitest); o alias de `node:test` traduz para a
 * API do Vitest.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));
const FONTE = readFileSync(join(AQUI, "S3FileManager.js"), "utf8");
const API = readFileSync(join(AQUI, "..", "services", "api.js"), "utf8");

/**
 * Remove comentários antes de procurar padrões proibidos.
 *
 * Sem isto, o próprio comentário que EXPLICA porque é que o cabeçalho não
 * se escreve à mão fazia o guarda ficar vermelho — e a saída óbvia seria
 * apagar a explicação, que é a parte que impede a regressão de voltar.
 */
const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const CODIGO = semComentarios(FONTE);
const API_CODIGO = semComentarios(API);

/**
 * Corpo de UMA função exportada, do seu `export const` até ao seguinte.
 *
 * Uma janela de N caracteres não serve: transbordava para a função a
 * seguir e dava por presente um `skipErrorToast` que era do vizinho — uma
 * mutação que o removesse da função certa continuava a passar.
 */
function corpoDaFuncao(fonte, nome) {
  const inicio = fonte.indexOf(`export const ${nome}`);
  if (inicio === -1) return "";
  const resto = fonte.slice(inicio + 1);
  const fim = resto.indexOf("export const ");
  return fim === -1 ? resto : resto.slice(0, fim);
}

describe("S3FileManager — transporte", () => {
  it("não faz UMA ÚNICA chamada fetch", () => {
    const ocorrencias = CODIGO.match(/\bfetch\s*\(/g) || [];
    assert.equal(
      ocorrencias.length,
      0,
      `encontradas ${ocorrencias.length} chamadas fetch: cada uma perde ` +
        "`X-Company-Id`/`X-Active-Role` e resolve empresa e papel errados",
    );
  });

  it("não volta a escrever cabeçalhos de contexto à mão", () => {
    // Escrever `X-Active-Role` à mão foi o remendo que escondeu o problema
    // real durante meses: três chamadas ficavam certas e as outras 22 não.
    assert.ok(
      !CODIGO.includes("X-Active-Role"),
      "o cabeçalho é injectado pelo interceptor; escrevê-lo à mão indica " +
        "que se voltou a contornar o cliente Axios",
    );
    assert.ok(!CODIGO.includes("X-Company-Id"));
  });

  it("não reconstrói o URL base do backend", () => {
    // `process.env.REACT_APP_BACKEND_URL` repetido é a origem do build de
    // dev a falar com a API de produção (ver utils/apiBaseUrl.js).
    assert.ok(
      !CODIGO.includes("REACT_APP_BACKEND_URL"),
      "o URL base vem do cliente Axios, que o resolve num ponto único",
    );
  });

  it("importa as funções de documentos do cliente Axios", () => {
    assert.ok(/from\s+["']\.\.\/services\/api["']/.test(FONTE));
    for (const funcao of [
      "getProcessS3Files",
      "uploadProcessS3File",
      "getS3FileContent",
      "aiAnalyzeS3Documents",
    ]) {
      assert.ok(FONTE.includes(funcao), `falta o import de ${funcao}`);
    }
  });
});

describe("Cliente Axios — o que o fetch contornava", () => {
  it("injecta X-Company-Id", () => {
    assert.ok(API.includes("X-Company-Id"));
  });

  it("injecta X-Active-Role", () => {
    assert.ok(API.includes("X-Active-Role"));
  });

  it("o 403 honra skipErrorToast", () => {
    // Sem isto, converter a listagem de ficheiros para Axios acrescentava
    // um toast global "Acesso Negado" por cima do aviso LOCALIZADO da tab
    // (PACOTE 11) — a mesma informação duas vezes, a segunda sem contexto.
    // Sobre o CÓDIGO, não sobre os comentários: uma mutação que trocasse
    // `if (!config?.skipErrorToast)` por `if (true)` continuaria a passar
    // enquanto o comentário acima mencionasse a variável.
    const bloco = API_CODIGO.slice(API_CODIGO.indexOf("if (status === 403)"));
    const corpo = bloco.slice(0, bloco.indexOf("if (status === 429)"));
    assert.ok(
      corpo.includes("skipErrorToast"),
      "o ramo do 403 tem de poder ser silenciado por pedido",
    );
  });
});

describe("Aviso localizado de permissão (PACOTE 11)", () => {
  it("a listagem de ficheiros pede para NÃO haver toast global", () => {
    // É este `skipErrorToast` que deixa o 403 chegar ao componente sem o
    // interceptor anunciar "Acesso Negado" por cima do aviso da tab.
    assert.ok(
      corpoDaFuncao(API_CODIGO, "getProcessS3Files").includes("skipErrorToast"),
      "sem isto o utilizador vê o aviso localizado E um toast genérico",
    );
  });

  it("o componente distingue o 403 dos restantes erros", () => {
    assert.ok(
      CODIGO.includes("setPermissionDenied(true)") &&
        /status === 403/.test(CODIGO),
      "o 403 tem de acender o painel localizado, não um toast",
    );
  });
});

describe("Proxy de conteúdo — o que evita o CORS do S3", () => {
  it("o conteúdo dos ficheiros vem pelo proxy do backend", () => {
    assert.ok(
      API.includes("/documents/proxy/"),
      "o download directo do bucket falha por falta de CORS; o proxy do " +
        "backend faz streaming e é por isso que existe",
    );
  });

  it("os pedidos de ficheiro pedem blob", () => {
    // Sem `responseType: "blob"` o Axios interpreta os bytes como texto e
    // o PDF chega corrompido à pré-visualização.
    assert.ok(
      corpoDaFuncao(API_CODIGO, "getS3FileContent").includes('responseType: "blob"'),
    );
  });

  it("o corpo de erro de um pedido blob é lido como texto", () => {
    // Com `responseType: "blob"`, o corpo de ERRO também vem como Blob:
    // `error.response.data.detail` fica undefined e a mensagem do servidor
    // (ex.: a lista de campos em falta na minuta) desaparece em silêncio.
    assert.ok(API.includes("readBlobErrorBody"));
    assert.ok(FONTE.includes("readBlobErrorBody"));
  });
});
