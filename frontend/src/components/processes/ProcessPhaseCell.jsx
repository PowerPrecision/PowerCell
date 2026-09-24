/**
 * ProcessPhaseCell — célula da fase na listagem de processos (Ponto 16).
 *
 * PORQUÊ: mudar a fase obrigava a abrir os Detalhes do processo, gravar
 * e voltar atrás. Numa listagem de 40 linhas isso são 40 idas e voltas.
 * A célula passa a ser um dropdown — mas continua a gravar pelo mesmo
 * `PUT /processes/{id}` dos Detalhes, para não furar a auditoria, o
 * histórico nem o motor de automações.
 *
 * Componente de APRESENTAÇÃO: diz o que aconteceu (`onChange(fase)`) e
 * não sabe gravar nada. Quem decide o que isso implica é a página.
 */
import { Badge } from "../ui/badge";
import { StatusBadge } from "../shared/StatusBadge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Trash2, Loader2 } from "lucide-react";
import {
  podeEditarFase,
  opcoesDeFase,
  deveGravarNovaFase,
} from "../../utils/inlinePhaseEdit";

/**
 * @param {object} props
 * @param {string} props.status — fase actual do processo
 * @param {string} props.role — papel efectivo do utilizador
 * @param {string} [props.baseRole] — papel base do JWT (`user.role`)
 * @param {Array<{name: string, label?: string, color?: string}>} props.workflowStatuses
 * @param {boolean} [props.isDeleted] — soft-delete (`is_deleted`)
 * @param {boolean} [props.saving] — gravação em curso nesta linha
 * @param {(fase: string) => void} props.onChange
 */
export default function ProcessPhaseCell({
  status,
  role,
  baseRole,
  workflowStatuses,
  isDeleted = false,
  saving = false,
  onChange,
}) {
  const eliminado = isDeleted || status === "eliminado";

  if (eliminado) {
    return (
      <Badge variant="destructive" className="gap-0.5" data-testid="fase-eliminado">
        <Trash2 className="h-3 w-3" />
        Eliminado
      </Badge>
    );
  }

  const editavel = podeEditarFase({ role, baseRole, status, isDeleted });
  if (!editavel) {
    return (
      <StatusBadge
        status={status}
        workflowStatuses={workflowStatuses}
        showOrder={false}
        className="capitalize"
      />
    );
  }

  const opcoes = opcoesDeFase(workflowStatuses, status);

  return (
    // O clique tem de morrer aqui: a linha da tabela navega para os
    // Detalhes no seu próprio onClick e levaria o utilizador embora
    // antes de ele chegar a escolher a fase.
    <div
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      role="presentation"
    >
      <Select
        value={status || undefined}
        disabled={saving}
        onValueChange={(nova) => {
          // A regra vive em `deveGravarNovaFase` (módulo puro): o
          // Radix já não dispara para o item seleccionado, mas isso é
          // uma garantia da biblioteca, não do produto.
          if (!deveGravarNovaFase(status, nova)) return;
          onChange?.(nova);
        }}
      >
        <SelectTrigger
          aria-label="Fase do processo"
          className="h-7 w-full min-w-[140px] max-w-[190px] text-xs capitalize"
        >
          {saving ? (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />A gravar…
            </span>
          ) : (
            <SelectValue />
          )}
        </SelectTrigger>
        <SelectContent>
          {opcoes.map((opcao) => (
            <SelectItem key={opcao.name} value={opcao.name} className="text-xs capitalize">
              {opcao.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
