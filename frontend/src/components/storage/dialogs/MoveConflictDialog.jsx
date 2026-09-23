/**
 * MoveConflictDialog — nome duplicado ao mover um ficheiro entre pastas
 * (Épico 8, Eixo 2).
 *
 * Arrastar um ficheiro para outra categoria pode colidir com um nome já lá
 * existente. O consultor decide: substituir, renomear, ignorar este — ou
 * aplicar a mesma decisão aos restantes do lote.
 *
 * COMPONENTE DE APRESENTAÇÃO: não move nada. Fechar cancela o lote, e é o
 * contentor que limpa o estado de arrastamento — senão o próximo "largar"
 * herdaria os ficheiros antigos.
 */
import { AlertTriangle, FileText, FolderSync, Pencil, Save, Trash2, X } from "lucide-react";

import { Button } from "../../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {Array<Object>} props.conflicts - Colisões por decidir.
 * @param {string} [props.targetCategory] - Pasta de destino, para o texto.
 * @param {(decisao: "overwrite"|"rename"|"skip") => void} props.onDecide
 * @param {(decisao: "overwrite"|"rename") => void} props.onDecideForAll
 * @param {() => void} props.onCancel
 */
export default function MoveConflictDialog({
  open,
  conflicts = [],
  targetCategory,
  onDecide,
  onDecideForAll,
  onCancel,
}) {
  return (
  <Dialog open={open} onOpenChange={(aberto) => !aberto && onCancel()}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 text-amber-600">
          <AlertTriangle className="h-5 w-5" />
          Ficheiro com Nome Duplicado
        </DialogTitle>
        <DialogDescription>
          Já existe um ficheiro com o mesmo nome na pasta de destino.
        </DialogDescription>
      </DialogHeader>
      
      {conflicts?.length > 0 && (
        <div className="space-y-4 py-4">
          {/* Info do ficheiro em conflito */}
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
            <div className="flex items-center gap-3">
              <FileText className="h-8 w-8 text-amber-600" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">
                  {conflicts[0]?.conflictFilename || conflicts[0]?.file?.name}
                </p>
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  Destino: {targetCategory}
                </p>
              </div>
            </div>
          </div>
          
          {/* Mostrar mais ficheiros se houver múltiplos conflitos */}
          {conflicts.length > 1 && (
            <p className="text-sm text-muted-foreground">
              +{conflicts.length - 1} outro(s) ficheiro(s) com conflito
            </p>
          )}
          
          {/* Opções de resolução */}
          <div className="space-y-2">
            <p className="text-sm font-medium">O que deseja fazer?</p>
            
            {/* Sugestões de nomes alternativos */}
            {conflicts[0]?.suggestedNames?.length > 0 && (
              <div className="bg-muted/50 rounded-lg p-3 mb-3">
                <p className="text-xs text-muted-foreground mb-2">Nomes sugeridos:</p>
                <div className="flex flex-wrap gap-2">
                  {conflicts[0].suggestedNames.slice(0, 3).map((suggestion, idx) => (
                    <Button
                      key={idx}
                      variant="outline"
                      size="sm"
                      onClick={() => onDecide('custom', suggestion.filename)}
                      className="text-xs"
                    >
                      <Save className="h-3 w-3 mr-1" />
                      {suggestion.filename || suggestion}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                onClick={() => onDecide('rename')}
                className="w-full"
              >
                <Pencil className="h-4 w-4 mr-2" />
                Renomear Automaticamente
              </Button>
              <Button
                variant="destructive"
                onClick={() => onDecide('overwrite')}
                className="w-full"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Substituir Existente
              </Button>
            </div>
            
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="ghost"
                onClick={() => onDecide('skip')}
                className="w-full"
              >
                <X className="h-4 w-4 mr-2" />
                Ignorar Este
              </Button>
              {conflicts?.length > 1 && (
                <Button
                  variant="ghost"
                  onClick={() => onDecideForAll('rename')}
                  className="w-full text-amber-600 hover:text-amber-700"
                >
                  <FolderSync className="h-4 w-4 mr-2" />
                  Renomear Todos
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </DialogContent>
  </Dialog>
  );
}
