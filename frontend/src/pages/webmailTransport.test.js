/**
 * Guarda: o Webmail tem de falar pelo cliente Axios.
 *
 * O MESMO INCIDENTE, SEXTA INSTÂNCIA (2026-09-21 → Set 2026).
 *   `WebmailPage.jsx` fazia 28 chamadas `fetch` cruas, e o
 *   `useWebmailEmails` mais uma. Todas passavam por um `webmailHeaders()`
 *   que escrevia `Authorization`, `X-Company-Id` e `X-Active-Role` à mão
 *   — uma função inteira a reimplementar o interceptor, que é o sinal
 *   mais claro de que o transporte estava no sítio errado.
 *
 *   No Webmail o custo é maior do que em qualquer das cinco instâncias
 *   anteriores: sem `X-Company-Id`, `get_active_company_id_async` cai em
 *   `user.company` (o NOME, não o id), a config de email por empresa não
 *   é encontrada, e a caixa mostrada passa a ser a de outro perfil. Foi
 *   este o sintoma do incidente original — o email de teste funcionava
 *   (ia por Axios) e o envio para balcões falhava (ia por `fetch`).
 *
 * Este ficheiro afirma sobre o CÓDIGO-FONTE de propósito: um teste de
 * comportamento com o transporte falseado não vê a diferença entre um
 * `fetch` e um `api.get` — e a diferença é exactamente o ponto.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));

/**
 * Remove comentários antes de procurar padrões proibidos.
 *
 * Sem isto, o comentário que EXPLICA porque é que o cabeçalho não se
 * escreve à mão fazia o guarda ficar vermelho — e a saída óbvia seria
 * apagar a explicação, que é a parte que impede a regressão de voltar.
 */
const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const ler = (...partes) =>
  semComentarios(readFileSync(join(AQUI, ...partes), "utf8"));

const PAGINA = ler("WebmailPage.jsx");
const HOOK = ler("..", "hooks", "useWebmailEmails.js");
const API = ler("..", "services", "api.js");

describe("O Webmail não faz `fetch` cru", () => {
  it("a página não tem uma única chamada `fetch(`", () => {
    const ocorrencias = PAGINA.match(/\bfetch\s*\(/g) || [];
    expect(ocorrencias).toHaveLength(0);
  });

  it("o hook da lista também não", () => {
    // É o pedido MAIS importante do ecrã: é o que traz os emails.
    const ocorrencias = HOOK.match(/\bfetch\s*\(/g) || [];
    expect(ocorrencias).toHaveLength(0);
  });

  it("ninguém volta a escrever os cabeçalhos de contexto à mão", () => {
    // `X-Company-Id` e `X-Active-Role` são do interceptor. Vê-los aqui
    // significa que alguém reabriu o caminho do `fetch`.
    for (const fonte of [PAGINA, HOOK]) {
      expect(fonte).not.toContain("X-Company-Id");
      expect(fonte).not.toContain("X-Active-Role");
    }
  });

  it("não sobra um `Authorization: Bearer` escrito à mão", () => {
    for (const fonte of [PAGINA, HOOK]) {
      expect(fonte).not.toMatch(/Bearer\s*\$\{/);
    }
  });

  it("o literal do URL do backend não é repetido na página", () => {
    // Regra de Set 2026: o URL vive em `utils/apiBaseUrl.js`. Repetido
    // aqui sem fallback, um build sem a variável pedia a
    // `undefined/api/...` — em silêncio.
    expect(PAGINA).not.toContain("process.env.REACT_APP_BACKEND_URL");
    expect(HOOK).not.toContain("process.env.REACT_APP_BACKEND_URL");
  });
});

describe("Contraprova: as funções de transporte existem mesmo", () => {
  // Sem isto, apagar as chamadas todas satisfazia as guardas acima.
  const OBRIGATORIAS = [
    "getWebmailEmails",
    "getWebmailStats",
    "getWebmailCompanies",
    "syncWebmail",
    "getEmailLabels",
    "getEmailFolders",
    "markEmail",
    "sendWebmailEmail",
    "downloadWebmailAttachment",
  ];

  it.each(OBRIGATORIAS)("`%s` está exportada em services/api.js", (nome) => {
    expect(API).toContain(`export const ${nome}`);
  });

  it("a página importa mesmo do cliente Axios", () => {
    expect(PAGINA).toMatch(/from\s+"\.\.\/services\/api"/);
  });

  it("o anexo pede `blob` e lê o corpo de erro como tal", () => {
    // `responseType: "blob"` faz o corpo de ERRO vir também como Blob;
    // sem `readBlobErrorBody` a mensagem do servidor desaparecia.
    const inicio = API.indexOf("export const downloadWebmailAttachment");
    const corpo = API.slice(inicio, API.indexOf("export const ", inicio + 1));
    expect(corpo).toContain('responseType: "blob"');
    expect(API).toContain("export const readBlobErrorBody");
  });
});
