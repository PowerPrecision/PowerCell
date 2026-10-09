/**
 * «Arquivar no Processo» (Bloco 2, Lote 12): regras puras do ecrã.
 *
 * A DECISÃO (qual processo, Index ou pasta, se gasta IA) é do servidor — o
 * `document_intake` e o `email_archive`. Aqui só se traduz a resposta para
 * o que o diálogo precisa, sem reimplementar a regra «indexado?».
 *
 * Duas coisas que não se podem perder:
 *  - uma lista do servidor normaliza-se UMA vez, com `Array.isArray` e
 *    nunca `|| []` (D-20): a resposta de um servidor mais antigo, ou de um
 *    erro, não pode rebentar o diálogo;
 *  - com mais do que um processo possível NÃO há pré-selecção. O servidor
 *    diz-o (`sugerido: null`); o ecrã não "ajuda" escolhendo o primeiro.
 */

/**
 * Quem pode arquivar. Espelha `PAPEIS_QUE_ARQUIVAM` do backend; a parede é o
 * servidor, isto só decide se o botão aparece. A indexação é SÓ LEITURA nos
 * documentos (regra do `S3FileManager`).
 */
export const PAPEIS_QUE_ARQUIVAM = [
  "admin",
  "ceo",
  "diretor",
  "administrativo",
  "consultor",
  "intermediario",
];

export const podeArquivarAnexos = (papelEfectivo) =>
  PAPEIS_QUE_ARQUIVAM.includes(String(papelEfectivo || "").toLowerCase());

/** As pastas finais, para um processo que já passou a Indexação. */
export const CATEGORIAS_DE_ARQUIVO = [
  { id: "Documentos Pessoais", label: "Pessoais" },
  { id: "Financeiros", label: "Financeiros" },
  { id: "Imóvel", label: "Imóvel" },
  { id: "Bancários", label: "Bancários" },
  { id: "RGPD", label: "RGPD" },
  { id: "Outros", label: "Outros" },
];

export const CATEGORIA_POR_OMISSAO = "Outros";

/** As sugestões, sempre como array. */
export const sugestoesDe = (resposta) =>
  Array.isArray(resposta?.sugestoes) ? resposta.sugestoes.filter((s) => s && s.process_id) : [];

/** O processo a pré-seleccionar: só o que o servidor sugeriu e existe na lista. */
export const processoPreSeleccionado = (resposta) => {
  const sugerido = resposta?.sugerido;
  if (!sugerido) return null;
  return sugestoesDe(resposta).some((s) => s.process_id === sugerido) ? sugerido : null;
};

/** O processo escolhido, procurado na lista (nunca assumido). */
export const processoEscolhido = (resposta, processId) =>
  sugestoesDe(resposta).find((s) => s.process_id === processId) || null;

/** Só se escolhe a pasta quando o ficheiro NÃO vai para a Index. */
export const devePerguntarAPasta = (processo) => processo?.ja_indexado === true;

/** O que acontece ao ficheiro, dito ao utilizador ANTES de confirmar. */
export const avisoDoDestino = (processo) => {
  if (!processo) return null;
  return processo.ja_indexado === true
    ? "O processo já está indexado: o ficheiro é guardado na pasta escolhida, sem passar pela IA."
    : "O processo ainda não está indexado: o ficheiro fica na pasta Index e entra na fila da Indexação.";
};

/** Rótulo curto de um processo na lista de escolha. */
export const rotuloDoProcesso = (sugestao) => {
  const numero = sugestao?.process_number ? `#${sugestao.process_number} · ` : "";
  return `${numero}${sugestao?.client_name || "Processo"}`;
};

/** A frase do toast depois de arquivar. */
export const mensagemDoArquivo = (resposta) => {
  if (resposta?.already_archived) return "Este anexo já estava arquivado neste processo.";
  if (resposta?.intake?.fila_ia === true) {
    return "Anexo arquivado na pasta Index, à espera da Indexação.";
  }
  return "Anexo arquivado no processo.";
};

/** A mensagem de erro do servidor, ou uma por omissão. */
export const erroDoArquivo = (erro) => {
  const detalhe = erro?.response?.data?.detail;
  if (typeof detalhe === "string" && detalhe.trim()) return detalhe;
  if (erro?.response?.status === 413) return "O anexo é demasiado grande para arquivar.";
  if (erro?.response?.status === 403) return "Não tem permissão para arquivar neste processo.";
  return "Não foi possível arquivar o anexo.";
};

/** O anexo já foi arquivado em algum processo? */
export const processosOndeFoiArquivado = (anexo) =>
  Array.isArray(anexo?.archived_to) ? anexo.archived_to.filter((r) => r && r.process_id) : [];
