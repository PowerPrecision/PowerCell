/**
 * PACOTE DQ — Página dedicada de Calendário / Agenda.
 * Vista mensal e semanal de grande dimensão. Consultores vêem só os seus
 * eventos; diretor/CEO/admin vêem a equipa da empresa activa.
 *
 * @route /calendario
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageHeader } from "../components/shared/PageHeader";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { EmptyState } from "../components/ui/EmptyState";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Label } from "../components/ui/label";
import { CalendarDays, Plus } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import {
  createDeadline,
  deleteDeadline,
  getCalendarDeadlines,
  getProcesses,
  getStaffUsers,
  updateDeadline,
} from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { filterAssignmentStaff } from "../utils/roleUtils";
import { safeDateStr, formatDate } from "../lib/utils";
import {
  agendaDateKey,
  calendarEventChipStyle,
  filterCalendarEvents,
  formatCalendarEventTitle,
  formatEventClockRange,
  isAbsenceEvent,
  isTeamCalendarRole,
} from "../utils/agendaCalendar";
import GlobalCalendar from "../components/calendar/GlobalCalendar";
import CreateEventDialog from "../components/admin/CreateEventDialog";

export default function CalendarPage() {
  const { user, effectiveRole } = useAuth();
  const isTeamView = isTeamCalendarRole(effectiveRole);

  const [events, setEvents] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [staffUsers, setStaffUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [consultorFilter, setConsultorFilter] = useState("all");
  const [eventTypeFilter, setEventTypeFilter] = useState("all");
  const [editingEvent, setEditingEvent] = useState(null);

  const load = useCallback(async () => {
    try {
      const [calRes, procRes, usersRes] = await Promise.all([
        getCalendarDeadlines(),
        getProcesses({ size: 100 }).catch(() => ({ data: [] })),
        getStaffUsers().catch(() => ({ data: [] })),
      ]);
      setEvents(Array.isArray(calRes.data) ? calRes.data : []);
      const procs = procRes?.data;
      setProcesses(Array.isArray(procs) ? procs : (procs?.items || procs?.processes || []));
      const users = Array.isArray(usersRes?.data) ? usersRes.data : [];
      setStaffUsers(filterAssignmentStaff(users));
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao carregar o calendário"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filteredEvents = useMemo(
    () => filterCalendarEvents(events, {
      consultorId: consultorFilter,
      eventType: eventTypeFilter,
    }),
    [events, consultorFilter, eventTypeFilter],
  );

  const upcoming = useMemo(() => {
    const today = agendaDateKey(new Date());
    return [...filteredEvents]
      .filter((e) => {
        const key = agendaDateKey(e.end_date || e.due_date);
        return key >= today;
      })
      .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)))
      .slice(0, 12);
  }, [filteredEvents]);

  const handleSubmit = async (eventData, eventId) => {
    try {
      if (eventId) {
        await updateDeadline(eventId, eventData);
        toast.success("Alterações guardadas");
      } else {
        await createDeadline(eventData);
        toast.success("Evento criado");
      }
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Não foi possível guardar o evento"));
      throw error;
    }
  };

  const openCreate = (date) => {
    setEditingEvent(null);
    setSelectedDate(date || new Date());
    setDialogOpen(true);
  };

  const handleEventClick = (event) => {
    if (!event) return;
    setEditingEvent(event);
    setDialogOpen(true);
  };

  const handleDialogOpenChange = (open) => {
    setDialogOpen(open);
    if (!open) setEditingEvent(null);
  };

  const handleDelete = async (id, { confirm = true } = {}) => {
    if (confirm && !window.confirm("Eliminar este evento?")) return;
    try {
      await deleteDeadline(id);
      toast.success("Evento eliminado");
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Não foi possível eliminar"));
      throw error;
    }
  };

  return (
    <DashboardLayout title="Calendário">
      <div className="space-y-6" data-testid="calendar-page">
        <PageHeader
          icon={CalendarDays}
          title="Calendário"
          description={
            isTeamView
              ? "Vista da equipa da empresa activa — prazos, marcações e ausências"
              : "Os seus prazos, marcações e ausências"
          }
          actions={
            <Button onClick={() => openCreate(new Date())} className="gap-2">
              <Plus className="h-4 w-4" />
              Novo evento
            </Button>
          }
        />

        <div
          className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-muted/20 p-3"
          data-testid="calendar-filters"
        >
          <div className="space-y-1 min-w-[180px]">
            <Label htmlFor="calendar-filter-consultor" className="text-xs text-muted-foreground">
              Consultor
            </Label>
            <Select value={consultorFilter} onValueChange={setConsultorFilter}>
              <SelectTrigger id="calendar-filter-consultor" className="h-9">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {staffUsers.map((staff) => (
                  <SelectItem key={staff.id} value={staff.id}>
                    {staff.name || staff.email || staff.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 min-w-[180px]">
            <Label htmlFor="calendar-filter-type" className="text-xs text-muted-foreground">
              Tipo de Evento
            </Label>
            <Select value={eventTypeFilter} onValueChange={setEventTypeFilter}>
              <SelectTrigger id="calendar-filter-type" className="h-9">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="deadline">Prazo</SelectItem>
                <SelectItem value="event">Marcação</SelectItem>
                <SelectItem value="absence">Ausência</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {loading ? (
          <div className="h-[420px] rounded-lg border border-border bg-muted/30 animate-pulse" />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 min-w-0">
              <GlobalCalendar
                events={filteredEvents}
                isTeamView={isTeamView}
                viewerId={user?.id}
                onEventClick={handleEventClick}
                onCreate={openCreate}
              />
            </div>
            <Card className="border-border h-fit">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Próximas marcações</CardTitle>
                <CardDescription>
                  {upcoming.length} agendamento{upcoming.length === 1 ? "" : "s"} à frente
                </CardDescription>
              </CardHeader>
              <CardContent>
                {upcoming.length === 0 ? (
                  <EmptyState
                    icon={CalendarDays}
                    message="Sem marcações futuras"
                    className="py-8"
                  />
                ) : (
                  <ScrollArea className="h-[520px]">
                    <ul className="space-y-2 pr-3">
                      {upcoming.map((event) => {
                        const chip = calendarEventChipStyle(event);
                        return (
                          <li key={event.id}>
                            <div
                              className={`rounded-md border p-2.5 ${chip.className}`}
                              style={chip.style}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <button
                                  type="button"
                                  className="text-left min-w-0 flex-1"
                                  onClick={() => handleEventClick(event)}
                                >
                                  <p className="text-sm font-medium truncate">
                                    {formatCalendarEventTitle(event, {
                                      viewerId: user?.id,
                                      isTeamView,
                                    })}
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {formatDate(safeDateStr(event.due_date))}
                                    {formatEventClockRange(event) ? ` · ${formatEventClockRange(event)}` : ""}
                                    {event.end_date && agendaDateKey(event.end_date) !== agendaDateKey(event.due_date)
                                      ? ` – ${formatDate(safeDateStr(event.end_date))}`
                                      : ""}
                                  </p>
                                </button>
                                <div className="flex flex-col items-end gap-1">
                                  {isAbsenceEvent(event) && (
                                    <Badge variant="secondary" className="text-[10px]">Ausência</Badge>
                                  )}
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-xs text-destructive"
                                    onClick={() => handleDelete(event.id)}
                                  >
                                    Eliminar
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        <CreateEventDialog
          open={dialogOpen}
          onOpenChange={handleDialogOpenChange}
          onSubmit={handleSubmit}
          onDelete={(id) => handleDelete(id, { confirm: false })}
          processes={processes}
          staffUsers={staffUsers}
          currentUserId={user?.id}
          initialDate={selectedDate}
          event={editingEvent}
        />
      </div>
    </DashboardLayout>
  );
}
