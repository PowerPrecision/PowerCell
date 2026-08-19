/**
 * CreateEventDialog - Dialog para criar eventos/prazos/ausências (Pacote DQ)
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
import { Loader2 } from "lucide-react";
import { safeString } from "../../utils/safeString";
import { agendaDateKey } from "../../utils/agendaCalendar";

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
    priority: "medium",
    process_id: "",
    assigned_user_ids: currentUserId ? [currentUserId] : [],
    type: "event",
    all_day: false,
    visible_to_client: false,
  };
}

const CreateEventDialog = ({
  open,
  onOpenChange,
  onSubmit,
  processes,
  staffUsers,
  currentUserId,
  initialDate
}) => {
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState(() => emptyForm(currentUserId, initialDate));

  useEffect(() => {
    if (!open) return;
    setFormData(emptyForm(currentUserId, initialDate));
  }, [open, initialDate, currentUserId]);

  const isAbsence = formData.type === "absence";

  const handleTypeChange = (value) => {
    setFormData((prev) => ({
      ...prev,
      type: value,
      process_id: value === "absence" ? "" : prev.process_id,
      visible_to_client: value === "absence" ? false : prev.visible_to_client,
      all_day: value === "absence" ? true : prev.all_day,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...formData,
        process_id: isAbsence ? null : (formData.process_id || null),
        assigned_user_ids: formData.assigned_user_ids.length > 0
          ? formData.assigned_user_ids
          : [currentUserId],
        visible_to_client: isAbsence ? false : !!formData.visible_to_client,
        all_day: isAbsence ? true : !!formData.all_day,
        end_date: (isAbsence || formData.all_day)
          ? (formData.end_date || formData.due_date)
          : null,
      };
      await onSubmit(payload);
      onOpenChange(false);
    } finally {
      setLoading(false);
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby="create-event-description">
        <DialogHeader>
          <DialogTitle>Criar Novo Evento</DialogTitle>
          <DialogDescription id="create-event-description">
            Adicione um prazo, marcação ou ausência ao calendário.
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
              <Label htmlFor="event-date">{isAbsence ? "Início *" : "Data *"}</Label>
              <Input
                id="event-date"
                type="date"
                value={formData.due_date}
                onChange={(e) => setFormData({ ...formData, due_date: e.target.value })}
                required
              />
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
          </div>

          <div className="flex items-start gap-3 p-3 rounded-md border border-border bg-muted/30">
            <Switch
              id="event-all-day"
              checked={isAbsence || formData.all_day}
              disabled={isAbsence}
              onCheckedChange={(checked) => setFormData({ ...formData, all_day: checked })}
            />
            <div className="space-y-0.5">
              <Label htmlFor="event-all-day" className="text-sm cursor-pointer">
                Dia inteiro
              </Label>
              <p className="text-xs text-muted-foreground">
                {isAbsence
                  ? "As ausências ocupam o dia completo e podem cruzar vários dias."
                  : "O bloco ocupa o dia completo no calendário."}
              </p>
            </div>
          </div>

          {(isAbsence || formData.all_day) && (
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
          )}

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
              {(staffUsers || []).map((staffUser) => (
                <div key={staffUser.id} className="flex items-center space-x-2">
                  <Checkbox
                    id={`user-${staffUser.id}`}
                    checked={formData.assigned_user_ids?.includes(staffUser.id) || staffUser.id === currentUserId}
                    disabled={staffUser.id === currentUserId}
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
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Evento"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateEventDialog;
