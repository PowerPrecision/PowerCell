/**
 * PACOTE DQ — Calendário global de grande dimensão (vistas Mensal e Semanal).
 * Cores por cliente (hash), prefixo do responsável na vista de equipa,
 * e blocos de ausência a cruzar os dias.
 */
import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { EmptyState } from "../ui/EmptyState";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react";
import {
  addMonths,
  addWeeks,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { pt } from "date-fns/locale";
import { cn } from "../../lib/utils";
import {
  agendaDateKey,
  calendarEventChipStyle,
  eventKindLabel,
  formatCalendarEventTitle,
  formatEventClockRange,
  formatEventStartTime,
  groupEventsByDay,
  isAbsenceEvent,
  weekDaysFrom,
} from "../../utils/agendaCalendar";

function EventChip({ event, isTeamView, viewerId, onClick, compact }) {
  const title = formatCalendarEventTitle(event, { viewerId, isTeamView });
  const chip = calendarEventChipStyle(event);
  const absence = isAbsenceEvent(event);
  const clock = compact ? formatEventStartTime(event) : formatEventClockRange(event);
  return (
    <button
      type="button"
      title={clock ? `${clock} ${title}` : title}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(event);
      }}
      className={cn(
        "w-full text-left rounded px-1.5 py-0.5 text-[11px] leading-tight truncate",
        compact ? "py-0.5" : "py-1",
        absence && "font-medium",
        chip.className
      )}
      style={chip.style}
      data-testid="calendar-event-chip"
    >
      {clock ? `${clock} ${title}` : title}
    </button>
  );
}

export default function GlobalCalendar({
  events = [],
  isTeamView = false,
  viewerId,
  onEventClick,
  onCreate,
  className,
}) {
  const [view, setView] = useState("month");
  const [cursor, setCursor] = useState(new Date());
  const [selected, setSelected] = useState(new Date());

  const byDay = useMemo(() => groupEventsByDay(events), [events]);
  const selectedKey = agendaDateKey(selected);
  const selectedEvents = byDay.get(selectedKey) || [];

  const monthDays = useMemo(() => {
    const start = startOfWeek(startOfMonth(cursor), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(cursor), { weekStartsOn: 1 });
    return eachDayOfInterval({ start, end });
  }, [cursor]);

  const weekDays = useMemo(() => weekDaysFrom(cursor), [cursor]);

  const goToday = () => {
    const now = new Date();
    setCursor(now);
    setSelected(now);
  };

  const headerLabel = view === "week"
    ? `${format(weekDays[0], "d MMM", { locale: pt })} – ${format(weekDays[6], "d MMM yyyy", { locale: pt })}`
    : format(cursor, "MMMM yyyy", { locale: pt });

  const shift = (dir) => {
    setCursor((d) => (view === "week" ? addWeeks(d, dir) : addMonths(d, dir)));
  };

  const renderDayCell = (day, { week } = {}) => {
    const key = agendaDateKey(day);
    const dayEvents = byDay.get(key) || [];
    const isSelected = isSameDay(day, selected);
    const inMonth = isSameMonth(day, cursor);
    const limit = week ? 8 : 3;
    const extra = dayEvents.length - limit;
    return (
      <button
        key={key}
        type="button"
        onClick={() => {
          setSelected(day);
          setCursor(day);
        }}
        onDoubleClick={() => onCreate?.(day)}
        className={cn(
          "flex flex-col items-stretch gap-1 border-border border-r border-b p-1.5 text-left transition-colors hover:bg-muted/40",
          week ? "min-h-[22rem]" : "min-h-[7.5rem] sm:min-h-[8.5rem]",
          isSelected && "bg-accent/40",
          !inMonth && !week && "bg-muted/20 text-muted-foreground"
        )}
      >
        <div className="flex items-center justify-between">
          <span
            className={cn(
              "text-xs font-medium h-6 w-6 flex items-center justify-center rounded-full",
              isSameDay(day, new Date()) && "bg-primary text-primary-foreground",
              isSelected && !isSameDay(day, new Date()) && "bg-foreground/10"
            )}
          >
            {format(day, "d")}
          </span>
          {dayEvents.length > 0 && (
            <span className="text-[10px] text-muted-foreground">{dayEvents.length}</span>
          )}
        </div>
        <div className="flex flex-col gap-0.5 min-h-0">
          {dayEvents.slice(0, limit).map((event) => (
            <EventChip
              key={event.id || `${event.title}-${event.due_date}`}
              event={event}
              isTeamView={isTeamView}
              viewerId={viewerId}
              onClick={onEventClick}
              compact={!week}
            />
          ))}
          {extra > 0 && (
            <span className="text-[10px] text-muted-foreground px-1">+{extra} mais</span>
          )}
        </div>
      </button>
    );
  };

  return (
    <Card className={cn("border-border", className)} data-testid="global-calendar">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base flex items-center gap-2 capitalize">
            <CalendarDays className="h-5 w-5 text-primary" />
            {headerLabel}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <ToggleGroup
              type="single"
              value={view}
              onValueChange={(v) => v && setView(v)}
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
            <div className="flex items-center gap-1">
              <Button type="button" variant="outline" size="icon" className="h-8 w-8" onClick={() => shift(-1)} aria-label="Anterior">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button type="button" variant="outline" size="sm" className="h-8" onClick={goToday}>
                Hoje
              </Button>
              <Button type="button" variant="outline" size="icon" className="h-8 w-8" onClick={() => shift(1)} aria-label="Seguinte">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
            {onCreate && (
              <Button type="button" size="sm" className="h-8 gap-1" onClick={() => onCreate(selected)}>
                <Plus className="h-4 w-4" />
                Novo
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border border-border overflow-hidden">
          <div className="grid grid-cols-7 bg-muted/40">
            {["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((label) => (
              <div key={label} className="px-2 py-2 text-center text-[11px] font-medium text-muted-foreground border-b border-border">
                {label}
              </div>
            ))}
          </div>
          {view === "month" ? (
            <div className="grid grid-cols-7">
              {monthDays.map((day) => renderDayCell(day))}
            </div>
          ) : (
            <div className="grid grid-cols-7">
              {weekDays.map((day) => renderDayCell(day, { week: true }))}
            </div>
          )}
        </div>

        <div className="border-t border-border pt-3">
          <p className="text-sm font-medium mb-2">
            {format(selected, "EEEE, d 'de' MMMM", { locale: pt })}
          </p>
          {selectedEvents.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              message="Sem agendamentos neste dia"
              className="py-6"
              action={onCreate ? (
                <Button variant="outline" size="sm" onClick={() => onCreate(selected)}>
                  <Plus className="h-4 w-4 mr-1" />
                  Criar evento
                </Button>
              ) : undefined}
            />
          ) : (
            <ul className="space-y-2">
              {selectedEvents.map((event) => {
                const chip = calendarEventChipStyle(event);
                return (
                  <li key={event.id || `${event.title}-${event.due_date}`}>
                    <button
                      type="button"
                      disabled={!onEventClick}
                      onClick={() => onEventClick?.(event)}
                      className={cn(
                        "w-full text-left rounded-md p-3 border",
                        onEventClick && "hover:bg-muted/50 transition-colors",
                        chip.className
                      )}
                      style={chip.style}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium">
                          {formatCalendarEventTitle(event, { viewerId, isTeamView })}
                        </p>
                        <Badge variant={isAbsenceEvent(event) ? "secondary" : event.type === "event" ? "secondary" : "outline"}>
                          {eventKindLabel(event.type)}
                        </Badge>
                      </div>
                      {formatEventClockRange(event) && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {formatEventClockRange(event)}
                        </p>
                      )}
                      {(event.client_name || event.description) && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">
                          {isAbsenceEvent(event)
                            ? (event.responsible_name || event.description || "Ausência / Férias")
                            : (event.client_name || event.description)}
                        </p>
                      )}
                    </button>
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
