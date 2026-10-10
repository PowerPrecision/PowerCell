/** `yarn gerar:portal-escuro` — regenera `src/styles/portalEscuro.css` a partir das fontes do Portal. */
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  FICHEIROS_DO_PORTAL,
  PASTAS_DO_PORTAL,
  extrairClasses,
  gerarCss,
} from "../src/styles/portalEscuroGerador.mjs";

const src = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

const fontes = [...FICHEIROS_DO_PORTAL];
for (const pasta of PASTAS_DO_PORTAL) {
  for (const nome of readdirSync(join(src, pasta))) {
    const caminho = join(pasta, nome);
    if (/\.(jsx|js)$/.test(nome) && !/\.test\./.test(nome) && statSync(join(src, caminho)).isFile()) {
      fontes.push(caminho);
    }
  }
}

const classes = extrairClasses(fontes.map((f) => readFileSync(join(src, f), "utf-8")));
writeFileSync(join(src, "styles", "portalEscuro.css"), gerarCss(classes));
console.log(`portalEscuro.css gerado: ${classes.length} classes de ${fontes.length} ficheiros.`);
