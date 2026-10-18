/**
 * O que o ecrã de mapeamento S3 mostra — nunca o que grava (QA-6).
 *
 * Duas coisas que partiam o ecrã:
 *  1. A lista de pastas só trazia as de TOPO (`Documentação Clientes/<id>`), mas o ponteiro de um
 *     processo novo é `…/<id>/processos/<id>`. O `<select>` não encontrava o valor atual entre as
 *     opções e mostrava a primeira — «Sem mapeamento» — para dezenas de processos que TÊM pasta.
 *  2. O nome da pasta era o do bucket: um uuid, ou `Joao_Silva`.
 *
 * `path` continua a ser a autoridade de tudo o que se grava; o rótulo é só para o ecrã
 * (a regra de `utils/pastaS3.js`).
 */
import { nomeVisivel, ordenarPastas } from "./pastaS3";

/**
 * As opções do seletor de UM processo: as pastas de topo (nome legível) e, se o ponteiro atual
 * não é uma delas, o próprio ponteiro como primeira opção — para o seletor mostrar o que está
 * gravado em vez de cair em «Sem mapeamento».
 */
export const opcoesDeMapeamento = (pastas, processo) => {
  const opcoes = ordenarPastas(Array.isArray(pastas) ? pastas : [])
    .filter((p) => typeof p?.path === "string" && p.path)
    .map((p) => ({ value: p.path, label: nomeVisivel(p) }));
  const atual = typeof processo?.s3_folder === "string" ? processo.s3_folder : "";
  if (atual && !opcoes.some((o) => o.value === atual)) {
    const legivel = (processo?.s3_folder_display || "").trim();
    opcoes.unshift({ value: atual, label: legivel || atual });
  }
  return opcoes;
};

/** O ponteiro está gravado e é texto? (um valor de outro tipo conta como «sem pasta») */
export const temPastaGravada = (processo) =>
  typeof processo?.s3_folder === "string" && processo.s3_folder.trim() !== "";
