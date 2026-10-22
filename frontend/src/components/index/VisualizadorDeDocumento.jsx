/**
 * VisualizadorDeDocumento — «Ver documento» da pesquisa avançada, sobreposto aos resultados.
 *
 * O utilizador vê o PDF ou a imagem que fez match SEM sair da lista (nem perder os filtros, a página ou
 * o sítio onde estava). Os bytes vêm de `GET /api/index/documents/{id}/content` (por id; a chave S3 nem
 * chega ao ecrã) e viram um `blob:` local — ver `PrevisualizadorDeFicheiro`.
 *
 * Uma linha pode ter vários documentos (a vista por emprego): então há «Anterior/Seguinte» e diz-se
 * «Documento 2 de 5». Apresentação pura: quem decide quando abre e fecha é a página.
 */
import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import PrevisualizadorDeFicheiro from "../shared/PrevisualizadorDeFicheiro";
import { getIndexDocumentContent } from "../../services/api";

function Conteudo({ documentos }) {
  const [indice, setIndice] = useState(0);
  const total = documentos.length;
  const actual = documentos[Math.min(indice, total - 1)];

  return (
    <>
      {total > 1 && (
        <div className="flex items-center justify-between gap-2" data-testid="visualizador-navegacao">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={indice === 0}
            onClick={() => setIndice((i) => Math.max(0, i - 1))}
            aria-label="Documento anterior"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />Anterior
          </Button>
          <span className="text-sm text-muted-foreground" aria-live="polite" data-testid="visualizador-posicao">
            Documento {indice + 1} de {total}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={indice >= total - 1}
            onClick={() => setIndice((i) => Math.min(total - 1, i + 1))}
            aria-label="Documento seguinte"
          >
            Seguinte<ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      )}
      <div className="rounded-md border bg-muted/30" data-testid="visualizador-corpo">
        <PrevisualizadorDeFicheiro
          chave={actual.id}
          carregar={() => getIndexDocumentContent(actual.id)}
          nome={actual.rotulo}
          alturaDoPdf="h-[65vh]"
          alturaMaxima="max-h-[65vh]"
        />
      </div>
    </>
  );
}

/**
 * @param {Object} props
 * @param {Array<{id: string, rotulo: string}>} props.documentos — vazio/ausente = fechado
 * @param {string} [props.titulo]
 * @param {Function} props.onFechar
 */
export default function VisualizadorDeDocumento({ documentos, titulo, onFechar }) {
  const lista = Array.isArray(documentos) ? documentos.filter((d) => d && d.id) : [];
  const aberto = lista.length > 0;

  return (
    <Dialog open={aberto} onOpenChange={(valor) => { if (!valor) onFechar?.(); }}>
      {aberto && (
        <DialogContent className="max-w-4xl" title={titulo || "Documento"} description="Pré-visualização do documento encontrado">
          <DialogHeader>
            <DialogTitle>{titulo || "Documento"}</DialogTitle>
            <DialogDescription>
              Pré-visualização: nada é descarregado nem guardado, e a pesquisa fica como estava.
            </DialogDescription>
          </DialogHeader>
          {/* a chave junta os ids: outra linha reinicia a navegação */}
          <Conteudo key={lista.map((d) => d.id).join(",")} documentos={lista} />
        </DialogContent>
      )}
    </Dialog>
  );
}
