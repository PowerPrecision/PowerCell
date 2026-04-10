/**
 * CreateEventDialog - Dialog para criar eventos/prazos
 */
import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Checkbox } from "../ui/checkbox";
import { Badge } from "../ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Loader2 } from "lucide-react";

const roleLabels = { 
  admin: "Administrador", 
  ceo: "CEO", 
  consultor: "Consultor", 
  mediador: "Intermediário", 
  intermediario: "Intermediário", 
  diretor: "Diretor(a)", 
  administrativo: "Administrativo(a)"
};

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
  const [formData, setFormData] = useState({
    title: "",
    description: "",
    due_date: initialDate ? initialDate.toISOString().split('T')[0] : new Date().toISOString().split('T')[0],
    priority: "medium",
    process_id: "",
    assigned_user_ids: currentUserId ? [currentUserId] : []
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await onSubmit({
        ...formData,
        process_id: formData.process_id || null,
        assigned_user_ids: formData.assigned_user_ids.length > 0 ? formData.assigned_user_ids : [currentUserId]
      });
      onOpenChange(false);
      setFormData({
        title: "",
        description: "",
        due_date: new Date().toISOString().split('T')[0],
        priority: "medium",
        process_id: "",
        assigned_user_ids: currentUserId ? [currentUserId] : []
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleUserAssignment = (userId) => {
    setFormData(prev => {
      const current = prev.assigned_user_ids || [];
      if (current.includes(userId)) {
        return { ...prev, assigned_user_ids: current.filter(id => id !== userId) };
      } else {
        return { ...prev, assigned_user_ids: [...current, userId] };
      }
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby="create-event-description">
        <DialogHeader>
          <DialogTitle>Criar Novo Evento</DialogTitle>
          <DialogDescription id="create-event-description">
            Adicione um evento ou prazo ao calendário.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="event-title">Título *</Label>
            <Input
              id="event-title"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="Ex: Reunião com cliente"
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
              <Label htmlFor="event-date">Data *</Label>
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
                <SelectTrigger>
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
          <div className="space-y-2">
            <Label htmlFor="event-process">Processo (opcional)</Label>
            <Select
              value={formData.process_id || "none"}
              onValueChange={(value) => setFormData({ ...formData, process_id: value === "none" ? "" : value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selecionar processo..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Nenhum (Evento Geral)</SelectItem>
                {(processes || []).slice(0, 50).map((process) => (
                  <SelectItem key={process.id} value={process.id}>
                    {process.client_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Atribuir a</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  const allUserIds = (staffUsers || []).map(u => u.id);
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
                    className={`text-sm cursor-pointer flex items-center gap-2 ${staffUser.id === currentUserId ? 'font-medium' : ''}`}
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
            <Button type="submit" disabled={loading} className="bg-teal-600 hover:bg-teal-700">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Evento"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateEventDialog;
