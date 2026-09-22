/**
 * UploadConflictDialog — ficheiro duplicado no destino (Épico 8, Eixo 2).
 *
 * Quando um upload colide com um nome já existente na pasta, o consultor
 * decide por ficheiro: substituir, renomear automaticamente, dar um nome
 * próprio ou saltar. Os conflitos são percorridos um a um.
 *
 * COMPONENTE DE APRESENTAÇÃO: não carrega nada nem conhece o S3. Cada
 * decisão volta ao contentor por `onResolve`, e é ele que retoma o upload.
 */
import { AlertTriangle, FileText } from "lucide-react";

import { Button } from "../../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {Array<{original_filename: string, suggested_names?: Array<{filename: string}>}>} props.conflicts
 * @param {number} props.currentIndex - Conflito a decidir agora.
 * @param {Object} props.resolutions - Decisões já tomadas, por índice.
 * @param {string} [props.category] - Categoria de destino, para o texto.
 * @param {(accao: "overwrite"|"rename"|"skip", nomeProprio?: string|null) => void} props.onResolve
 *   A decisão aplica-se ao conflito em `currentIndex`; o contentor é
 *   que sabe qual é, e é ele que guarda a lista de resoluções.
 * @param {() => void} props.onNext - Avança (ou retoma o upload no último).
 * @param {() => void} props.onCancel - Cancela o lote inteiro.
 */
export default function UploadConflictDialog({
  open,
  conflicts = [],
  currentIndex = 0,
  resolutions = {},
  category,
  onResolve,
  onNext,
  onCancel,
}) {
  return (
  <Dialog open={open} onOpenChange={(aberto) => !aberto && onCancel()}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 text-amber-600">
          <AlertTriangle className="h-5 w-5" />
          Ficheiro Duplicado Detetado
        </DialogTitle>
        <DialogDescription>
          Já existe um ficheiro com o mesmo nome no destino.
          Escolha como pretende resolver este conflito.
        </DialogDescription>
      </DialogHeader>

      {conflicts.length > 0 && (
        <>
          {/* Indicador de progresso */}
          {conflicts.length > 1 && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
              <span>
                Conflito {currentIndex + 1} de {conflicts.length}
              </span>
              <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                <div 
                  className="h-full bg-amber-500 transition-all"
                  style={{ 
                    width: `${((currentIndex + 1) / conflicts.length) * 100}%` 
                  }}
                />
              </div>
            </div>
          )}

          {/* Conflito atual */}
          {(() => {
            const conflict = conflicts[currentIndex];
            const resolution = resolutions?.[currentIndex];
            
            if (!conflict) return null;
            
            return (
              <div className="space-y-4 py-4">
                {/* Info do ficheiro */}
                <div className="p-4 bg-amber-50 dark:bg-amber-950/30 rounded-lg border border-amber-200 dark:border-amber-800">
                  <div className="flex items-start gap-3">
                    <FileText className="h-8 w-8 text-amber-600 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-amber-800 dark:text-amber-200 truncate">
                        {conflict.original_filename}
                      </p>
                      <p className="text-sm text-amber-700 dark:text-amber-300">
                        Já existe um ficheiro com este nome na categoria "{category}"
                      </p>
                    </div>
                  </div>
                </div>

                {/* Opções de resolução */}
                <div className="space-y-3">
                  <p className="text-sm font-medium">Escolha uma ação:</p>
                  
                  {/* Opção: Substituir */}
                  <label className={`
                    flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                    ${resolution?.action === 'overwrite' 
                      ? 'border-red-500 bg-red-50 dark:bg-red-950/30' 
                      : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
                    }
                  `}>
                    <input
                      type="radio"
                      name="conflict-action"
                      checked={resolution?.action === 'overwrite'}
                      onChange={() => onResolve('overwrite')}
                      className="mt-1"
                    />
                    <div>
                      <p className="font-medium text-red-700 dark:text-red-300">
                        Substituir ficheiro existente
                      </p>
                      <p className="text-sm text-muted-foreground">
                        O ficheiro atual será eliminado e substituído pelo novo
                      </p>
                    </div>
                  </label>

                  {/* Opção: Renomear */}
                  <label className={`
                    flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                    ${resolution?.action === 'rename' 
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30' 
                      : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
                    }
                  `}>
                    <input
                      type="radio"
                      name="conflict-action"
                      checked={resolution?.action === 'rename'}
                      onChange={() => {
                        // Selecionar o primeiro nome sugerido automaticamente
                        const suggested = conflict.suggested_names?.[0]?.filename;
                        onResolve('rename', suggested || null);
                      }}
                      className="mt-1"
                    />
                    <div className="flex-1">
                      <p className="font-medium text-blue-700 dark:text-blue-300">
                        Guardar com nome diferente
                      </p>
                      <p className="text-sm text-muted-foreground mb-2">
                        O ficheiro será guardado com um novo nome
                      </p>
                      
                      {/* Seleção de nome */}
                      {resolution?.action === 'rename' && conflict.suggested_names?.length > 0 && (
                        <select
                          value={resolution.customName || ''}
                          onChange={(e) => onResolve('rename', e.target.value)}
                          className="w-full text-sm p-2 border rounded bg-white dark:bg-gray-800"
                        >
                          {conflict.suggested_names.map((s, idx) => (
                            <option key={idx} value={s.filename}>{s.filename}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </label>

                  {/* Opção: Ignorar */}
                  <label className={`
                    flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                    ${resolution?.action === 'skip' 
                      ? 'border-gray-500 bg-gray-50 dark:bg-gray-800' 
                      : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
                    }
                  `}>
                    <input
                      type="radio"
                      name="conflict-action"
                      checked={resolution?.action === 'skip'}
                      onChange={() => onResolve('skip')}
                      className="mt-1"
                    />
                    <div>
                      <p className="font-medium text-gray-700 dark:text-gray-300">
                        Ignorar este ficheiro
                      </p>
                      <p className="text-sm text-muted-foreground">
                        O ficheiro não será enviado e o existente será mantido
                      </p>
                    </div>
                  </label>
                </div>
              </div>
            );
          })()}
        </>
      )}

      <DialogFooter className="flex gap-2">
        <Button
          variant="outline"
          onClick={onCancel}
        >
          Cancelar Tudo
        </Button>
        <Button
          onClick={onNext}
          disabled={!resolutions?.[currentIndex]?.action}
          className="bg-amber-600 hover:bg-amber-700"
        >
          {currentIndex < conflicts.length - 1 
            ? 'Próximo' 
            : 'Continuar Upload'}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
