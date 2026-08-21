/**
 * PACOTE DU — Dialog de detalhe de evento do calendário.
 * Não navega sozinho: o botão "Abrir Processo" é explícito.
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { CalendarDays, User, Tag, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { formatDate, formatDateTime } from "../../lib/utils";
import { eventHasClockTime, eventKindLabel } from "../../utils/agendaCalendar";
import { processDeepLink } from "../../utils/processDeepLink";

export default function CalendarEventDialog({ event, open, onOpenChange, showProcessLink = true }) {
  const navigate = useNavigate();
  if (!event) return null;

  const dateLabel = eventHasClockTime(event)
    ? formatDateTime(event.due_date || event.start_date || event.date)
    : formatDate(event.due_date || event.start_date || event.date);
  const endLabel = event.end_date && event.end_date !== event.due_date
    ? ` – ${eventHasClockTime(event) ? formatDateTime(event.end_date) : formatDate(event.end_date)}`
    : "";

  const openProcess = () => {
    if (!event.process_id) return;
    onOpenChange?.(false);
    navigate(processDeepLink(event.process_id));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="calendar-event-dialog">
        <DialogHeader>
          <DialogTitle className="text-base">{event.title || "Evento"}</DialogTitle>
          <DialogDescription>
            Detalhes da marcação — abra o processo só se precisar.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-muted-foreground shrink-0" />
            <span>{dateLabel}{endLabel}</span>
          </div>
          <div className="flex items-center gap-2">
            <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
            <Badge variant="outline">{eventKindLabel(event.type)}</Badge>
          </div>
          {(event.client_name || event.process_number) && (
            <div className="flex items-center gap-2">
              <User className="h-4 w-4 text-muted-foreground shrink-0" />
              <span>
                {event.client_name || "Cliente"}
                {event.process_number ? ` · #${event.process_number}` : ""}
              </span>
            </div>
          )}
          {event.description && (
            <p className="text-muted-foreground whitespace-pre-wrap">{event.description}</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange?.(false)}>
            Fechar
          </Button>
          {event.process_id && showProcessLink && (
            <Button onClick={openProcess} className="gap-1.5" data-testid="calendar-open-process">
              <ExternalLink className="h-4 w-4" />
              Abrir Processo
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
