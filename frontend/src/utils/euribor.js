/**
 * Euribor a 12 meses para as calculadoras (Risco, Simulador do Portal do
 * Cliente) — `GET /api/public/euribor`.
 *
 * PORQUÊ ESTE MÓDULO: as calculadoras faziam `fetch("/api/public/euribor")`
 * relativo ao domínio do FRONTEND. Na Vercel esse caminho cai na rewrite
 * para `index.html`, o `r.json()` rebentava e a Euribor nunca era
 * preenchida em produção (só funcionava com o proxy do Vite em local).
 * Vai agora ao backend pelo `API_BASE_URL` único.
 *
 * Usa um Axios SEM interceptores e sem cabeçalhos de sessão de propósito:
 * o endpoint é público e as calculadoras vivem tanto no CRM como no Portal
 * do Parceiro e no Portal do Cliente — nenhum deles deve enviar aqui o seu
 * token nem o `X-Company-Id`/`X-Active-Role` do staff.
 */
import axios from "axios";

import { API_BASE_URL } from "./apiBaseUrl";

/** @returns {Promise<{euribor_12m: number, is_fallback?: boolean}>} */
export async function obterEuribor() {
  const resposta = await axios.get(`${API_BASE_URL}/public/euribor`, { timeout: 15000 });
  return resposta.data;
}
