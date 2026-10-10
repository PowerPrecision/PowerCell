/**
 * Descarrega um PDF gerado pelo servidor e traduz a falha em mensagem.
 *
 * `responseType: "blob"` faz o corpo de ERRO chegar também como Blob; sem
 * `readBlobErrorBody` o motivo do servidor (422 período inválido, 503
 * «demorou demasiado») desaparecia e o utilizador via só «erro».
 */
import { readBlobErrorBody } from "../../services/api";
import { descarregarBlob, nomeDoFicheiro } from "../../utils/executivo";
import { extractErrorMessage } from "../../utils/extractErrorMessage";

/**
 * @param {() => Promise<{data: Blob, headers: object}>} chamada
 * @param {string} nomeDeRecuo
 * @returns {Promise<{ok: true, nome: string} | {ok: false, erro: string}>}
 */
export async function descarregarPdf(chamada, nomeDeRecuo) {
  try {
    const resposta = await chamada();
    const nome = nomeDoFicheiro(resposta.headers, nomeDeRecuo);
    descarregarBlob(resposta.data, nome);
    return { ok: true, nome };
  } catch (erro) {
    const corpo = await readBlobErrorBody(erro);
    return { ok: false, erro: extractErrorMessage(corpo?.detail, "Não foi possível gerar o PDF") };
  }
}
