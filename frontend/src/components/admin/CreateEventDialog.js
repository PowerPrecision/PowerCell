/**
 * CreateEventDialog - Criar e editar eventos/prazos/ausências (Pacote FA)
 */
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Checkbox } from "../ui/checkbox";
import { Badge } from "../ui/badge";
import { Switch } from "../ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Loader2, Trash2 } from "lucide-react";
import { safeString } from "../../utils/safeString";
import {
  agendaDateKey,
  agendaTimeValue,
  buildEventPayload,
  DEFAULT_EVENT_END_TIME,
  DEFAULT_EVENT_START_TIME,
  isAbsenceEvent,
} from "../../utils/agendaCalendar";

const roleLabels = {
  admin: "Administrador",
  ceo: "CEO",
  consultor: "Consultor",
  intermediario: "Intermediário",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)"
};

function emptyForm(currentUserId, initialDate) {
  const due = agendaDateKey(initialDate || new Date());
  return {
    title: "",
    description: "",
    due_date: due,
    end_date: due,
    start_time: DEFAULT_EVENT_START_TIME,
    end_time: DEFAULT_EVENT_END_TIME,
    priority: "medium",
    process_id: "",
    assigned_user_ids: currentUserId ? [currentUserId] : [],
    type: "event",
    all_day: false,
    visible_to_client: false,
  };
}

function formFromEvent(event, currentUserId) {
  const due = agendaDateKey(event?.due_date) || agendaDateKey(new Date());
  const end = agendaDateKey(event?.end_date) || due;
  const startTime = agendaTimeValue(event?.due_date) || DEFAULT_EVENT_START_TIME;
  const endTime = agendaTimeValue(event?.end_date) || DEFAULT_EVENT_END_TIME;
  const assigned = Array.isArray(event?.assigned_user_ids) ? event.assigned_user_ids : [];
  return {
    title: event?.title || "",
    description: event?.description || "",
    due_date: due,
    end_date: end,
    start_time: startTime,
    end_time: endTime,
    priority: event?.priority || "medium",
    process_id: event?.process_id || "",
    assigned_user_ids: assigned.length > 0
      ? assigned
      : (currentUserId ? [currentUserId] : []),
    type: isAbsenceEvent(event) ? "absence" : (event?.type || "event"),
    all_day: event?.all_day === true || isAbsenceEvent(event),
    visible_to_client: !!event?.visible_to_client,
  };
}

const CreateEventDialog = ({
  open,
  onOpenChange,
  onSubmit,
  onDelete,
  processes,
  staffUsers,
  currentUserId,
  initialDate,
  event = null,
}) => {
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [timeError, setTimeError] = useState("");
  const [formData, setFormData] = useState(() => emptyForm(currentUserId, initialDate));

  const isEditing = Boolean(event?.id);

  useEffect(() => {
    if (!open) return;
    setTimeError("");
    setFormData(event?.id ? formFromEvent(event, currentUserId) : emptyForm(currentUserId, initialDate));
  }, [open, initialDate, currentUserId, event]);

  const isAbsence = formData.type === "absence";
  const showTimes = !isAbsence && !formData.all_day;

  const handleTypeChange = (value) => {
    setFormData((prev) => ({
      ...prev,
      type: value,
      process_id: value === "absence" ? "" : prev.process_id,
      visible_to_client: value === "absence" ? false : prev.visible_to_client,
      all_day: value === "absence" ? true : prev.all_day,
    }));
    setTimeError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setTimeError("");
    const isAbsenceType = formData.type === "absence";
    const payload = buildEventPayload(formData, {
      currentUserId,
      isAbsence: isAbsenceType,
    });
    if (!payload.all_day && payload.end_date && payload.due_date && payload.end_date <= payload.due_date) {
      setTimeError("A hora de fim deve ser posterior à hora de início.");
      return;
    }
    setLoading(true);
    try {
      await onSubmit(payload, event?.id || null);
      onOpenChange(false);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!event?.id || !onDelete) return;
    if (!window.confirm("Eliminar este evento?")) return;
    setDeleting(true);
    try {
      await onDelete(event.id);
      onOpenChange(false);
    } finally {
      setDeleting(false);
    }
  };

  const toggleUserAssignment = (userId) => {
    setFormData((prev) => {
      const current = prev.assigned_user_ids || [];
      if (current.includes(userId)) {
        return { ...prev, assigned_user_ids: current.filter((id) => id !== userId) };
      }
      return { ...prev, assigned_user_ids: [...current, userId] };
    });
  };

  const busy = loading || deleting;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="create-event-dialog" aria-describedby="create-event-description">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Editar Evento" : "Criar Novo Evento"}</DialogTitle>
          <DialogDescription id="create-event-description">
            {isEditing
              ? "Altere os dados da marcação, incluindo data e horário."
              : "Adicione um prazo, marcação ou ausência ao calendário."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="event-type">Tipo</Label>
            <Select value={formData.type} onValueChange={handleTypeChange}>
              <SelectTrigger id="event-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="deadline">Prazo limite</SelectItem>
                <SelectItem value="event">Marcação</SelectItem>
                <SelectItem value="absence">Ausência / Férias</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="event-title">Título *</Label>
            <Input
              id="event-title"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder={isAbsence ? "Ex: Férias — Flávio" : "Ex: Escritura Patrícia"}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="event-description">Descrição</Label>
            <Textarea
              id="event-description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Detalhes do evento..."
              rows={3}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="event-date">{isAbsence ? "Início *" : "Data de início *"}</Label>
              <Input
                id="event-date"
                type="date"
                value={formData.due_date}
                onChange={(e) => {
                  const next = e.target.value;
                  setFormData((prev) => ({
                    ...prev,
                    due_date: next,
                    end_date: !prev.end_date || prev.end_date < next ? next : prev.end_date,
                  }));
                }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="event-start-time">Hora de Início</Label>
              <Input
                id="event-start-time"
                type="time"
                step="60"
                value={formData.start_time}
                onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                required={showTimes}
                disabled={!showTimes}
                data-testid="event-start-time"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="event-end-date">Data de fim</Label>
              <Input
                id="event-end-date"
                type="date"
                min={formData.due_date}
                value={formData.end_date || formData.due_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="event-end-time">Hora de Fim</Label>
              <Input
                id="event-end-time"
                type="time"
                step="60"
                value={formData.end_time}
                onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
                required={showTimes}
                disabled={!showTimes}
                data-testid="event-end-time"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="event-priority">Prioridade</Label>
            <Select
              value={formData.priority}
              onValueChange={(value) => setFormData({ ...formData, priority: value })}
            >
              <SelectTrigger id="event-priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Baixa</SelectItem>
                <SelectItem value="medium">Média</SelectItem>
                <SelectItem value="high">Alta</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {timeError && (
            <p className="text-sm text-destructive" data-testid="event-time-error">{timeError}</p>
          )}

          <div className="flex items-start gap-3 p-3 rounded-md border border-border bg-muted/30">
            <Switch
              id="event-all-day"
              checked={isAbsence || formData.all_day}
              disabled={isAbsence}
              onCheckedChange={(checked) => {
                setFormData((prev) => ({
                  ...prev,
                  all_day: checked,
                  start_time: prev.start_time || DEFAULT_EVENT_START_TIME,
                  end_time: prev.end_time || DEFAULT_EVENT_END_TIME,
                }));
                setTimeError("");
              }}
            />
            <div className="space-y-0.5">
              <Label htmlFor="event-all-day" className="text-sm cursor-pointer">
                Dia inteiro
              </Label>
              <p className="text-xs text-muted-foreground">
                {isAbsence
                  ? "As ausências ocupam o dia completo e podem cruzar vários dias."
                  : "Desative para definir hora de início e de fim."}
              </p>
            </div>
          </div>

          {!isAbsence && (
            <div className="space-y-2">
              <Label htmlFor="event-process">Processo (opcional)</Label>
              <Select
                value={formData.process_id || "none"}
                onValueChange={(value) => setFormData({ ...formData, process_id: value === "none" ? "" : value })}
              >
                <SelectTrigger id="event-process">
                  <SelectValue placeholder="Selecionar processo..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Nenhum (Evento Geral)</SelectItem>
                  {(processes || []).slice(0, 50).map((process) => (
                    <SelectItem key={process.id} value={process.id}>
                      {safeString(process.client_name)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>{isAbsence ? "Colaborador" : "Atribuir a"}</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  const allUserIds = (staffUsers || []).map((u) => u.id);
                  setFormData({ ...formData, assigned_user_ids: allUserIds });
                }}
              >
                Selecionar Todos
              </Button>
            </div>
            <div className="border rounded-md p-3 max-h-40 overflow-y-auto space-y-2">
              {(staffUsers || []).map((staffUser) => {
                const forceSelf = !isEditing && staffUser.id === currentUserId;
                return (
                  <div key={staffUser.id} className="flex items-center space-x-2">
                    <Checkbox
                      id={`user-${staffUser.id}`}
                      checked={formData.assigned_user_ids?.includes(staffUser.id) || forceSelf}
                      disabled={forceSelf}
                      onCheckedChange={() => toggleUserAssignment(staffUser.id)}
                    />
                    <label
                      htmlFor={`user-${staffUser.id}`}
                      className={`text-sm cursor-pointer flex items-center gap-2 ${staffUser.id === currentUserId ? "font-medium" : ""}`}
                    >
                      {staffUser.name}
                      {staffUser.id === currentUserId && <Badge variant="outline" className="text-xs">Você</Badge>}
                      <span className="text-xs text-muted-foreground">({roleLabels[staffUser.role] || staffUser.role})</span>
                    </label>
                  </div>
                );
              })}
            </div>
          </div>
          <DialogFooter className={isEditing ? "sm:justify-between" : undefined}>
            {isEditing && onDelete && (
              <Button
                type="button"
                variant="ghost"
                className="gap-1.5 text-destructive hover:text-destructive"
                onClick={handleDelete}
                disabled={busy}
                data-testid="event-delete"
              >
                {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Eliminar
              </Button>
            )}
            <div className="flex flex-col-reverse sm:flex-row gap-2 sm:space-x-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancelar
              </Button>
              <Button type="submit" disabled={busy} className="gap-1.5" data-testid="event-submit">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : (isEditing ? "Guardar Alterações" : "Criar Evento")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateEventDialog;
