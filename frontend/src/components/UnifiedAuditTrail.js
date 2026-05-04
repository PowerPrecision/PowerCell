/**
 * UnifiedAuditTrail - "Filme da Lead"
 * O24 - Vista unificada de todos os eventos do processo em ordem cronológica
 * 
 * Combina: alterações de status, comentários/atividades, uploads de documentos,
 * envio de emails, atribuições, etc.
 */
import React, { useState, useMemo } from "react";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Button } from "./ui/button";
import {
  ArrowRight, MessageSquare, FileText, Mail, UserPlus,
  Clock, Filter, ChevronDown, ChevronUp, CheckSquare, Globe
} from "lucide-react";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

const EVENT_TYPES = {
  status_change: { label: "Alteração de Estado", icon: ArrowRight, color: "text-blue-500 bg-blue-50 dark:bg-blue-950" },
  comment: { label: "Comentário", icon: MessageSquare, color: "text-green-500 bg-green-50 dark:bg-green-950" },
  document: { label: "Documento", icon: FileText, color: "text-purple-500 bg-purple-50 dark:bg-purple-950" },
  email: { label: "Email", icon: Mail, color: "text-orange-500 bg-orange-50 dark:bg-orange-950" },
  assignment: { label: "Atribuição", icon: UserPlus, color: "text-indigo-500 bg-indigo-50 dark:bg-indigo-950" },
  task: { label: "Tarefa", icon: CheckSquare, color: "text-amber-500 bg-amber-50 dark:bg-amber-950" },
  portal_upload: { label: "Portal", icon: Globe, color: "text-teal-500 bg-teal-50 dark:bg-teal-950" },
  other: { label: "Outro", icon: Clock, color: "text-gray-500 bg-gray-50 dark:bg-gray-950" },
};

const classifyEvent = (entry) => {
  if (entry.type === "status_change" || entry.action?.includes("status") || entry.field === "status") return "status_change";
  if (entry.type === "comment" || entry.comment) return "comment";
  if (entry.action === "DOCUMENT_UPLOADED_BY_CLIENT") return "portal_upload";
  if (entry.type === "document" || entry.action?.includes("document") || entry.action?.includes("upload")) return "document";
  if (entry.type === "email" || entry.action?.includes("email")) return "email";
  if (entry.type === "assignment" || entry.action?.includes("atribu")) return "assignment";
  if (entry.type === "task" || entry.action?.includes("tarefa") || entry.field === "tarefa") return "task";
  return "other";
};

const EventItem = ({ event }) => {
  const type = classifyEvent(event);
  const config = EVENT_TYPES[type];
  const Icon = config.icon;
  const timestamp = event.timestamp || event.created_at;

  return (
    <div className="flex gap-3 py-2" data-testid={`audit-event-${event.id || event.timestamp}`}>
      <div className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 ${config.color}`}>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            {type === "status_change" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Sistema"}</span>
                {" alterou estado: "}
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">{event.old_value || "—"}</Badge>
                {" → "}
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">{event.new_value || event.new_status || "—"}</Badge>
              </p>
            )}
            {type === "comment" && (
              <div>
                <span className="text-sm font-medium">{event.user_name || "Anónimo"}</span>
                {event.source === "trello" && <Badge variant="outline" className="ml-1 text-[9px] px-1 py-0">trello</Badge>}
                <p className="text-sm text-muted-foreground mt-0.5 line-clamp-3">{event.comment}</p>
              </div>
            )}
            {type === "document" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Sistema"}</span>
                {" "}{event.action || "carregou documento"}
                {event.field && <span className="text-muted-foreground"> ({event.field})</span>}
              </p>
            )}
            {type === "email" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Sistema"}</span>
                {" "}{event.action || "enviou email"}
              </p>
            )}
            {type === "assignment" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Sistema"}</span>
                {" "}{event.action || "atribuiu processo"}
                {event.new_value && <span className="text-muted-foreground"> a {event.new_value}</span>}
              </p>
            )}
            {type === "task" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Sistema"}</span>
                {" "}{event.action || "ação de tarefa"}
                {event.new_value && <span className="text-muted-foreground font-medium"> — {event.new_value}</span>}
              </p>
            )}
            {type === "portal_upload" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Cliente (Portal)"}</span>
                {" submeteu documento: "}
                <span className="font-medium">{event.new_value || event.field}</span>
              </p>
            )}
            {type === "other" && (
              <p className="text-sm">
                <span className="font-medium">{event.user_name || "Sistema"}</span>
                {" "}{event.action || event.comment || "ação registada"}
              </p>
            )}
          </div>
          {timestamp && (
            <span className="text-[10px] text-muted-foreground whitespace-nowrap shrink-0">
              {format(parseISO(timestamp), "dd/MM HH:mm", { locale: pt })}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

const UnifiedAuditTrail = ({ history = [], activities = [], maxHeight = "400px" }) => {
  const [typeFilter, setTypeFilter] = useState("all");
  const [expanded, setExpanded] = useState(false);
  
  // Merge history + activities into a single chronological list
  const allEvents = useMemo(() => {
    const events = [];
    
    // Add history entries (status changes, field edits)
    history.forEach(h => {
      events.push({
        ...h,
        _sortDate: h.created_at || h.timestamp || "2000-01-01",
      });
    });
    
    // Add activities (comments, etc.) - avoid duplicates
    const historyIds = new Set(history.map(h => h.id).filter(Boolean));
    activities.forEach(a => {
      if (!historyIds.has(a.id)) {
        events.push({
          ...a,
          type: a.type || "comment",
          _sortDate: a.created_at || a.timestamp || "2000-01-01",
        });
      }
    });
    
    // Sort chronologically (newest first)
    events.sort((a, b) => new Date(b._sortDate) - new Date(a._sortDate));
    return events;
  }, [history, activities]);
  
  // Apply filter
  const filteredEvents = useMemo(() => {
    if (typeFilter === "all") return allEvents;
    return allEvents.filter(e => classifyEvent(e) === typeFilter);
  }, [allEvents, typeFilter]);
  
  const displayEvents = expanded ? filteredEvents : filteredEvents.slice(0, 20);
  
  // Count by type
  const typeCounts = useMemo(() => {
    const counts = {};
    allEvents.forEach(e => {
      const t = classifyEvent(e);
      counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
  }, [allEvents]);

  return (
    <div className="space-y-3" data-testid="unified-audit-trail">
      {/* Filter chips */}
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
          return (
            <Button
              key={key}
              variant={typeFilter === key ? "default" : "outline"}
              size="sm"
              className="h-6 text-[10px] px-2"
              onClick={() => setTypeFilter(key)}
            >
              {config.label} ({count})
            </Button>
          );
        })}
      </div>
      
      {/* Events list */}
      <ScrollArea style={{ maxHeight }}>
        {filteredEvents.length === 0 ? (
          <p className="text-center text-muted-foreground text-sm py-6">Sem eventos registados</p>
        ) : (
          <div className="divide-y divide-border">
            {displayEvents.map((event, idx) => (
              <EventItem key={event.id || `event-${idx}`} event={event} />
            ))}
          </div>
        )}
        
        {!expanded && filteredEvents.length > 20 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs"
            onClick={() => setExpanded(true)}
          >
            <ChevronDown className="h-3.5 w-3.5 mr-1" />
            Ver mais {filteredEvents.length - 20} eventos
          </Button>
        )}
        {expanded && filteredEvents.length > 20 && (
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
