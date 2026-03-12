/**
 * TasksPanel - Painel de Tarefas
 * Componente para gerir tarefas (criar, listar, concluir)
 */
import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Badge } from "./ui/badge";
import { Checkbox } from "./ui/checkbox";
import { Label } from "./ui/label";
import { ScrollArea } from "./ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { 
  ClipboardList, Plus, Check, RotateCcw, Trash2, Loader2, 
  MoreVertical, User, Clock, CheckCircle2, Circle, Calendar, AlertTriangle
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";
import { getTasks, getMyTasks, getProcessTasks, createTask, completeTask, reopenTask, deleteTask, getUsers } from "../services/api";

const TasksPanel = ({ 
  processId = null, 
  processName = null,
  showCreateButton = true,
  compact = false,
  maxHeight = "400px",
  showOnlyMyTasks = false  // Novo: mostrar apenas tarefas atribuídas ao utilizador atual
}) => {
  const [tasks, setTasks] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCompleted, setShowCompleted] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  
  // Form state
  const [newTask, setNewTask] = useState({
    title: "",
    description: "",
    assigned_to: [],
    due_date: ""  // Data de vencimento (opcional)
  });

  useEffect(() => {
    fetchData();
  }, [processId, showCompleted, showOnlyMyTasks]);

  const fetchData = async () => {
    try {
      setLoading(true);
      
      let tasksRes;
      if (processId) {
        tasksRes = await getProcessTasks(processId);
      } else if (showOnlyMyTasks) {
        // Buscar apenas tarefas atribuídas ao utilizador actual
        tasksRes = await getMyTasks();
      } else {
        tasksRes = await getTasks({ include_completed: showCompleted });
      }
      
      const usersRes = await getUsers();
      
      // Filtrar tarefas concluídas se necessário
      let filteredTasks = tasksRes.data;
      if (!showCompleted) {
        filteredTasks = filteredTasks.filter(t => !t.completed);
      }
      
      setTasks(filteredTasks);
      setUsers(usersRes.data.filter(u => u.role !== "cliente"));
    } catch (error) {
      console.error("Erro ao carregar tarefas:", error);
      toast.error("Erro ao carregar tarefas");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTask = async () => {
    if (!newTask.title.trim()) {
      toast.error("O título é obrigatório");
      return;
    }
    if (newTask.assigned_to.length === 0) {
      toast.error("Selecione pelo menos um utilizador");
      return;
    }

    try {
      setCreating(true);
      
      // Preparar dados da tarefa
      const taskData = {
        title: newTask.title,
        description: newTask.description,
        assigned_to: newTask.assigned_to,
        process_id: processId
      };
      
      // Adicionar due_date apenas se preenchido
      if (newTask.due_date) {
        taskData.due_date = new Date(newTask.due_date).toISOString();
      }
      
      await createTask(taskData);
      toast.success("Tarefa criada com sucesso");
      setIsCreateDialogOpen(false);
      setNewTask({ title: "", description: "", assigned_to: [], due_date: "" });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar tarefa");
    } finally {
      setCreating(false);
    }
  };

  const handleCompleteTask = async (taskId) => {
    try {
      await completeTask(taskId);
      toast.success("Tarefa concluída");
      fetchData();
    } catch (error) {
      toast.error("Erro ao concluir tarefa");
    }
  };

  const handleReopenTask = async (taskId) => {
    try {
      await reopenTask(taskId);
      toast.success("Tarefa reaberta");
      fetchData();
    } catch (error) {
      toast.error("Erro ao reabrir tarefa");
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar esta tarefa?")) return;
    try {
      await deleteTask(taskId);
      toast.success("Tarefa eliminada");
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao eliminar tarefa");
    }
  };

  const openCreateDialog = () => {
    // Se tiver processName, pré-preencher o título
    if (processName && processId) {
      setNewTask({
        title: `[${processName}] `,
        description: "",
        assigned_to: []
      });
    } else {
      setNewTask({ title: "", description: "", assigned_to: [], due_date: "" });
    }
    setIsCreateDialogOpen(true);
  };

  const toggleUserSelection = (userId) => {
    setNewTask(prev => ({
      ...prev,
      assigned_to: prev.assigned_to.includes(userId)
        ? prev.assigned_to.filter(id => id !== userId)
        : [...prev.assigned_to, userId]
    }));
  };

  const selectAllUsers = () => {
    setNewTask(prev => ({
      ...prev,
      assigned_to: users.map(u => u.id)
    }));
  };

  const clearAllUsers = () => {
    setNewTask(prev => ({
      ...prev,
      assigned_to: []
    }));
  };

  // Helper para mostrar badge de prazo
  const getDueDateBadge = (task) => {
    if (!task.due_date || task.completed) return null;
    
    const daysUntil = task.days_until_due;
    const isOverdue = task.is_overdue;
    
    if (isOverdue) {
      return (
        <Badge variant="destructive" className="text-xs">
          <AlertTriangle className="h-3 w-3 mr-1" />
          Atrasada ({Math.abs(daysUntil)}d)
        </Badge>
      );
    } else if (daysUntil === 0) {
      return (
        <Badge variant="destructive" className="text-xs">
          <Clock className="h-3 w-3 mr-1" />
          Vence hoje
        </Badge>
      );
    } else if (daysUntil === 1) {
      return (
        <Badge variant="warning" className="text-xs bg-orange-100 text-orange-800">
          <Clock className="h-3 w-3 mr-1" />
          Vence amanhã
        </Badge>
      );
    } else if (daysUntil <= 3) {
      return (
        <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">
          <Clock className="h-3 w-3 mr-1" />
          {daysUntil} dias
        </Badge>
      );
    } else {
      return (
        <Badge variant="outline" className="text-xs text-muted-foreground">
          <Calendar className="h-3 w-3 mr-1" />
          {format(parseISO(task.due_date), "dd/MM", { locale: pt })}
        </Badge>
      );
    }
  };

  if (loading) {
    return (
      <Card className="border-border">
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="border-border">
        <CardHeader className={compact ? "pb-2" : ""}>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className={`flex items-center gap-2 ${compact ? "text-base" : "text-lg"}`}>
                <ClipboardList className="h-5 w-5" />
                Tarefas
                {tasks.length > 0 && (
                  <Badge variant="secondary" className="ml-2">{tasks.length}</Badge>
                )}
              </CardTitle>
              {!compact && (
                <CardDescription>
                  {processId ? "Tarefas deste processo" : "Todas as tarefas"}
                </CardDescription>
              )}
            </div>
            {showCreateButton && (
              <Button 
                size="sm" 
                onClick={openCreateDialog}
                className="bg-teal-600 hover:bg-teal-700"
              >
                <Plus className="h-4 w-4 mr-1" />
                Nova
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Filtro de concluídas */}
          <div className="flex items-center gap-2 mb-4">
            <Checkbox
              id="showCompleted"
              checked={showCompleted}
              onCheckedChange={setShowCompleted}
            />
            <Label htmlFor="showCompleted" className="text-sm text-muted-foreground cursor-pointer">
              Mostrar concluídas
            </Label>
          </div>

          {/* Lista de tarefas */}
          {tasks.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <ClipboardList className="h-12 w-12 mx-auto mb-2 opacity-20" />
              <p>Nenhuma tarefa {showCompleted ? "" : "pendente"}</p>
            </div>
          ) : (
            <ScrollArea style={{ maxHeight }}>
              <div className="space-y-2">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                      task.completed 
                        ? "bg-muted/30 border-muted" 
                        : "bg-background border-border hover:bg-muted/50"
                    }`}
                  >
                    {/* Checkbox/Status */}
                    <button
                      onClick={() => task.completed ? handleReopenTask(task.id) : handleCompleteTask(task.id)}
                      className="mt-0.5 flex-shrink-0"
                    >
                      {task.completed ? (
                        <CheckCircle2 className="h-5 w-5 text-green-600" />
                      ) : (
                        <Circle className="h-5 w-5 text-muted-foreground hover:text-blue-600" />
                      )}
                    </button>

                    {/* Conteúdo */}
                    <div className="flex-1 min-w-0">
                      <p className={`font-medium ${task.completed ? "line-through text-muted-foreground" : ""}`}>
                        {task.title}
                      </p>
                      {task.description && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {task.description}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-2 mt-2">
                        {/* Badge de prazo */}
                        {getDueDateBadge(task)}
                        {/* Atribuídos */}
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <User className="h-3 w-3" />
                          {task.assigned_to_names?.join(", ") || "Sem atribuição"}
                        </div>
                        {/* Processo */}
                        {task.process_name && !processId && (
                          <Badge variant="outline" className="text-xs">
                            {task.process_name}
                          </Badge>
                        )}
                        {/* Data de criação */}
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          {format(parseISO(task.created_at), "dd/MM/yyyy", { locale: pt })}
                        </div>
                      </div>
                    </div>

                    {/* Menu */}
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {task.completed ? (
                          <DropdownMenuItem onClick={() => handleReopenTask(task.id)}>
                            <RotateCcw className="h-4 w-4 mr-2" />
                            Reabrir
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => handleCompleteTask(task.id)}>
                            <Check className="h-4 w-4 mr-2" />
                            Concluir
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem 
                          onClick={() => handleDeleteTask(task.id)}
                          className="text-red-600"
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Eliminar
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Dialog para criar tarefa */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Nova Tarefa</DialogTitle>
            <DialogDescription>
              Crie uma tarefa e atribua a um ou mais utilizadores.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="title">Título *</Label>
              <Input
                id="title"
                placeholder="Título da tarefa"
                value={newTask.title}
                onChange={(e) => setNewTask(prev => ({ ...prev, title: e.target.value }))}
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="description">Descrição</Label>
              <Textarea
                id="description"
                placeholder="Descrição opcional..."
                value={newTask.description}
                onChange={(e) => setNewTask(prev => ({ ...prev, description: e.target.value }))}
                rows={3}
              />
            </div>
            
            <div className="space-y-2">
              <Label>Atribuir a *</Label>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-muted-foreground">
                  Selecione um ou mais utilizadores
                </p>
                <div className="flex gap-2">
                  <Button 
                    type="button" 
                    variant="outline" 
                    size="sm"
                    onClick={selectAllUsers}
                    className="text-xs h-7"
                  >
                    Todos
                  </Button>
                  <Button 
                    type="button" 
                    variant="outline" 
                    size="sm"
                    onClick={clearAllUsers}
                    className="text-xs h-7"
                  >
                    Nenhum
                  </Button>
                </div>
              </div>
              <ScrollArea className="h-[200px] border rounded-md p-2">
                <div className="space-y-2">
                  {users.map((user) => (
                    <div
                      key={user.id}
                      className={`flex items-center gap-3 p-2 rounded cursor-pointer transition-colors ${
                        newTask.assigned_to.includes(user.id)
                          ? "bg-blue-50 border border-blue-200"
                          : "hover:bg-muted"
                      }`}
                      onClick={() => toggleUserSelection(user.id)}
                    >
                      <Checkbox
                        checked={newTask.assigned_to.includes(user.id)}
                        onChange={() => {}}
                      />
                      <div>
                        <p className="font-medium text-sm">{user.name}</p>
                        <p className="text-xs text-muted-foreground">{user.role}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
              {newTask.assigned_to.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {newTask.assigned_to.length} utilizador(es) selecionado(s)
                </p>
              )}
            </div>

            {/* Data de vencimento (opcional) */}
            <div className="space-y-2">
              <Label htmlFor="due_date">Data de Vencimento (opcional)</Label>
              <Input
                id="due_date"
                type="date"
                value={newTask.due_date}
                onChange={(e) => setNewTask(prev => ({ ...prev, due_date: e.target.value }))}
                min={new Date().toISOString().split('T')[0]}
              />
              <p className="text-xs text-muted-foreground">
                Se definida, será enviado um alerta quando o prazo se aproximar.
              </p>
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleCreateTask} 
              disabled={creating}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
              Criar Tarefa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default TasksPanel;
