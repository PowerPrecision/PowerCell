#!/usr/bin/env node
/**
 * Corredor dos testes unitários do frontend (`node --test`).
 *
 * PORQUÊ UM SCRIPT E NÃO `node --test src/`:
 * - os padrões glob no `node --test` só existem a partir do Node 22, e o CI
 *   corre Node 20 — enumerar os ficheiros aqui funciona em ambos;
 * - deixar a expansão a cargo da shell tornaria o comando dependente do SO.
 *
 * Uso:
 *   yarn test              → corre todos os ficheiros *.test.js/jsx em src/
 *   yarn test utils        → corre apenas os ficheiros cujo caminho contém "utils"
 */
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const raizFrontend = fileURLToPath(new URL("..", import.meta.url));
const raizSrc = join(raizFrontend, "src");
const PADRAO = /\.test\.(js|jsx)$/;
const IGNORAR = new Set(["node_modules", "dist", "build", ".vite"]);

/**
 * Lista recursivamente os ficheiros de teste sob um directório.
 * @param {string} dir
 * @returns {string[]}
 */
function encontrarTestes(dir) {
  const encontrados = [];
  for (const entrada of readdirSync(dir)) {
    if (IGNORAR.has(entrada)) continue;
    const caminho = join(dir, entrada);
    if (statSync(caminho).isDirectory()) {
      encontrados.push(...encontrarTestes(caminho));
    } else if (PADRAO.test(entrada)) {
      encontrados.push(caminho);
    }
  }
  return encontrados;
}

const filtros = process.argv.slice(2);
const ficheiros = encontrarTestes(raizSrc)
  .filter((f) => filtros.length === 0 || filtros.some((p) => f.includes(p)))
  .sort();

if (ficheiros.length === 0) {
  console.error(`Nenhum ficheiro de teste encontrado${filtros.length ? ` para: ${filtros.join(", ")}` : ""}.`);
  process.exit(1);
}

console.log(`A correr ${ficheiros.length} ficheiros de teste...`);
const resultado = spawnSync(
  process.execPath,
  ["--test", ...ficheiros.map((f) => relative(raizFrontend, f))],
  { cwd: raizFrontend, stdio: "inherit" },
);

process.exit(resultado.status ?? 1);
