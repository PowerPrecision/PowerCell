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
 * @returns {Promise<{ok: true, nome: string, analise: string|null} | {ok: false, erro: string}>}
 *   `analise`: o que o servidor diz ter acontecido à análise de IA
 *   (`incluida`, `simulada`, `indisponivel`, `nao-pedida`), ou `null` se não disser.
 */
export async function descarregarPdf(chamada, nomeDeRecuo) {
  try {
    const resposta = await chamada();
    const nome = nomeDoFicheiro(resposta.headers, nomeDeRecuo);
    descarregarBlob(resposta.data, nome);
    return { ok: true, nome, analise: resposta.headers?.["x-analise-ia"] ?? null };
  } catch (erro) {
    const corpo = await readBlobErrorBody(erro);
    return { ok: false, erro: extractErrorMessage(corpo?.detail, "Não foi possível gerar o PDF") };
  }
}

/**
 * A mensagem para o utilizador depois de um PDF gerado.
 *
 * Quem pediu a análise de IA e não a recebeu tem de ser avisado: um PDF sem
 * ela e sem uma palavra parece um defeito — ou, pior, parece que a análise
 * foi feita e é a equipa que não tem nada a dizer.
 *
 * @param {{analise: string|null}} resultado
 * @param {boolean} pediuAnalise
 * @returns {{tipo: "sucesso"|"aviso", texto: string}}
 */
export function mensagemDoPdf(resultado, pediuAnalise) {
  if (pediuAnalise && resultado?.analise === "indisponivel") {
    return {
      tipo: "aviso",
      texto: "PDF gerado sem a análise de IA: o serviço não respondeu ou não havia dados a analisar.",
    };
  }
  if (pediuAnalise && resultado?.analise === "simulada") {
    return { tipo: "sucesso", texto: "PDF gerado (análise simulada: ambiente de desenvolvimento)" };
  }
  return { tipo: "sucesso", texto: "PDF gerado" };
}
