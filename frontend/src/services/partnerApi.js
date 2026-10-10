/**
 * Cliente HTTP do Portal do Parceiro.
 *
 * NÃO USA O CLIENTE DO STAFF (`services/api.js`), e é de propósito:
 *   * aquele injecta `X-Company-Id`/`X-Active-Role` e lê o token do staff —
 *     o parceiro não deve enviar nem conhecer nenhum dos três;
 *   * o tratamento de erros dele abre toasts globais e redirecciona para
 *     `/login`; o parceiro tem o seu login e as suas mensagens (em cada
 *     página, junto ao campo a que dizem respeito).
 *
 * Todas as funções devolvem `data` (o corpo), não a resposta do Axios.
 *
 * O 401 FORA da entrada significa «a sessão morreu» (expirou, foi
 * suspensa, mudaram-lhe a palavra-passe): limpa o token e avisa a árvore do
 * parceiro, que mostra o login. Na entrada, um 401 é só «credenciais
 * erradas» e não toca na sessão.
 */
import axios from "axios";

import { API_BASE_URL } from "../utils/apiBaseUrl";
import { anunciarSessaoExpirada, lerToken } from "../utils/partnerSession";
import { putParaS3 } from "../utils/s3Put";

export const partnerHttp = axios.create({
  baseURL: `${API_BASE_URL}/partner`,
  timeout: 60000,
});

const ROTAS_DE_ENTRADA = ["/auth/login", "/auth/accept-invite", "/auth/invite/"];

partnerHttp.interceptors.request.use((config) => {
  const token = lerToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

partnerHttp.interceptors.response.use(
  (resposta) => resposta,
  (erro) => {
    const url = String(erro?.config?.url || "");
    const eEntrada = ROTAS_DE_ENTRADA.some((r) => url.startsWith(r));
    if (erro?.response?.status === 401 && !eEntrada) anunciarSessaoExpirada();
    return Promise.reject(erro);
  }
);

const dados = (pedido) => pedido.then((r) => r.data);

// ── Entrada ─────────────────────────────────────────────────────────
export const entrar = (email, password) => dados(partnerHttp.post("/auth/login", { email, password }));
export const lerConvite = (token) => dados(partnerHttp.get(`/auth/invite/${encodeURIComponent(token)}`));
export const aceitarConvite = ({ token, password, accept_terms }) =>
  dados(partnerHttp.post("/auth/accept-invite", { token, password, accept_terms }));
export const mudarPalavraPasse = (current_password, new_password) =>
  dados(partnerHttp.post("/auth/change-password", { current_password, new_password }));

// ── Leitura ─────────────────────────────────────────────────────────
export const obterPerfil = () => dados(partnerHttp.get("/me"));
export const obterPainel = () => dados(partnerHttp.get("/dashboard"));
export const listarCasos = ({ etapa, q, page, size } = {}) =>
  dados(
    partnerHttp.get("/cases", {
      params: {
        ...(etapa ? { etapa } : {}),
        ...(q ? { q } : {}),
        ...(page ? { page } : {}),
        ...(size ? { size } : {}),
      },
    })
  );
export const obterCaso = (caseId) => dados(partnerHttp.get(`/cases/${encodeURIComponent(caseId)}`));

// ── Escrita ─────────────────────────────────────────────────────────
export const submeterLead = (payload) => dados(partnerHttp.post("/leads", payload));

export const pedirUrlDeEnvio = (caseId, body) =>
  dados(partnerHttp.post(`/cases/${encodeURIComponent(caseId)}/upload-url`, body));
export const confirmarEnvio = (caseId, body) =>
  dados(partnerHttp.post(`/cases/${encodeURIComponent(caseId)}/confirm-upload`, body));
export const obterUrlDeDescarga = (caseId, fileId) =>
  dados(
    partnerHttp.get(
      `/cases/${encodeURIComponent(caseId)}/files/${encodeURIComponent(fileId)}/download-url`
    )
  );

/**
 * Os três passos de um envio: pedir o URL → `PUT` no S3 → confirmar.
 *
 * A categoria e o pedido são PEDIDOS; quem decide a pasta e se a IA corre é
 * o servidor (desvio inteligente). O tamanho e o tipo que o browser declara
 * não vão: o servidor lê os reais do objecto.
 */
export async function enviarFicheiro(caseId, file, { requestId, category, onProgress } = {}) {
  const tipo = file.type || "application/octet-stream";
  const url = await pedirUrlDeEnvio(caseId, {
    filename: file.name,
    content_type: tipo,
    ...(category ? { category } : {}),
    ...(requestId ? { request_id: requestId } : {}),
  });
  await putParaS3(url.upload_url, file, { onProgress });
  return confirmarEnvio(caseId, {
    file_key: url.file_key,
    original_filename: file.name,
    ...(category ? { category } : {}),
    ...(requestId ? { request_id: requestId } : {}),
  });
}
