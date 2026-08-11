/**
 * AssignmentContextCard — Card de contexto fixo (coluna direita) com a
 * equipa responsável pelo processo, a prioridade e os prazos mais críticos.
 *
 * PORQUÊ: Substitui o antigo botão "Atribuições" solto no cabeçalho — a
 * gestão de atribuições passa a viver junto da informação que ela edita,
 * sempre visível independentemente do separador ativo. A Prioridade
 * (antigo cartão isolado no Resumo) segue a mesma lógica: é um metadado
 * compacto do processo, por isso vive aqui como um badge/dropdown em vez
 * de ocupar uma secção própria.
 */
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Users, UserCog, Clock, AlertTriangle, ChevronDown } from "lucide-react";
import { differenceInCalendarDays } from "date-fns";
import { pt } from "date-fns/locale";
import { safeString } from "../../utils/safeString";
import { safeParseISO, safeFormat } from "../../lib/utils";

const PRIORITY_OPTIONS = [
  { value: "baixa", label: "Baixa", badgeVariant: "outline" },
  { value: "media", label: "Média", badgeVariant: "secondary" },
  { value: "alta", label: "Alta", badgeVariant: "destructive" },
];

function PrioritySelector({ value, onChange, disabled }) {
  const current = PRIORITY_OPTIONS.find((o) => o.value === value) || PRIORITY_OPTIONS[1];

  if (disabled) {
    return (
      <Badge variant={current.badgeVariant} className="text-xs font-normal" data-testid="priority-badge-readonly">
        {current.label}
      </Badge>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        data-testid="priority-selector-trigger"
      >
        <Badge variant={current.badgeVariant} className="text-xs font-normal gap-1 cursor-pointer">
          {current.label}
          <ChevronDown className="h-3 w-3 opacity-70" />
        </Badge>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Prioridade</DropdownMenuLabel>
        {PRIORITY_OPTIONS.map((opt) => (
          <DropdownMenuItem
            key={opt.value}
            onSelect={() => onChange(opt.value)}
            data-testid={`priority-option-${opt.value}`}
          >
            <Badge variant={opt.badgeVariant} className="text-xs font-normal">
              {opt.label}
            </Badge>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function TeamRow({ label, names }) {
  return (
    <div className="flex items-start justify-between gap-2 py-1">
      <span className="text-xs text-muted-foreground shrink-0 pt-0.5">{label}</span>
      {names.length > 0 ? (
        <div className="flex flex-wrap justify-end gap-1">
          {names.map((name, idx) => (
            <Badge key={idx} variant="secondary" className="text-xs font-normal">
              {name}
            </Badge>
          ))}
        </div>
      ) : (
        <span className="text-xs text-muted-foreground italic">Não atribuído</span>
      )}
    </div>
  );
}

export default function AssignmentContextCard({
  process,
  consultorNames = [],
  mediadorNames = [],
  deadlines = [],
  onManageAssignment,
  canManageAssignment,
  priority = "media",
  onPriorityChange,
  canEditPriority = false,
}) {
  const indexacaoName = safeString(process?.indexacao_name);
  const parceiroName = safeString(process?.parceiro_name);

  const upcomingDeadlines = [...deadlines]
    .filter((d) => d && !d.completed && d.due_date)
    .map((d) => ({ ...d, _date: safeParseISO(d.due_date) }))
    .filter((d) => d._date)
    .sort((a, b) => a._date - b._date)
    .slice(0, 3);

  const today = new Date();

  return (
    <Card className="border-border" data-testid="assignment-context-card">
      <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base flex items-center gap-2">
          <Users className="h-4 w-4 text-primary" />
          Atribuição
        </CardTitle>
        {canManageAssignment && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs gap-1"
            onClick={onManageAssignment}
            data-testid="assign-users-btn"
          >
            <UserCog className="h-3.5 w-3.5" />
            Gerir
          </Button>
        )}
      </CardHeader>
      <CardContent className="pt-0 space-y-1">
        <div className="flex items-center justify-between gap-2 py-1">
          <span className="text-xs text-muted-foreground shrink-0">Prioridade</span>
          <PrioritySelector
            value={priority}
            onChange={onPriorityChange}
            disabled={!canEditPriority}
          />
        </div>
        <TeamRow label="Consultor(es)" names={consultorNames} />
        <TeamRow label="Mediador(es)" names={mediadorNames} />
        {indexacaoName && <TeamRow label="Indexação" names={[indexacaoName]} />}
        {parceiroName && <TeamRow label="Parceiro" names={[parceiroName]} />}

        <div className="pt-3 mt-2 border-t border-border">
          <p className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            Prazos Críticos
          </p>
          {upcomingDeadlines.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">Sem prazos pendentes</p>
          ) : (
            <ul className="space-y-1.5">
              {upcomingDeadlines.map((d) => {
                const overdue = differenceInCalendarDays(d._date, today) < 0;
                return (
                  <li key={d.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate flex items-center gap-1.5">
                      {overdue && <AlertTriangle className="h-3 w-3 text-destructive shrink-0" aria-hidden="true" />}
                      <span className="truncate">{safeString(d.title)}</span>
                    </span>
                    <span className={overdue ? "text-destructive font-medium shrink-0" : "text-muted-foreground shrink-0"}>
                      {safeFormat(d.due_date, "dd/MM/yy", { locale: pt })}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
