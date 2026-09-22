/**
 * Resolução do URL base do backend — ponto ÚNICO.
 *
 * PORQUÊ ESTE MÓDULO EXISTE
 * -------------------------
 * Até aqui, seis ficheiros repetiam o mesmo padrão:
 *
 *   const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com";
 *
 * e o `define` do `vite.config.js` aplicava o mesmo fallback em tempo de
 * build. Consequência: um build de DEV sem `REACT_APP_BACKEND_URL` definido
 * apontava, em silêncio, para a API de PRODUÇÃO — sem erro, sem aviso, a
 * escrever dados reais de clientes a partir de uma sessão de desenvolvimento.
 * Isto viola a separação estrita dev/prod da infraestrutura (serviço Render e
 * bucket S3 dedicados por ambiente).
 *
 * REGRA
 * -----
 * 1. `REACT_APP_BACKEND_URL` definido  → é sempre essa (normalizada).
 * 2. Ausente, mas a correr num host local → `http://localhost:8001`.
 *    Um ambiente local NUNCA cai para produção por omissão.
 * 3. Ausente e em host remoto → fallback de produção (retrocompatibilidade
 *    com deploys antigos), com aviso audível na consola.
 *
 * O `vite.config.js` importa `resolveBuildTimeBackendUrl` para aplicar a
 * mesma regra em tempo de build; a regra vive num só sítio.
 */

/** Fallback histórico de produção. Mantido só para o caso 3. */
export const PRODUCTION_FALLBACK_URL = "https://powercell.onrender.com";

/** URL do backend local por omissão (uvicorn em `backend/`). */
export const LOCAL_FALLBACK_URL = "http://localhost:8001";

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"]);

/**
 * Um hostname é "local" se for loopback ou terminar em `.local`/`.localhost`.
 *
 * @param {string} [hostname]
 * @returns {boolean}
 */
export function isLocalHostname(hostname) {
  const host = String(hostname || "").trim().toLowerCase();
  if (!host) return false;
  if (LOCAL_HOSTNAMES.has(host)) return true;
  return host.endsWith(".local") || host.endsWith(".localhost");
}

/**
 * Normaliza um URL base: sem espaços e sem barras finais.
 *
 * @param {string} [url]
 * @returns {string}
 */
export function normalizeBaseUrl(url) {
  return String(url || "").trim().replace(/\/+$/, "");
}

/**
 * Aplica a regra descrita no topo do ficheiro.
 *
 * Função pura — recebe tudo o que precisa, para ser testável sem `window`
 * e reutilizável em tempo de build (Vite) e em tempo de execução (browser).
 *
 * @param {object} [options]
 * @param {string} [options.envUrl] Valor de `REACT_APP_BACKEND_URL`.
 * @param {string} [options.hostname] Host onde a app corre (ou vai correr).
 * @returns {string} URL base sem barra final.
 */
export function resolveApiBaseUrl({ envUrl, hostname } = {}) {
  const fromEnv = normalizeBaseUrl(envUrl);
  if (fromEnv) return fromEnv;
  if (isLocalHostname(hostname)) return LOCAL_FALLBACK_URL;
  return PRODUCTION_FALLBACK_URL;
}

/**
 * Regra equivalente para tempo de build (o Vite não conhece o hostname).
 * Em qualquer modo que não seja `production`, a ausência da variável cai
 * para o backend local — nunca para produção.
 *
 * @param {object} [options]
 * @param {string} [options.envUrl] Valor de `REACT_APP_BACKEND_URL`.
 * @param {string} [options.mode] Modo do Vite (`development`, `production`, …).
 * @returns {{ url: string, source: "env" | "local-fallback" | "production-fallback" }}
 */
export function resolveBuildTimeBackendUrl({ envUrl, mode } = {}) {
  const fromEnv = normalizeBaseUrl(envUrl);
  if (fromEnv) return { url: fromEnv, source: "env" };
  if (String(mode || "").toLowerCase() !== "production") {
    return { url: LOCAL_FALLBACK_URL, source: "local-fallback" };
  }
  return { url: PRODUCTION_FALLBACK_URL, source: "production-fallback" };
}

/**
 * Detecta a configuração perigosa: app servida de um host local a falar com
 * a API de produção. Não altera o comportamento (o operador pode querê-lo de
 * propósito); grita na consola para que deixe de ser silencioso.
 *
 * @param {object} [options]
 * @param {string} [options.baseUrl] URL base já resolvido.
 * @param {string} [options.hostname] Host onde a app corre.
 * @param {Console} [options.logger] Injectável nos testes.
 * @returns {boolean} true se detectou a mistura de ambientes.
 */
export function warnOnCrossEnvironment({ baseUrl, hostname, logger } = {}) {
  const isMixed =
    isLocalHostname(hostname) && normalizeBaseUrl(baseUrl) === PRODUCTION_FALLBACK_URL;
  if (isMixed) {
    const out = logger || (typeof console !== "undefined" ? console : null);
    if (out && typeof out.error === "function") {
      out.error(
        "[PowerCell] ATENÇÃO: a aplicação está a correr localmente mas aponta para a API de PRODUÇÃO " +
          `(${PRODUCTION_FALLBACK_URL}). Defina REACT_APP_BACKEND_URL no ficheiro .env do frontend ` +
          "antes de continuar — qualquer alteração afecta dados reais.",
      );
    }
  }
  return isMixed;
}

const runtimeHostname =
  typeof window !== "undefined" && window.location ? window.location.hostname : "";

/**
 * URL base do backend para este runtime. Importar isto em vez de repetir
 * `process.env.REACT_APP_BACKEND_URL || "<url de produção>"`.
 */
export const BACKEND_URL = resolveApiBaseUrl({
  envUrl: typeof process !== "undefined" && process.env ? process.env.REACT_APP_BACKEND_URL : "",
  hostname: runtimeHostname,
});

/** `BACKEND_URL` com o prefixo `/api`, que é o que a maioria dos módulos usa. */
export const API_BASE_URL = `${BACKEND_URL}/api`;

warnOnCrossEnvironment({ baseUrl: BACKEND_URL, hostname: runtimeHostname });
