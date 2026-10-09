/**
 * useArquivarAnexo — o fluxo «Arquivar no Processo» do Webmail (Bloco 2).
 *
 * Abre o diálogo, pede ao servidor os processos activos do remetente, e
 * arquiva o anexo no escolhido. O contentor só decide o que fazer DEPOIS
 * (`onArquivado`): aqui não se toca na lista de emails.
 *
 * Duas regras que não se podem perder:
 *  - respostas fora de ordem: abrir um anexo, fechar e abrir outro enquanto
 *    o primeiro pedido ainda voa não pode pôr as sugestões do primeiro no
 *    diálogo do segundo — o `pedido` (contador) descarta a resposta velha;
 *  - não se arquiva duas vezes em paralelo (`arquivando` fecha a porta).
 */
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { archiveEmailAttachment, getEmailArchiveSuggestions } from "../services/api";
import { erroDoArquivo, mensagemDoArquivo } from "../utils/emailArchive";

const ESTADO_FECHADO = {
  aberto: false,
  anexo: null,
  indice: -1,
  estado: "a_carregar",
  resposta: null,
  erro: "",
  arquivando: false,
};

/**
 * @param {object} opcoes
 * @param {string|null|undefined} opcoes.emailId
 * @param {(indice: number, resposta: object, processId: string) => void} [opcoes.onArquivado]
 */
export default function useArquivarAnexo({ emailId, onArquivado } = {}) {
  const [estado, setEstado] = useState(ESTADO_FECHADO);
  const pedido = useRef(0);

  const carregar = useCallback(async (id) => {
    const este = ++pedido.current;
    setEstado((e) => ({ ...e, estado: "a_carregar", erro: "", resposta: null }));
    try {
      const { data } = await getEmailArchiveSuggestions(id);
      if (este !== pedido.current) return;
      setEstado((e) => ({ ...e, estado: "pronto", resposta: data || {} }));
    } catch (erro) {
      if (este !== pedido.current) return;
      setEstado((e) => ({
        ...e,
        estado: "erro",
        erro:
          typeof erro?.response?.data?.detail === "string"
            ? erro.response.data.detail
            : "Não foi possível obter os processos sugeridos.",
      }));
    }
  }, []);

  const abrir = useCallback(
    (anexo, indice) => {
      if (!emailId) return;
      setEstado({ ...ESTADO_FECHADO, aberto: true, anexo, indice });
      carregar(emailId);
    },
    [emailId, carregar],
  );

  const fechar = useCallback(() => {
    pedido.current += 1; // descarta qualquer resposta ainda em voo
    setEstado(ESTADO_FECHADO);
  }, []);

  const tentarDeNovo = useCallback(() => {
    if (emailId) carregar(emailId);
  }, [emailId, carregar]);

  const confirmar = useCallback(
    async ({ processId, category }) => {
      if (!emailId || !estado.anexo || estado.arquivando) return;
      const { anexo, indice } = estado;
      const idDoAnexo = anexo.id || `${emailId}:${indice}`;
      setEstado((e) => ({ ...e, arquivando: true }));
      try {
        const { data } = await archiveEmailAttachment(emailId, idDoAnexo, {
          process_id: processId,
          category,
        });
        toast.success(mensagemDoArquivo(data));
        if (onArquivado) onArquivado(indice, data || {}, processId);
        pedido.current += 1;
        setEstado(ESTADO_FECHADO);
      } catch (erro) {
        toast.error(erroDoArquivo(erro));
        setEstado((e) => ({ ...e, arquivando: false }));
      }
    },
    [emailId, estado, onArquivado],
  );

  return { ...estado, abrir, fechar, confirmar, tentarDeNovo };
}
