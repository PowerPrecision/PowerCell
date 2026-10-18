/**
 * DocumentReviewModal — Revisão Human-in-the-Loop de sugestões IA por documento.
 *
 * PACOTE DJ — Implementa o modal de revisão de sugestões de metadados geradas
 * pela IA (categoria, validade, nome, filename). A IA escreve em campos
 * `suggested_*` paralelos (não toca em `ai_*`); o consultor aprova ou rejeita
 * explicitamente antes de aplicar.
 *
 * Padrão visual: clone do `DataConflictResolver.jsx` (grelha 3 colunas
 * "Actual → Sugerido" + botões Aceitar/Rejeitar), adaptado a um único
 * documento e montado num painel LATERAL (`Sheet`, QA-6): o documento fica
 * visível ao lado da revisão, que é o que um modal central escondia.
 *
 * Decisões:
 * - Cada campo é seleccionável individualmente (toggle) — o consultor pode
 *   aplicar apenas um subconjunto das sugestões (ex: aceitar a categoria mas
 *   rejeitar a validade).
 * - Campos sem sugestão da IA (`suggested_*` vazio) não são mostrados.
 * - A selecção parte SÓ dos campos que existem e mudam o valor atual. Partir de
 *   uma lista fixa de quatro mostrava «A IA não encontrou sugestões» por cima de
 *   um botão «Aplicar Selecionadas (4)» (QA-6): a contagem tem de vir do que se vê.
 * - Confiança (confidence) aparece como Badge com cor semântica (primary ≥0.8,
 *   accent-foreground ≥0.6, destructive <0.6).
 * - Usa apenas tokens Shadcn (sem cores Tailwind cruas) — dark-mode safe.
 *
 * @param {Object} props
 * @param {boolean} props.open - Estado de abertura do Dialog
 * @param {Function} props.onOpenChange - Setter (open) => void
 * @param {Object} props.doc - Objecto documento vindo do endpoint
 *   `/documents/{doc_id}/ai-analyze-review` ou da listagem de ficheiros
 *   (deve incluir `suggested_*`, `ai_*`/`current_*`, `ai_confidence`, etc.)
 * @param {Function} [props.onResolved] - Callback chamado após aplicar/rejeitar
 *   (tipicamente `fetchFiles` para refrescar a lista)
 */
import { useState, useMemo, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "./ui/sheet";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import {
  Sparkles,
  Check,
  X,
  ArrowRight,
  Loader2,
  BrainCircuit,
  FileText,
  Calendar,
  Tag,
} from "lucide-react";
import { toast } from "sonner";
import { applyAIReview, rejectAIReview } from "../services/api";

// Tokens semânticos de cor para o badge de confiança.
// ≥0.8 → primary (verde institucional), ≥0.6 → accent (âmbar), <0.6 → destructive.
const confidenceColorClass = (conf) => {
  if (conf == null) return "text-muted-foreground";
  if (conf >= 0.8) return "text-primary";
  if (conf >= 0.6) return "text-accent-foreground";
  return "text-destructive";
};

const formatValue = (value) => {
  if (value == null || value === "") return "—";
  if (typeof value === "string") return value;
  return String(value);
};

export function DocumentReviewModal({ open, onOpenChange, doc, onResolved }) {
  const [applying, setApplying] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  // Campos seleccionados para aplicação parcial (toggle por campo).
  const [selectedFields, setSelectedFields] = useState(new Set());

  // Constrói a lista de campos a rever. Apenas campos com sugestão preenchida
  // são exibidos — o resto é omitido para evitar ruído visual.
  const fields = useMemo(() => {
    if (!doc) return [];
    const suggestions = doc.suggestions || {};
    const current = doc.current || {};

    return [
      {
        key: "nome",
        label: "Nome",
        icon: FileText,
        current: current.nome || doc.suggested_nome_current || doc.extracted_data?.nome_completo?.nome || doc.ai_nome,
        suggested: suggestions.nome || doc.suggested_nome,
        confidence: suggestions.confidence ?? doc.suggested_confidence ?? doc.ai_confidence,
      },
      {
        key: "categoria",
        label: "Categoria",
        icon: Tag,
        current: current.categoria || current.category || doc.ai_category || doc.category,
        suggested: suggestions.categoria || suggestions.category || doc.suggested_category,
        confidence: suggestions.confidence ?? doc.suggested_confidence ?? doc.ai_confidence,
      },
      {
        key: "validade",
        label: "Data de Validade",
        icon: Calendar,
        current: current.validade || current.expiry_date || doc.ai_expiry_date || doc.expiry_date,
        suggested: suggestions.validade || suggestions.expiry_date || doc.suggested_expiry_date,
        confidence: suggestions.confidence ?? doc.suggested_confidence ?? doc.ai_confidence,
      },
      {
        key: "filename",
        label: "Nome do Ficheiro",
        icon: FileText,
        current: current.filename || doc.filename || doc.original_filename,
        suggested: suggestions.filename || doc.suggested_filename,
        confidence: suggestions.confidence ?? doc.suggested_confidence ?? doc.ai_confidence,
      },
    ].filter((f) => f.suggested != null && f.suggested !== "");
  }, [doc]);

  // Só conta como sugestão o que mudaria o valor: «igual ao atual» não é uma alteração.
  const camposComAlteracao = useMemo(
    () => fields.filter((f) => f.suggested !== f.current).map((f) => f.key),
    [fields]
  );
  const assinaturaDasSugestoes = camposComAlteracao.join("|");

  // Ao abrir (ou quando o documento / as sugestões mudam) a selecção parte dos
  // campos que se VÊEM com alteração — nunca de uma lista fixa.
  useEffect(() => {
    if (open && doc) {
      setSelectedFields(new Set(assinaturaDasSugestoes ? assinaturaDasSugestoes.split("|") : []));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reage ao id do documento e às sugestões que ele traz, não a mutações internas de `doc`.
  }, [open, doc?.doc_id, doc?.id, assinaturaDasSugestoes]);

  // Early return depois dos hooks — não pode ser antes dos hooks (Rules of Hooks).
  if (!doc) return null;

  const aplicaveis = camposComAlteracao.filter((k) => selectedFields.has(k));
  const semSugestoes = fields.length === 0;

  const docId = doc.doc_id || doc.id;
  const docName = doc.filename || doc.original_filename || "Documento";

  const toggleField = (key) => {
    setSelectedFields((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleApply = async () => {
    if (!docId) {
      toast.error("Documento inválido — ID em falta.");
      return;
    }
    setApplying(true);
    try {
      const fieldsToApply = aplicaveis;
      await applyAIReview(docId, { fields: fieldsToApply });
      toast.success("Sugestões aplicadas com sucesso.");
      onOpenChange?.(false);
      if (onResolved) onResolved();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erro ao aplicar sugestões.");
    } finally {
      setApplying(false);
    }
  };

  const handleReject = async () => {
    if (!docId) {
      toast.error("Documento inválido — ID em falta.");
      return;
    }
    setRejecting(true);
    try {
      await rejectAIReview(docId, {});
      toast.success("Sugestões rejeitadas.");
      onOpenChange?.(false);
      if (onResolved) onResolved();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erro ao rejeitar sugestões.");
    } finally {
      setRejecting(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-xl overflow-hidden flex flex-col gap-0"
        data-testid="revisao-sugestoes-documento"
      >
        <SheetHeader className="text-left">
          <SheetTitle className="flex items-center gap-2">
            <BrainCircuit className="h-5 w-5 text-primary" />
            Revisão de Sugestões IA
          </SheetTitle>
          <SheetDescription className="truncate" title={docName}>
            {docName} — reveja as sugestões da IA antes de aplicar.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 min-h-0 pr-4">
          <div className="space-y-3 py-2">
            {semSugestoes ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                A IA não encontrou sugestões para este documento.
              </p>
            ) : (
              fields.map((field) => {
                const Icon = field.icon;
                const isSelected = selectedFields.has(field.key);
                const hasSuggestion = field.suggested && field.suggested !== field.current;
                return (
                  <div
                    key={field.key}
                    className={`rounded-lg border p-3 transition-colors ${
                      isSelected
                        ? "border-primary/30 bg-primary/5"
                        : "border-border bg-muted/30"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2 gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="text-sm font-medium truncate">{field.label}</span>
                        {field.confidence != null && (
                          <Badge
                            variant="outline"
                            className={`text-[10px] h-4 px-1.5 shrink-0 ${confidenceColorClass(field.confidence)}`}
                          >
                            {Math.round((field.confidence || 0) * 100)}% confiança
                          </Badge>
                        )}
                      </div>
                      {hasSuggestion && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2 text-xs shrink-0"
                          onClick={() => toggleField(field.key)}
                          type="button"
                        >
                          {isSelected ? (
                            <>
                              <Check className="h-3 w-3 mr-1" /> Selecionado
                            </>
                          ) : (
                            <>
                              <X className="h-3 w-3 mr-1" /> Ignorar
                            </>
                          )}
                        </Button>
                      )}
                    </div>
                    {hasSuggestion ? (
                      <div className="grid grid-cols-[1fr_auto_1fr] gap-2 items-center">
                        <div className="p-2 rounded border border-border bg-background">
                          <p className="text-[10px] text-muted-foreground mb-0.5">Atual</p>
                          <p className="text-sm font-medium truncate" title={formatValue(field.current)}>
                            {formatValue(field.current)}
                          </p>
                        </div>
                        <ArrowRight className="h-4 w-4 text-muted-foreground" />
                        <div className="p-2 rounded border border-primary/20 bg-primary/5">
                          <p className="text-[10px] text-primary mb-0.5 flex items-center gap-1">
                            <Sparkles className="h-3 w-3" /> Sugerido
                          </p>
                          <p className="text-sm font-medium truncate" title={formatValue(field.suggested)}>
                            {formatValue(field.suggested)}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground italic">
                        {field.suggested
                          ? "Sem alteração sugerida (valor igual ao atual)."
                          : "Sem sugestão."}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>

        <SheetFooter className="border-t pt-4 gap-2 sm:gap-2 sm:flex-row sm:justify-end">
          {semSugestoes ? (
            <Button variant="outline" onClick={() => onOpenChange?.(false)} type="button">
              Fechar
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={handleReject}
                disabled={rejecting || applying}
                type="button"
              >
                {rejecting ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <X className="h-4 w-4 mr-2" />
                )}
                Rejeitar Tudo
              </Button>
              <Button
                onClick={handleApply}
                disabled={applying || rejecting || aplicaveis.length === 0}
                type="button"
              >
                {applying ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Check className="h-4 w-4 mr-2" />
                )}
                Aplicar Selecionadas ({aplicaveis.length})
              </Button>
            </>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

export default DocumentReviewModal;
