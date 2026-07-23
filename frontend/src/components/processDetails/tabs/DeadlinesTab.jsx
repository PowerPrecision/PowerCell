/**
 * DeadlinesTab — extraído de ProcessDetails.js (side-tab "Prazos").
 * Calendário + lista de prazos do processo, com diálogo de criação.
 */
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Label } from "../../ui/label";
import { Textarea } from "../../ui/textarea";
import { Calendar } from "../../ui/calendar";
import { ScrollArea } from "../../ui/scroll-area";
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
import { Plus, Calendar as CalendarIcon, Check, Trash2 } from "lucide-react";
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
        <h3 className="font-medium">Prazos</h3>
        {canManageDeadlines && (
          <Dialog open={isDeadlineDialogOpen} onOpenChange={setIsDeadlineDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" data-testid="add-deadline-btn">
                <Plus className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent aria-describedby="deadline-dialog-description" className="sm:max-w-md w-[calc(100vw-2rem)]">
              <DialogHeader>
                <DialogTitle>Novo Prazo</DialogTitle>
                <DialogDescription id="deadline-dialog-description">
                  Crie um novo prazo para este processo.
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
              </div>
              <DialogFooter>
                <Button onClick={handleCreateDeadline}>Criar Prazo</Button>
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
          <p className="text-center text-muted-foreground text-sm py-4">Sem prazos</p>
        ) : (
          <div className="space-y-2">
            {deadlines.map((deadline) => (
              <div
                key={deadline.id}
                className={`flex items-center justify-between p-2 rounded-md ${deadline.completed ? "bg-muted/30" : "bg-muted/50"}`}
              >
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggleDeadline(deadline)}
                    className={`h-4 w-4 rounded border flex items-center justify-center ${
                      deadline.completed ? "bg-emerald-500 border-emerald-500 text-white" : "border-slate-300"
                    }`}
                    disabled={!canManageDeadlines}
                  >
                    {deadline.completed && <Check className="h-3 w-3" />}
                  </button>
                  <div>
                    <p className={`text-sm ${deadline.completed ? "line-through text-muted-foreground" : ""}`}>
                      {safeString(deadline.title)}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {safeFormat(deadline.due_date, "dd/MM/yyyy")}
                    </p>
                  </div>
                </div>
                {canManageDeadlines && (
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDeleteDeadline(deadline.id)}>
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
