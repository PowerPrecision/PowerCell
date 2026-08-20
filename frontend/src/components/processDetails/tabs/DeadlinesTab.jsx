/**
 * DeadlinesTab — extraído de ProcessDetails.js (side-tab "Prazos").
 * Calendário + lista de prazos do processo, com diálogo de criação.
 *
 * PACOTE DH — evolução para "Agenda": cada item passa a ter:
 *   - type: "deadline" (Prazo Limite) | "event" (Marcação)
 *   - reminder_time: antecedência do lembrete ("1h", "1d", "3d", "7d" ou null)
 *   - visible_to_client: se o cliente vê este item no Portal do Cliente
 * O tab label passou de "Prazos" para "Agenda" no ProcessDetails.js.
 */
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Label } from "../../ui/label";
import { Textarea } from "../../ui/textarea";
import { Calendar } from "../../ui/calendar";
import { ScrollArea } from "../../ui/scroll-area";
import { Switch } from "../../ui/switch";
import { Badge } from "../../ui/badge";
// PACOTE DH — EmptyState canónico substitui o <p>Sem prazos</p> ad-hoc
import { EmptyState } from "../../ui/EmptyState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../../ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "../../ui/popover";
// PACOTE DH — ícones Bell (lembrete) e Eye (visível no portal);
// CalendarClock para o EmptyState canónico.
import { Plus, Calendar as CalendarIcon, Check, Trash2, Bell, Eye, CalendarClock } from "lucide-react";
import { format, isValid } from "date-fns";
import { pt } from "date-fns/locale";
import { safeString } from "../../../utils/safeString";
import { safeFormat } from "../../../lib/utils";

export default function DeadlinesTab({
  canManageDeadlines,
  isDeadlineDialogOpen,
  setIsDeadlineDialogOpen,
  deadlineForm,
  setDeadlineForm,
  selectedDate,
  setSelectedDate,
  handleCreateDeadline,
  deadlineDates,
  deadlines,
  handleToggleDeadline,
  handleDeleteDeadline,
}) {
  return (
    <>
      <div className="flex items-center justify-between mb-4">
        {/* PACOTE DH — título evolui de "Prazos" para "Agenda" */}
        <h3 className="font-medium">Agenda</h3>
        {canManageDeadlines && (
          <Dialog open={isDeadlineDialogOpen} onOpenChange={setIsDeadlineDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" data-testid="add-deadline-btn">
                <Plus className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent aria-describedby="deadline-dialog-description" className="sm:max-w-md w-[calc(100vw-2rem)]">
              <DialogHeader>
                <DialogTitle>Novo Prazo / Evento</DialogTitle>
                <DialogDescription id="deadline-dialog-description">
                  Crie um novo prazo ou marcação para este processo.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Título</Label>
                  <Input
                    value={deadlineForm.title}
                    onChange={(e) => setDeadlineForm({ ...deadlineForm, title: e.target.value })}
                    placeholder="Ex: Entregar documentos"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Descrição</Label>
                  <Textarea
                    value={deadlineForm.description}
                    onChange={(e) => setDeadlineForm({ ...deadlineForm, description: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Data Limite</Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className="w-full justify-start text-left font-normal">
                        <CalendarIcon className="mr-2 h-4 w-4" />
                        {selectedDate && isValid(selectedDate) ? format(selectedDate, "PPP", { locale: pt }) : "Selecione"}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0">
                      <Calendar mode="single" selected={selectedDate} onSelect={setSelectedDate} locale={pt} />
                    </PopoverContent>
                  </Popover>
                </div>
                <div className="space-y-2">
                  <Label>Prioridade</Label>
                  <Select
                    value={deadlineForm.priority}
                    onValueChange={(value) => setDeadlineForm({ ...deadlineForm, priority: value })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Baixa</SelectItem>
                      <SelectItem value="medium">Média</SelectItem>
                      <SelectItem value="high">Alta</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* PACOTE DH — Tipo: Prazo (deadline) ou Marcação (event) */}
                <div className="space-y-2">
                  <Label>Tipo</Label>
                  <Select
                    value={deadlineForm.type || "deadline"}
                    onValueChange={(value) => setDeadlineForm({ ...deadlineForm, type: value })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="deadline">Prazo Limite</SelectItem>
                      <SelectItem value="event">Marcação</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* PACOTE DH — Lembrete: antecedência do alerta */}
                <div className="space-y-2">
                  <Label>Lembrete</Label>
                  <Select
                    value={deadlineForm.reminder_time || "none"}
                    onValueChange={(value) => setDeadlineForm({
                      ...deadlineForm,
                      reminder_time: value === "none" ? null : value,
                    })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Sem lembrete</SelectItem>
                      <SelectItem value="1h">1 hora antes</SelectItem>
                      <SelectItem value="1d">1 dia antes</SelectItem>
                      <SelectItem value="3d">3 dias antes</SelectItem>
                      <SelectItem value="7d">7 dias antes</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* PACOTE DH — Visível no Portal do Cliente */}
                <div className="flex items-start gap-3 p-3 rounded-md border border-border bg-muted/30">
                  <Switch
                    id="visible-to-client"
                    checked={!!deadlineForm.visible_to_client}
                    onCheckedChange={(checked) => setDeadlineForm({ ...deadlineForm, visible_to_client: checked })}
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor="visible-to-client" className="text-sm cursor-pointer">
                      Visível no Portal do Cliente
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      O cliente verá este evento na sua agenda do Portal.
                    </p>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button onClick={handleCreateDeadline}>Criar</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Calendar
        mode="single"
        selected={selectedDate}
        locale={pt}
        modifiers={{ deadline: deadlineDates }}
        modifiersStyles={{
          deadline: { backgroundColor: "hsl(var(--primary))", color: "white", borderRadius: "4px" },
        }}
        className="rounded-md border mb-4"
      />

      <ScrollArea className="h-[200px]">
        {deadlines.length === 0 ? (
          /* PACOTE DH — EmptyState canónico substitui o <p>Sem prazos</p> */
          <EmptyState
            icon={CalendarClock}
            title="Sem eventos"
            message="Ainda não há prazos ou marcações para este processo."
          />
        ) : (
          <div className="space-y-2">
            {deadlines.map((deadline) => (
              <div
                key={deadline.id}
                className={`flex items-center justify-between p-2 rounded-md ${deadline.completed ? "bg-muted/30" : "bg-muted/50"}`}
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <button
                    onClick={() => handleToggleDeadline(deadline)}
                    className={`h-4 w-4 rounded border flex items-center justify-center shrink-0 ${
                      deadline.completed ? "bg-emerald-500 border-emerald-500 text-white" : "border-slate-300"
                    }`}
                    disabled={!canManageDeadlines}
                  >
                    {deadline.completed && <Check className="h-3 w-3" />}
                  </button>
                  {/* PACOTE DH — Badge a distinguir tipo: Evento vs Prazo */}
                  <Badge
                    variant={deadline.type === "event" || deadline.type === "absence" ? "secondary" : "outline"}
                    className="shrink-0 text-[10px] px-1.5 py-0"
                  >
                    {deadline.type === "event" ? "Evento" : deadline.type === "absence" ? "Ausência" : "Prazo"}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm truncate ${deadline.completed ? "line-through text-muted-foreground" : ""}`}>
                      {safeString(deadline.title)}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {safeFormat(deadline.due_date, "dd/MM/yyyy")}
                    </p>
                  </div>
                  {/* PACOTE DH — ícones indicadores (lembrete / visível no portal) */}
                  <div className="flex items-center gap-1 shrink-0">
                    {deadline.reminder_time && (
                      <Bell
                        className="h-3.5 w-3.5 text-muted-foreground"
                        aria-label={`Lembrete: ${deadline.reminder_time}`}
                        title={`Lembrete: ${deadline.reminder_time}`}
                      />
                    )}
                    {deadline.visible_to_client && (
                      <Eye
                        className="h-3.5 w-3.5 text-muted-foreground"
                        aria-label="Visível no Portal do Cliente"
                        title="Visível no Portal do Cliente"
                      />
                    )}
                  </div>
                </div>
                {canManageDeadlines && (
                  <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleDeleteDeadline(deadline.id)}>
                    <Trash2 className="h-3 w-3 text-destructive" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </>
  );
}
