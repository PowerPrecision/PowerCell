/**
 * GenerateTemplateDialog — gerar uma minuta a partir do processo
 * (Épico 8, Eixo 2).
 *
 * COMPONENTE DE APRESENTAÇÃO. O erro de validação vem pronto do contentor
 * (`{message, missingFields}`): é ele que o lê do corpo da resposta, que
 * chega como Blob por o pedido pedir `responseType: "blob"` — ver
 * `readBlobErrorBody` em `services/api.js`.
 */
import { AlertTriangle, FileDown, Loader2 } from "lucide-react";

import { Button } from "../../ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../ui/select";
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
 * @param {Array<{id: string, label: string}>} props.templates
 * @param {string} props.selectedTemplate - Escolha actual (controlada).
 * @param {{message: string, missingFields?: string[]}|null} [props.error]
 * @param {boolean} [props.generating]
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(id: string) => void} props.onTemplateChange
 * @param {() => void} props.onGenerate
 */
export default function GenerateTemplateDialog({
  open,
  templates = [],
  selectedTemplate,
  error,
  generating = false,
  onOpenChange,
  onTemplateChange,
  onGenerate,
}) {
  return (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <FileDown className="h-5 w-5 text-emerald-600" />
          Gerar Minuta
        </DialogTitle>
        <DialogDescription>
          Selecione o tipo de documento para gerar automaticamente com os dados do cliente.
        </DialogDescription>
      </DialogHeader>
      
      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Tipo de Documento</label>
          <Select
            value={selectedTemplate}
            onValueChange={(value) => {
              onTemplateChange(value);
            }}
          >
            <SelectTrigger data-testid="template-select">
              <SelectValue placeholder="Selecione o tipo de documento..." />
            </SelectTrigger>
            <SelectContent>
              {templates.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Erro de validação - campos em falta */}
        {error && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">
                  Não é possível gerar a minuta
                </p>
                <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                  {error.message}
                </p>
                {error.missingFields?.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                      Campos em falta:
                    </p>
                    <ul className="mt-1 text-sm text-amber-700 dark:text-amber-300 list-disc list-inside">
                      {error.missingFields.map((field, idx) => (
                        <li key={idx}>{field}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                  Preencha os dados em falta na ficha do cliente antes de gerar o documento.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      <DialogFooter className="flex gap-2">
        <Button
          variant="outline"
          onClick={() => onOpenChange(false)}
          disabled={generating}
        >
          Cancelar
        </Button>
        <Button
          onClick={onGenerate}
          disabled={!selectedTemplate || generating}
          className="bg-emerald-600 hover:bg-emerald-700"
        >
          {generating ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <FileDown className="h-4 w-4 mr-2" />
          )}
          Gerar e Descarregar
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
