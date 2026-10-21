/**
 * Pré-visualização de um ficheiro da lead DENTRO da gaveta (imagem ou PDF).
 *
 * Os bytes vêm do backend por `file_id` (Axios, com a sessão e os cabeçalhos de empresa) e viram um URL
 * `blob:` local — nunca um URL pré-assinado do bucket: o CSP do frontend só deixa `<iframe>` em
 * `self` e `blob:`, e assim a chave S3 nem chega ao browser. O URL é libertado ao fechar ou trocar de
 * ficheiro (um `createObjectURL` esquecido segura o ficheiro inteiro em memória).
 *
 * LIMITES: a área tem altura e largura máximas e rola (`overflow-auto`): uma imagem de 4000 px ou um
 * PDF de 40 páginas não alargam nem alongam a gaveta. O servidor recusa acima de 15 MB; nada é
 * guardado em cache pelo browser (`no-store`).
 */
import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";

import { Button } from "../ui/button";
import { getLeadFileContent, readBlobErrorBody } from "../../services/api";
import { safeString } from "../../utils/safeString";
import { mensagemDaFalhaDePrevisualizacao, tipoDaPrevisualizacao } from "../../utils/previsualizacao";

/**
 * @param {Object} props
 * @param {string} props.leadId
 * @param {{file_id: string, filename: string}} props.ficheiro
 * @param {Function} props.onFechar
 */
export default function PreviewDoFicheiro({ leadId, ficheiro, onFechar }) {
  const [url, setUrl] = useState("");
  const [erro, setErro] = useState("");
  const [aCarregar, setACarregar] = useState(true);
  const tipo = tipoDaPrevisualizacao(ficheiro?.filename);
  const nome = safeString(ficheiro?.filename) || "ficheiro";

  useEffect(() => {
    if (!leadId || !ficheiro?.file_id || !tipo) return undefined;
    let activo = true;
    let criado = "";
    setUrl("");
    setErro("");
    setACarregar(true);
    getLeadFileContent(leadId, ficheiro.file_id)
      .then((resposta) => {
        if (!activo) return;
        // O tipo é o NOSSO (pela extensão), não o que o cabeçalho trouxer: um blob sem tipo certo
        // faria o `<iframe>` descarregar em vez de mostrar.
        criado = URL.createObjectURL(new Blob([resposta.data], { type: tipo.mime }));
        setUrl(criado);
      })
      .catch(async (e) => {
        if (!activo) return;
        const corpo = await readBlobErrorBody(e);
        if (activo) setErro(mensagemDaFalhaDePrevisualizacao(e?.response?.status, corpo?.detail));
      })
      .finally(() => { if (activo) setACarregar(false); });
    return () => {
      activo = false;
      if (criado) URL.revokeObjectURL(criado);
    };
  }, [leadId, ficheiro?.file_id, tipo]);

  return (
    <div className="mt-2 rounded-md border bg-muted/30" data-testid="previsualizacao">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <span className="min-w-0 truncate text-xs text-muted-foreground" title={nome}>Pré-visualização — {nome}</span>
        <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-2" onClick={onFechar} data-testid="previsualizacao-fechar">
          <X className="h-3.5 w-3.5" aria-hidden="true" />Fechar
        </Button>
      </div>

      {/* Limites: nunca mais alta do que 60% do ecrã nem mais larga do que a gaveta; rola dentro. */}
      <div className="max-h-[60vh] max-w-full overflow-auto" data-testid="previsualizacao-area">
        {aCarregar && (
          <p className="flex items-center gap-2 p-4 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A carregar…
          </p>
        )}
        {erro && <p role="alert" className="p-4 text-sm text-destructive" data-testid="previsualizacao-erro">{erro}</p>}
        {url && tipo?.forma === "imagem" && (
          <img src={url} alt={`Pré-visualização de ${nome}`} className="mx-auto block h-auto max-w-full" data-testid="previsualizacao-imagem" />
        )}
        {url && tipo?.forma === "pdf" && (
          <iframe src={url} title={`Pré-visualização de ${nome}`} className="block h-[60vh] w-full border-0" data-testid="previsualizacao-pdf" />
        )}
      </div>
    </div>
  );
}
