/**
 * O Explorador fala por Axios, zero `fetch` cru (Épico 10, Gestor S3).
 *
 * Era a 7.ª instância do incidente de 2026-09-21: um `fetch` cru não leva
 * o `X-Company-Id` nem o `X-Active-Role`, porque o interceptor vive no
 * cliente Axios (`services/api.js`). Enquanto a página era só de admin isso
 * não pesava; num endpoint cujo RESULTADO depende do contexto — a pasta de
 * outra rede responde 404 — passou a pesar.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// `new URL(..., import.meta.url)` não resolve para um caminho de ficheiro
// no ambiente jsdom — o padrão do projecto é este.
const AQUI = dirname(fileURLToPath(import.meta.url));

const PAGINA = readFileSync(join(AQUI, "FilesExplorerPage.jsx"), "utf8");
const API = readFileSync(join(AQUI, "..", "services", "api.js"), "utf8");

// Ignora comentários de propósito: a explicação da regra menciona `fetch`,
// e uma guarda que lesse comentários proibiria a própria explicação.
function semComentarios(fonte) {
  return fonte
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((linha) => linha.replace(/\/\/.*$/, ""))
    .join("\n");
}

describe("transporte do Explorador de Ficheiros", () => {
  it("não faz uma única chamada fetch", () => {
    expect(semComentarios(PAGINA)).not.toMatch(/\bfetch\s*\(/);
  });

  it("não reconstrói o URL do backend à mão", () => {
    const codigo = semComentarios(PAGINA);
    expect(codigo).not.toContain("REACT_APP_BACKEND_URL");
    expect(codigo).not.toMatch(/\/api\/admin\/s3-/);
  });

  it("as seis operações têm função de API própria", () => {
    // Contraprova: uma página sem `fetch` porque deixou de fazer pedidos
    // satisfaria o teste de cima sem provar nada.
    for (const nome of [
      "getS3FolderContents",
      "uploadS3ExplorerFile",
      "downloadS3ExplorerFile",
      "renameS3ExplorerEntry",
      "deleteS3ExplorerEntry",
      "createS3ExplorerFolder",
    ]) {
      expect(API).toContain(`export const ${nome}`);
      expect(PAGINA).toContain(nome);
    }
  });

  it("o download pede blob e lê o corpo de erro como blob", () => {
    // `responseType: "blob"` faz o corpo de ERRO vir também como Blob: sem
    // `readBlobErrorBody`, a mensagem do servidor desaparece em silêncio.
    const bloco = API.slice(API.indexOf("export const downloadS3ExplorerFile"));
    expect(bloco.slice(0, 300)).toContain('responseType: "blob"');
    expect(PAGINA).toContain("readBlobErrorBody");
  });

  it("o upload não escreve Content-Type", () => {
    // A predefinição da instância é `application/json` e o Axios converte
    // o FormData em JSON — o interceptor trata disto num ponto só.
    // Sem `semComentarios`, o comentário que EXPLICA a regra fazia a
    // guarda ficar vermelha — e a saída óbvia seria apagar a explicação,
    // que é a parte que impede a regressão de voltar.
    const bloco = semComentarios(API).slice(
      semComentarios(API).indexOf("export const uploadS3ExplorerFile"),
      semComentarios(API).indexOf("export const downloadS3ExplorerFile"),
    );
    expect(bloco).not.toContain("Content-Type");
  });

  it("a página distingue 404 de 403", () => {
    // 404 = pasta fora da rede (não existe, do ponto de vista de quem pede).
    // 403 = sem permissão para a página. Dizer "sem permissões" a um 404
    // confirmaria que a pasta existe.
    expect(PAGINA).toMatch(/estado === 404/);
    expect(PAGINA).toMatch(/estado === 403/);
  });
});
