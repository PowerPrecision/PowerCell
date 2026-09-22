/**
 * SmartRenameResultsDialog — resultado da renomeação inteligente
 * (Épico 8, Eixo 2).
 *
 * Mostra quantos documentos foram renomeados, saltados ou falharam, e o
 * detalhe nome-a-nome. COMPONENTE DE APRESENTAÇÃO: só lê.
 */
import { AlertCircle, CheckCircle, Sparkles, X } from "lucide-react";

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
 * @param {Object|null} props.results - Resposta de `/rename-all-smart`.
 * @param {(aberto: boolean) => void} props.onOpenChange
 */
export default function SmartRenameResultsDialog({ open, results, onOpenChange }) {
  return (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-lg max-h-[80vh] overflow-auto">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-amber-600" />
          Renomeação Inteligente
        </DialogTitle>
        <DialogDescription>
          Resultado da renomeação automática dos documentos
        </DialogDescription>
      </DialogHeader>
      
      {results && (
        <div className="space-y-4 py-4">
          {/* Estatísticas resumidas */}
          <div className="grid grid-cols-4 gap-2">
            <div className="text-center p-2 bg-muted rounded-lg">
              <p className="text-2xl font-bold">{results.total}</p>
              <p className="text-xs text-muted-foreground">Total</p>
            </div>
            <div className="text-center p-2 bg-green-50 dark:bg-green-950/30 rounded-lg">
              <p className="text-2xl font-bold text-green-600">{results.renamed}</p>
              <p className="text-xs text-green-600">Renomeados</p>
            </div>
            <div className="text-center p-2 bg-amber-50 dark:bg-amber-950/30 rounded-lg">
              <p className="text-2xl font-bold text-amber-600">{results.skipped}</p>
              <p className="text-xs text-amber-600">Ignorados</p>
            </div>
            <div className="text-center p-2 bg-red-50 dark:bg-red-950/30 rounded-lg">
              <p className="text-2xl font-bold text-red-600">{results.errors}</p>
              <p className="text-xs text-red-600">Erros</p>
            </div>
          </div>
          
          {/* Lista detalhada */}
          {results.details && results.details.length > 0 && (
            <div className="border rounded-lg divide-y max-h-60 overflow-auto">
              {results.details.map((item, idx) => (
                <div key={idx} className="p-2 flex items-center gap-2 text-sm">
                  {item.status === "renamed" ? (
                    <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                  ) : item.status === "skipped" ? (
                    <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                  ) : (
                    <X className="h-4 w-4 text-red-500 flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium">{item.file}</p>
                    {item.new_name && (
                      <p className="text-xs text-green-600 truncate">→ {item.new_name}</p>
                    )}
                    {item.reason && (
                      <p className="text-xs text-muted-foreground">{item.reason}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      <DialogFooter>
        <Button onClick={() => onOpenChange(false)}>
          Fechar
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
