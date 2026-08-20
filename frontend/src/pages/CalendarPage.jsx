/**
 * PACOTE DQ — Página dedicada de Calendário / Agenda.
 * Vista mensal e semanal de grande dimensão. Consultores vêem só os seus
 * eventos; diretor/CEO/admin vêem a equipa da empresa activa.
 *
 * @route /calendario
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import DashboardLayout from "../layouts/DashboardLayout";
import { PageHeader } from "../components/shared/PageHeader";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { EmptyState } from "../components/ui/EmptyState";
import { CalendarDays, Plus } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import {
  createDeadline,
  deleteDeadline,
  getCalendarDeadlines,
  getProcesses,
  getUsers,
} from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { excludeRoles } from "../utils/roleUtils";
import { safeDateStr, formatDate } from "../lib/utils";
import {
  agendaDateKey,
  calendarEventChipStyle,
  formatCalendarEventTitle,
  isAbsenceEvent,
  isTeamCalendarRole,
} from "../utils/agendaCalendar";
import GlobalCalendar from "../components/calendar/GlobalCalendar";
import CreateEventDialog from "../components/admin/CreateEventDialog";

export default function CalendarPage() {
  const navigate = useNavigate();
  const { user, effectiveRole } = useAuth();
  const isTeamView = isTeamCalendarRole(effectiveRole);

  const [events, setEvents] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [staffUsers, setStaffUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(new Date());

  const load = useCallback(async () => {
    try {
      const [calRes, procRes, usersRes] = await Promise.all([
        getCalendarDeadlines(),
        getProcesses({ size: 100 }).catch(() => ({ data: [] })),
        getUsers().catch(() => ({ data: [] })),
      ]);
      setEvents(Array.isArray(calRes.data) ? calRes.data : []);
      const procs = procRes?.data;
      setProcesses(Array.isArray(procs) ? procs : (procs?.items || procs?.processes || []));
      const users = Array.isArray(usersRes?.data) ? usersRes.data : [];
      setStaffUsers(excludeRoles(users, ["cliente", "parceiro"]));
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao carregar o calendário"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upcoming = useMemo(() => {
    const today = agendaDateKey(new Date());
    return [...events]
      .filter((e) => {
        const key = agendaDateKey(e.end_date || e.due_date);
        return key >= today;
      })
      .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)))
      .slice(0, 12);
  }, [events]);

  const handleCreate = async (eventData) => {
    await createDeadline(eventData);
    toast.success("Evento criado");
    await load();
  };

  const openCreate = (date) => {
    setSelectedDate(date || new Date());
    setDialogOpen(true);
  };

  const handleEventClick = (event) => {
    if (event?.process_id) {
      navigate(`/processo/${event.process_id}`);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Eliminar este evento?")) return;
    try {
      await deleteDeadline(id);
      toast.success("Evento eliminado");
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Não foi possível eliminar"));
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

        {loading ? (
          <div className="h-[420px] rounded-lg border border-border bg-muted/30 animate-pulse" />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 min-w-0">
              <GlobalCalendar
                events={events}
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
                                    {event.end_date && event.end_date !== event.due_date
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
          onOpenChange={setDialogOpen}
          onSubmit={handleCreate}
          processes={processes}
          staffUsers={staffUsers}
          currentUserId={user?.id}
          initialDate={selectedDate}
        />
      </div>
    </DashboardLayout>
  );
}
