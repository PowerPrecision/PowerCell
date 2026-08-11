/**
 * Cabeçalho reutilizável de cartão com toggle de edição e collapse.
 * Extraído de ProcessDetails.js.
 */
import { Button } from "../ui/button";
import { Pencil, ChevronDown, ChevronUp, Loader2 } from "lucide-react";

export default function CardHeaderWithEdit({
  title,
  cardKey,
  icon: Icon,
  canEdit,
  collapsible,
  collapsed = false,
  empty = false,
  isEditing = false,
  isProcessLocked = false,
  saving = false,
  onToggleCollapse,
  onStartEdit,
  onCancelEdit,
  onSave,
}) {
  return (
    <div className="flex items-center justify-between">
      <div
        className="flex items-center gap-2 cursor-pointer select-none"
        onClick={() => collapsible && onToggleCollapse?.(cardKey)}
        onKeyDown={(e) => {
          if (!collapsible) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggleCollapse?.(cardKey);
          }
        }}
        role={collapsible ? "button" : undefined}
        tabIndex={collapsible ? 0 : undefined}
      >
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
        <h4 className="font-semibold text-sm">{title}</h4>
        {collapsible && (
          collapsed
            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            : <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        {empty && !collapsed && (
          <span className="text-xs text-muted-foreground italic ml-1">— Sem dados preenchidos</span>
        )}
      </div>
      {canEdit && !isProcessLocked && !isEditing && (
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onStartEdit?.(cardKey)}
          title="Editar"
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      )}
      {canEdit && !isProcessLocked && isEditing && (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => onCancelEdit?.()}
          >
            Cancelar
          </Button>
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={onSave}
            disabled={saving}
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Guardar"}
          </Button>
        </div>
      )}
    </div>
  );
}
