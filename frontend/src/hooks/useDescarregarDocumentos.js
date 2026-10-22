/**
 * useDescarregarDocumentos — descarrega, um a um, os documentos de um resultado da pesquisa do Index.
 *
 * Um resultado por emprego pode ter vários documentos: descarregam-se em sequência (nunca em paralelo — o
 * servidor limita os pedidos e o browser pede autorização a quem recebe muitos de uma vez). Uma falha num
 * não impede os seguintes e diz-se no fim, com o número certo. Quem chama só diz o que se quer: a decisão do
 * nome, do `Blob` e do aviso vive aqui e em `utils/descarregarFicheiro`.
 */
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { getIndexDocumentContent, readBlobErrorBody } from "../services/api";
import { guardarBlob, mensagemDaFalhaDeDescarga, nomeDaDescarga } from "../utils/descarregarFicheiro";

export function useDescarregarDocumentos() {
  const [emCurso, setEmCurso] = useState(() => new Set());
  const activos = useRef(new Set());

  const descarregar = useCallback(async (chave, documentos) => {
    const lista = Array.isArray(documentos) ? documentos.filter((d) => d && d.id) : [];
    if (!lista.length || activos.current.has(chave)) return { feitos: 0, falhados: 0 };
    activos.current.add(chave);
    setEmCurso(new Set(activos.current));
    let feitos = 0;
    let motivo = null;
    try {
      for (const doc of lista) {
        try {
          const resposta = await getIndexDocumentContent(doc.id, { download: true });
          const nome = nomeDaDescarga({
            rotulo: doc.rotulo,
            contentType: resposta.headers?.["content-type"] || resposta.data?.type,
            disposicao: resposta.headers?.["content-disposition"],
          });
          guardarBlob(resposta.data, nome);
          feitos += 1;
        } catch (erro) {
          const corpo = await readBlobErrorBody(erro).catch(() => null);
          motivo = mensagemDaFalhaDeDescarga(erro?.response?.status, corpo?.detail);
        }
      }
    } finally {
      activos.current.delete(chave);
      setEmCurso(new Set(activos.current));
    }
    const falhados = lista.length - feitos;
    if (falhados > 0) {
      toast.error(
        lista.length === 1 ? motivo : `${falhados} de ${lista.length} documentos não foram descarregados. ${motivo}`,
      );
    } else if (lista.length > 1) {
      toast.success(`${feitos} documentos descarregados.`);
    }
    return { feitos, falhados };
  }, []);

  return { descarregar, emCurso };
}

export default useDescarregarDocumentos;
