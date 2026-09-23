/**
 * AIResultsDialog — resultados da análise IA em lote (Épico 8, Eixo 2).
 *
 * Mostra o que a IA extraiu dos documentos do processo: que documentos
 * processou e com que confiança, que campos da ficha estão vazios e podem
 * ser preenchidos, quais entram em conflito com o que já lá está, e quais
 * coincidem.
 *
 * COMPONENTE DE APRESENTAÇÃO: não chama a API nem escreve na ficha. Quando
 * o consultor aceita uma sugestão — uma ou todas —, devolve os valores por
 * `onApplySuggestions` e o contentor decide o que fazer com eles.
 */
import { AlertCircle, Brain, CheckCircle, FileText, Loader2, Sparkles } from "lucide-react";

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
 * @param {boolean} props.open
 * @param {Object|null} props.results - Resposta de `/documents/ai-analyze`.
 * @param {string} [props.clientName] - Nome do titular, para o subtítulo.
 * @param {boolean} [props.applying] - Aplicação em curso (bloqueia botões).
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(valores: Record<string, any>) => void} props.onApplySuggestions
 */
export default function AIResultsDialog({
  open,
  results,
  clientName,
  applying = false,
  onOpenChange,
  onApplySuggestions,
}) {
  const sugestoes = results?.analysis?.auto_fill_suggestions;

  // Achata `{campo: {value, confidence}}` em `{campo: value}` — é o que o
  // contentor precisa para escrever na ficha.
  const aplicarSugestoes = () =>
    onApplySuggestions(
      Object.fromEntries(Object.entries(sugestoes || {}).map(([k, v]) => [k, v.value])),
    );

  return (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-purple-600" />
          Resultados da Análise IA
        </DialogTitle>
        <DialogDescription>
          Dados extraídos dos documentos de {clientName || "cliente"}
        </DialogDescription>
      </DialogHeader>

      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {results?.analysis && (
          <>
            {/* Documentos Analisados */}
            <div className="space-y-2">
              <h4 className="font-medium text-sm flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Documentos Processados ({results.analysis.documents_analyzed?.length || 0})
              </h4>
              <div className="grid gap-2">
                {results.analysis.documents_analyzed?.map((doc, idx) => (
                  <div key={idx} className="p-2 rounded border bg-muted/30">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{doc.file_name}</span>
                      <Badge variant="outline" className="text-xs">
                        {doc.tipo_documento || "outro"}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      Confiança: {Math.round((doc.confianca || 0) * 100)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Campos Vazios (Podem ser Preenchidos) */}
            {results.analysis.comparison?.empty_fields?.length > 0 && (
              <div className="space-y-2">
                <h4 className="font-medium text-sm flex items-center gap-2 text-green-600">
                  <CheckCircle className="h-4 w-4" />
                  Campos a Preencher ({results.analysis.comparison.empty_fields.length})
                </h4>
                <div className="grid gap-2">
                  {results.analysis.comparison.empty_fields.map((field, idx) => {
                    // Obter confiança do campo via auto_fill_suggestions
                    const suggestion = results.analysis.auto_fill_suggestions?.[field.field];
                    const conf = suggestion?.confidence;
                    const pct = Math.round((conf || 0) * 100);
                    const confBadge = conf >= 0.8
                      ? "bg-green-100 text-green-700"
                      : conf >= 0.6
                        ? "bg-amber-100 text-amber-700"
                        : "bg-red-100 text-red-700";
                    return (
                      <div key={idx} className={`p-2 rounded border ${conf < 0.8 ? 'border-amber-300 bg-amber-50 dark:bg-amber-950/30' : 'bg-green-50 dark:bg-green-950/30'}`}>
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">{field.field}</span>
                          <div className="flex gap-1">
                            <Badge className="bg-green-100 text-green-700">Novo</Badge>
                            {conf !== undefined && (
                              <Badge className={`text-[10px] ${confBadge}`}>
                                {pct}%
                              </Badge>
                            )}
                          </div>
                        </div>
                        <p className={`text-sm mt-1 ${conf < 0.8 ? 'text-amber-700 dark:text-amber-300' : 'text-green-700 dark:text-green-300'}`}>
                          {field.suggested_value}
                        </p>
                        {conf < 0.8 && conf !== undefined && (
                          <p className="text-[10px] text-amber-600 mt-1">⚠️ Baixa confiança — verifique manualmente</p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          Fonte: {field.source}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Campos com Diferenças */}
            {results.analysis.comparison?.different?.length > 0 && (
              <div className="space-y-2">
                <h4 className="font-medium text-sm flex items-center gap-2 text-amber-600">
                  <AlertCircle className="h-4 w-4" />
                  Dados Divergentes ({results.analysis.comparison.different.length})
                </h4>
                <div className="grid gap-2">
                  {results.analysis.comparison.different.map((field, idx) => (
                    <div key={idx} className="p-2 rounded border bg-amber-50 dark:bg-amber-950/30">
                      <div className="text-sm font-medium">{field.field}</div>
                      <div className="grid grid-cols-2 gap-2 mt-1">
                        <div className="text-xs">
                          <span className="text-muted-foreground">Actual:</span>
                          <p className="font-medium">{field.current_value}</p>
                        </div>
                        <div className="text-xs">
                          <span className="text-muted-foreground">Documento:</span>
                          <p className="font-medium text-amber-700">{field.document_value}</p>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="mt-2 text-xs bg-amber-100 hover:bg-amber-200 border-amber-300"
                        onClick={() => onApplySuggestions({ [field.field]: field.document_value })}
                        disabled={applying}
                      >
                        {applying ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <CheckCircle className="h-3 w-3 mr-1" />}
                        Usar valor do documento
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Campos Coincidentes */}
            {results.analysis.comparison?.matching?.length > 0 && (
              <div className="space-y-2">
                <h4 className="font-medium text-sm flex items-center gap-2 text-muted-foreground">
                  <CheckCircle className="h-4 w-4" />
                  Dados Confirmados ({results.analysis.comparison.matching.length})
                </h4>
                <div className="flex flex-wrap gap-1">
                  {results.analysis.comparison.matching.map((field, idx) => (
                    <Badge key={idx} variant="outline" className="text-xs">
                      {field.field}: {field.value?.toString().substring(0, 20)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <DialogFooter className="flex gap-2 pt-4 border-t">
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Fechar
        </Button>
        {results?.analysis?.auto_fill_suggestions && 
          Object.keys(results.analysis.auto_fill_suggestions).length > 0 && (
          <Button
            onClick={aplicarSugestoes}
            disabled={applying}
            className="bg-purple-600 hover:bg-purple-700"
          >
            {applying ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Sparkles className="h-4 w-4 mr-2" />
            )}
            Aplicar Sugestões
          </Button>
        )}
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
