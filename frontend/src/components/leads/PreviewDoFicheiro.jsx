/**
 * Pré-visualização de um ficheiro da lead DENTRO da gaveta (imagem ou PDF).
 *
 * Só a moldura e a origem dos bytes (`getLeadFileContent`, por `file_id`, nunca por chave S3) são daqui;
 * o desenho, os limites, o `blob:` e as falhas são do `PrevisualizadorDeFicheiro`, partilhado com o
 * «Ver documento» da pesquisa do Index.
 */
import { X } from "lucide-react";

import { Button } from "../ui/button";
import PrevisualizadorDeFicheiro from "../shared/PrevisualizadorDeFicheiro";
import { getLeadFileContent } from "../../services/api";
import { safeString } from "../../utils/safeString";

/**
 * @param {Object} props
 * @param {string} props.leadId
 * @param {{file_id: string, filename: string}} props.ficheiro
 * @param {Function} props.onFechar
 */
export default function PreviewDoFicheiro({ leadId, ficheiro, onFechar }) {
  const nome = safeString(ficheiro?.filename) || "ficheiro";

  return (
    <div className="mt-2 rounded-md border bg-muted/30" data-testid="previsualizacao">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <span className="min-w-0 truncate text-xs text-muted-foreground" title={nome}>Pré-visualização — {nome}</span>
        <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-2" onClick={onFechar} data-testid="previsualizacao-fechar">
          <X className="h-3.5 w-3.5" aria-hidden="true" />Fechar
        </Button>
      </div>
      {leadId && ficheiro?.file_id ? (
        <PrevisualizadorDeFicheiro
          chave={`${leadId}:${ficheiro.file_id}`}
          carregar={() => getLeadFileContent(leadId, ficheiro.file_id)}
          nome={nome}
        />
      ) : null}
    </div>
  );
}
