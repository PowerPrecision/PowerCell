/**
 * PACOTE DO.2 — Calendário visual mensal/semanal (Shadcn Calendar).
 * Consome eventos/prazos da Agenda (Pacote DH). Dias com marcações
 * mostram um ponto; o dia seleccionado lista os títulos.
 */
import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Calendar } from "../ui/calendar";
import { ScrollArea } from "../ui/scroll-area";
import { EmptyState } from "../ui/EmptyState";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { addWeeks, format, isSameDay } from "date-fns";
import { pt } from "date-fns/locale";
import { cn } from "../../lib/utils";
import {
  agendaDateKey,
  eventKindLabel,
  groupEventsByDay,
  parseAgendaDate,
  weekDaysFrom,
} from "../../utils/agendaCalendar";

export default function AgendaCalendar({
  events = [],
  title = "Calendário",
  description,
  onEventClick,
  className,
  compact = false,
}) {
  const [view, setView] = useState("month");
  const [selected, setSelected] = useState(new Date());
  const [weekAnchor, setWeekAnchor] = useState(new Date());

  const byDay = useMemo(() => groupEventsByDay(events), [events]);
  const selectedKey = agendaDateKey(selected);
  const selectedEvents = byDay.get(selectedKey) || [];

  const eventDates = useMemo(
    () =>
      [...byDay.keys()]
        .map((key) => parseAgendaDate(key))
        .filter(Boolean),
    [byDay]
  );

  const weekDays = useMemo(() => weekDaysFrom(weekAnchor), [weekAnchor]);

  return (
    <Card className={cn("border-border", className)} data-testid="agenda-calendar">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <CalendarDays className="h-5 w-5 text-primary" />
              {title}
            </CardTitle>
            {description && (
              <CardDescription className="mt-1">{description}</CardDescription>
            )}
          </div>
          <ToggleGroup
            type="single"
            value={view}
            onValueChange={(v) => {
              if (!v) return;
              setView(v);
              if (v === "week") setWeekAnchor(selected);
            }}
            size="sm"
            variant="outline"
            aria-label="Vista do calendário"
          >
            <ToggleGroupItem value="month" className="px-3 text-xs">
              Mensal
            </ToggleGroupItem>
            <ToggleGroupItem value="week" className="px-3 text-xs">
              Semanal
            </ToggleGroupItem>
          </ToggleGroup>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {view === "month" ? (
          <Calendar
            mode="single"
            selected={selected}
            onSelect={(date) => date && setSelected(date)}
            locale={pt}
            weekStartsOn={1}
            className="rounded-md border border-border mx-auto"
            modifiers={{ hasEvent: eventDates }}
            modifiersClassNames={{
              hasEvent:
                "relative font-semibold after:absolute after:bottom-0.5 after:left-1/2 after:-translate-x-1/2 after:h-1.5 after:w-1.5 after:rounded-full after:bg-primary",
            }}
          />
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setWeekAnchor((d) => addWeeks(d, -1))}
                aria-label="Semana anterior"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <p className="text-sm font-medium">
                {format(weekDays[0], "d MMM", { locale: pt })}
                {" – "}
                {format(weekDays[6], "d MMM yyyy", { locale: pt })}
              </p>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setWeekAnchor((d) => addWeeks(d, 1))}
                aria-label="Semana seguinte"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid grid-cols-7 gap-1">
              {weekDays.map((day) => {
                const key = agendaDateKey(day);
                const count = byDay.get(key)?.length || 0;
                const isSelected = isSameDay(day, selected);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSelected(day)}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-md border border-border p-2 text-xs transition-colors hover:bg-muted/60",
                      isSelected && "bg-primary text-primary-foreground border-primary"
                    )}
                  >
                    <span className="uppercase text-[10px] text-muted-foreground">
                      {format(day, "EEEEE", { locale: pt })}
                    </span>
                    <span className="font-medium">{format(day, "d")}</span>
                    {count > 0 && (
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          isSelected ? "bg-primary-foreground" : "bg-primary"
                        )}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="border-t border-border pt-3">
          <p className="text-sm font-medium mb-2">
            {format(selected, "d 'de' MMMM", { locale: pt })}
          </p>
          {selectedEvents.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              message="Sem agendamentos neste dia"
              className="py-6"
            />
          ) : (
            <ScrollArea className={compact ? "h-[160px]" : "h-[220px]"}>
              <ul className="space-y-2 pr-2">
                {selectedEvents.map((event) => (
                  <li key={event.id || `${event.title}-${event.due_date}`}>
                    <button
                      type="button"
                      disabled={!onEventClick}
                      onClick={() => onEventClick?.(event)}
                      className={cn(
                        "w-full text-left rounded-md border border-border bg-muted/30 p-2.5",
                        onEventClick && "hover:bg-muted/50 transition-colors"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium truncate">
                          {event.title || "Agendamento"}
                        </p>
                        <Badge variant={event.type === "event" ? "secondary" : "outline"}>
                          {eventKindLabel(event.type)}
                        </Badge>
                      </div>
                      {(event.client_name || event.description) && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">
                          {event.client_name || event.description}
                        </p>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </ScrollArea>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
