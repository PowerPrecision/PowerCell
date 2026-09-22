/**
 * OrganizeResultsDialog — resumo da organização automática
 * (Épico 8, Eixo 2).
 *
 * Depois de a IA analisar e arrumar os documentos nas pastas certas, este
 * diálogo diz quantos foram analisados, quantos mudaram de sítio e para
 * onde. COMPONENTE DE APRESENTAÇÃO: só lê.
 */
import { FolderSync } from "lucide-react";

import { Badge } from "../../ui/badge";
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
 * @param {Object|null} props.results - `null` mantém o diálogo fechado.
 * @param {() => void} props.onClose
 */
export default function OrganizeResultsDialog({ results, onClose }) {
  return (
  <Dialog open={!!results} onOpenChange={(aberto) => !aberto && onClose()}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <FolderSync className="h-5 w-5 text-teal-600" />
          Organização Completa
        </DialogTitle>
        <DialogDescription>
          Os documentos foram analisados e organizados automaticamente.
        </DialogDescription>
      </DialogHeader>
      
      {results && (
        <div className="space-y-4 py-4">
          {/* Resumo */}
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center p-3 bg-muted rounded-lg">
              <p className="text-2xl font-bold text-blue-600">{results.analyzed}</p>
              <p className="text-xs text-muted-foreground">Analisados</p>
            </div>
            <div className="text-center p-3 bg-teal-50 dark:bg-teal-950/30 rounded-lg">
              <p className="text-2xl font-bold text-teal-600">{results.organized}</p>
              <p className="text-xs text-teal-600">Organizados</p>
            </div>
          </div>

          {/* Categorias encontradas */}
          {results.categories?.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Categorias identificadas:</p>
              <div className="flex flex-wrap gap-1">
                {results.categories.map((cat, idx) => (
                  <Badge key={idx} variant="outline" className="text-xs">
                    {cat}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Detalhes */}
          {results.details?.length > 0 && (
            <div className="border rounded-lg max-h-40 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted sticky top-0">
                  <tr>
                    <th className="text-left p-2">Ficheiro</th>
                    <th className="text-left p-2">Pasta</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {results.details.slice(0, 10).map((item, idx) => (
                    <tr key={idx}>
                      <td className="p-2 truncate max-w-[150px]">{item.filename || item.file_name}</td>
                      <td className="p-2">{item.target_folder || item.category}</td>
                    </tr>
                  ))}
                  {results.details.length > 10 && (
                    <tr>
                      <td colSpan={2} className="p-2 text-center text-muted-foreground">
                        +{results.details.length - 10} mais...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <DialogFooter>
        <Button onClick={onClose} className="bg-teal-600 hover:bg-teal-700">
          Fechar
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
