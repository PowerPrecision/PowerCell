/**
 * UnifiedAuditTrail - "Filme da Lead" / Histórico de Auditoria
 * PACOTE DS — tabela rica: ícone da ação, quem, quando, descrição clara.
 *
 * Combina: alterações de fase, comentários/atividades, uploads, emails, atribuições.
 */
import { useState, useMemo } from "react";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Button } from "./ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";
import {
  ArrowRight, MessageSquare, FileText, Mail, UserPlus,
  Clock, Filter, ChevronDown, ChevronUp, CheckSquare, Globe, Pencil, Plus, Trash2,
} from "lucide-react";
import { pt } from "date-fns/locale";
import { safeFormat } from "../lib/utils";
import { safeString } from "../utils/safeString";
import { EmptyState } from "./ui/EmptyState";
import { hasRole } from "../utils/roleUtils";
import {
  AUDIT_EVENT_TYPES,
  classifyAuditEvent,
  describeAuditEvent,
  mergeAuditEvents,
} from "../utils/processAuditHistory";

const EVENT_TYPES = {
  status_change: { label: "Alteração de Estado", icon: ArrowRight, iconClass: "text-primary bg-primary/10" },
  comment: { label: "Comentário", icon: MessageSquare, iconClass: "text-primary bg-primary/10" },
  document: { label: "Documento", icon: FileText, iconClass: "text-primary bg-secondary" },
  email: { label: "Email", icon: Mail, iconClass: "text-primary bg-accent" },
  assignment: { label: "Atribuição", icon: UserPlus, iconClass: "text-primary bg-secondary" },
  task: { label: "Tarefa", icon: CheckSquare, iconClass: "text-accent-foreground bg-accent" },
  portal_upload: { label: "Portal", icon: Globe, iconClass: "text-primary bg-muted" },
  created: { label: "Criação", icon: Plus, iconClass: "text-primary bg-primary/10" },
  edit: { label: "Edição", icon: Pencil, iconClass: "text-muted-foreground bg-muted" },
  other: { label: "Outro", icon: Clock, iconClass: "text-muted-foreground bg-muted" },
};

function EventIcon({ type }) {
  const config = EVENT_TYPES[type] || EVENT_TYPES.other;
  const Icon = config.icon;
  return (
    <div
      className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${config.iconClass}`}
      title={config.label}
      aria-hidden="true"
    >
      <Icon className="h-3.5 w-3.5" />
    </div>
  );
}

function detailsText(event) {
  const oldVal = event.old_value ?? event.old_status;
  const newVal = event.new_value ?? event.new_status;
  if (oldVal != null && oldVal !== "" && newVal != null && newVal !== "") {
    return `${safeString(oldVal)} → ${safeString(newVal)}`;
  }
  if (event.field && (newVal != null && newVal !== "")) {
    return `${safeString(event.field)}: ${safeString(newVal)}`;
  }
  return "";
}

const UnifiedAuditTrail = ({
  history = [],
  activities = [],
  maxHeight = "500px",
  currentUser = null,
  onDeleteComment = null,
}) => {
  const [typeFilter, setTypeFilter] = useState("all");
  const [expanded, setExpanded] = useState(false);

  const allEvents = useMemo(
    () => mergeAuditEvents(history, activities),
    [history, activities],
  );

  const filteredEvents = useMemo(() => {
    if (typeFilter === "all") return allEvents;
    return allEvents.filter((e) => classifyAuditEvent(e) === typeFilter);
  }, [allEvents, typeFilter]);

  const displayEvents = expanded ? filteredEvents : filteredEvents.slice(0, 40);

  const typeCounts = useMemo(() => {
    const counts = {};
    allEvents.forEach((e) => {
      const t = classifyAuditEvent(e);
      counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
  }, [allEvents]);

  return (
    <div className="space-y-3" data-testid="unified-audit-trail">
      <div className="flex flex-wrap items-center gap-1.5">
        <Filter className="h-3.5 w-3.5 text-muted-foreground" />
        <Button
          variant={typeFilter === "all" ? "default" : "outline"}
          size="sm"
          className="h-6 text-[10px] px-2"
          onClick={() => setTypeFilter("all")}
        >
          Todos ({allEvents.length})
        </Button>
        {Object.entries(EVENT_TYPES).map(([key, config]) => {
          const count = typeCounts[key] || 0;
          if (count === 0) return null;
          const meta = AUDIT_EVENT_TYPES[key];
          return (
            <Button
              key={key}
              variant={typeFilter === key ? "default" : "outline"}
              size="sm"
              className="h-6 text-[10px] px-2"
              onClick={() => setTypeFilter(key)}
            >
              {meta?.label || config.label} ({count})
            </Button>
          );
        })}
      </div>

      <ScrollArea style={{ maxHeight }}>
        {filteredEvents.length === 0 ? (
          <EmptyState
            icon={Clock}
            title="Sem eventos registados"
            message="As alterações de fase, documentos, emails e notas aparecem aqui."
            className="py-8"
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"> </TableHead>
                <TableHead>Ação</TableHead>
                <TableHead className="w-[140px]">Utilizador</TableHead>
                <TableHead className="w-[150px]">Data / Hora</TableHead>
                <TableHead className="w-[220px]">Detalhes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayEvents.map((event, idx) => {
                const type = classifyAuditEvent(event);
                const timestamp = event.timestamp || event.created_at;
                const details = detailsText(event);
                return (
                  <TableRow
                    key={event.id || `event-${idx}`}
                    data-testid={`audit-event-${event.id || event.timestamp || idx}`}
                  >
                    <TableCell className="align-top pt-3">
                      <EventIcon type={type} />
                    </TableCell>
                    <TableCell className="align-top">
                      <p className="text-sm text-foreground leading-snug">
                        {describeAuditEvent(event)}
                      </p>
                      {type === "comment" && event.comment && event.description !== event.comment && (
                        <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">
                          {safeString(event.comment)}
                        </p>
                      )}
                    </TableCell>
                    <TableCell className="align-top text-sm">
                      {safeString(event.user_name) || "Sistema"}
                    </TableCell>
                    <TableCell className="align-top text-xs text-muted-foreground whitespace-nowrap">
                      {timestamp
                        ? safeFormat(timestamp, "dd/MM/yyyy HH:mm", { locale: pt })
                        : "—"}
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex items-start justify-between gap-1">
                        {details ? (
                          <Badge variant="outline" className="text-[10px] font-normal whitespace-normal">
                            {details}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                        {type === "comment" && onDeleteComment && currentUser && (
                          event.user_id === currentUser.id || hasRole(currentUser, "admin")
                        ) && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0"
                            onClick={() => onDeleteComment(event.id)}
                            aria-label="Eliminar nota"
                          >
                            <Trash2 className="h-3 w-3 text-destructive" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}

        {!expanded && filteredEvents.length > 40 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs"
            onClick={() => setExpanded(true)}
          >
            <ChevronDown className="h-3.5 w-3.5 mr-1" />
            Ver mais {filteredEvents.length - 40} eventos
          </Button>
        )}
        {expanded && filteredEvents.length > 40 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs"
            onClick={() => setExpanded(false)}
          >
            <ChevronUp className="h-3.5 w-3.5 mr-1" />
            Colapsar
          </Button>
        )}
      </ScrollArea>
    </div>
  );
};

export default UnifiedAuditTrail;
