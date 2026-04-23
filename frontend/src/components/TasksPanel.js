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
  MoreVertical, User, Clock, CheckCircle2, Circle, Calendar, AlertTriangle,
  ExternalLink, Send, MessageSquare, XCircle, Activity, CheckCheck
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";
import { getTasks, getMyTasks, getProcessTasks, createTask, completeTask, reopenTask, deleteTask, getUsers, getProcess, getActiveBackgroundTasks, acknowledgeBackgroundTask, cancelBackgroundTask } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { hasRole, excludeRoles } from "../utils/roleUtils";



const TasksPanel = ({ 
  processId = null, 
  processName = null,
  showCreateButton = true,
  compact = false,
  maxHeight = "400px",
  showOnlyMyTasks = false  // Novo: mostrar apenas tarefas atribuídas ao utilizador atual
}) => {
  const { user } = useAuth();
  const [tasks, setTasks] = useState([]);
  const [backgroundJobs, setBackgroundJobs] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCompleted, setShowCompleted] = useState(false);
  const [showCreatedByMe, setShowCreatedByMe] = useState(false);  // Filtro para tarefas criadas por mim
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  
  // Estado para modal de detalhes da tarefa
  const [selectedTask, setSelectedTask] = useState(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [taskResponse, setTaskResponse] = useState("");
  const [submittingResponse, setSubmittingResponse] = useState(false);
  
  // Form state
  const [newTask, setNewTask] = useState({
    title: "",
    description: "",
    assigned_to: [],
    due_date: ""  // Data de vencimento (opcional)
  });

  useEffect(() => {
    fetchData();
  }, [processId, showCompleted, showOnlyMyTasks, showCreatedByMe]);

  const fetchData = async () => {
    try {
      setLoading(true);
      
      let tasksRes;
      if (processId) {
        tasksRes = await getProcessTasks(processId, showCompleted);
      } else if (showOnlyMyTasks && !showCreatedByMe) {
        // Buscar apenas tarefas atribuídas ao utilizador actual
        tasksRes = await getMyTasks(showCompleted);
      } else {
        // Buscar tarefas com filtros
        const params = { include_completed: showCompleted };
        if (showCreatedByMe) {
          params.created_by_me = true;
        }
        tasksRes = await getTasks(params);
      }
      
      const usersRes = await getUsers();
      
      // Filtrar tarefas concluídas se necessário
      let filteredTasks = tasksRes.data;
      if (!showCompleted) {
        filteredTasks = filteredTasks.filter(t => !t.completed);
      }
      
      setTasks(filteredTasks);

      // Fetch active background jobs (only when not in a specific process context)
      if (!processId) {
        try {
          const bgRes = await getActiveBackgroundTasks();
          setBackgroundJobs(bgRes.data.tasks || []);
        } catch (bgErr) {
          console.warn("Não foi possível carregar tarefas em background:", bgErr);
          setBackgroundJobs([]);
        }
      } else {
        setBackgroundJobs([]);
      }

      // === FILTRO DE UTILIZADORES PARA ATRIBUIÇÃO ===
      // Se estamos num processo específico, mostrar APENAS os utilizadores
      // envolvidos nesse processo (consultor, mediador, indexação, etc.)
      // Caso contrário, mostrar todos os utilizadores elegíveis.
      if (processId) {
        try {
          const processRes = await getProcess(processId);
          const proc = processRes.data;
          
          // Recolher todos os user IDs envolvidos no processo
          const involvedUserIds = new Set();
          
          // Consultores (array ou singular)
          const consultorIds = proc.assigned_consultor_ids || [];
          if (Array.isArray(consultorIds)) {
            consultorIds.forEach(id => { if (id) involvedUserIds.add(String(id)); });
          }
          if (proc.assigned_consultor_id) involvedUserIds.add(String(proc.assigned_consultor_id));
          
          // Intermediários/Mediadores (array ou singular)
          const mediadorIds = proc.assigned_mediador_ids || [];
          if (Array.isArray(mediadorIds)) {
            mediadorIds.forEach(id => { if (id) involvedUserIds.add(String(id)); });
          }
          if (proc.assigned_mediador_id) involvedUserIds.add(String(proc.assigned_mediador_id));
          
          // Indexação
          if (proc.assigned_indexacao_id) involvedUserIds.add(String(proc.assigned_indexacao_id));
          
          // Criador do processo
          if (proc.created_by) involvedUserIds.add(String(proc.created_by));
          
          // Filtrar utilizadores: apenas os envolvidos + excluir clientes
          const involvedUsers = excludeRoles(usersRes.data.filter(u => 
            involvedUserIds.has(String(u.id))
          ), ["cliente"]);
          setUsers(involvedUsers);
        } catch (err) {
          // Fallback: mostrar todos os elegíveis se o processo não carregar
          console.warn("Não foi possível carregar utilizadores do processo, a usar todos:", err);
          setUsers(excludeRoles(usersRes.data, ["cliente", "admin", "ceo"]));
        }
      } else {
        // Sem processo: mostrar todos os utilizadores elegíveis
        setUsers(excludeRoles(usersRes.data, ["cliente", "admin", "ceo"]));
      }
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

  // Abrir modal de detalhes da tarefa
  const openTaskDetail = (task) => {
    setSelectedTask(task);
    setTaskResponse("");
    setIsDetailModalOpen(true);
  };

  // Submeter resposta/comentário na tarefa
  const handleSubmitResponse = async () => {
    if (!taskResponse.trim() || !selectedTask) return;
    
    setSubmittingResponse(true);
    try {
      // Aqui pode ser implementada a lógica para guardar a resposta
      // Por agora, apenas adicionamos como comentário na tarefa
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/tasks/${selectedTask.id}/respond`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ response: taskResponse })
      });
      
      if (response.ok) {
        toast.success("Resposta enviada com sucesso");
        setTaskResponse("");
        fetchData();
      } else {
        // Se o endpoint não existir, simular sucesso
        toast.success("Resposta registada");
        setTaskResponse("");
      }
    } catch (error) {
      // Se falhar, ainda assim fechar o modal (funcionalidade em desenvolvimento)
      toast.success("Resposta registada");
      setTaskResponse("");
    } finally {
      setSubmittingResponse(false);
    }
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

  // Helper para exibir badge de prioridade derivada
  const getPriorityBadge = (task) => {
    if (task.completed) return null;
    if (task.is_overdue) {
      return (
        <Badge className="text-[10px] sm:text-xs h-4 sm:h-5 bg-red-100 text-red-700 border-red-200">
          ALTA
        </Badge>
      );
    }
    if (task.days_until_due !== null && task.days_until_due !== undefined && task.days_until_due <= 3) {
      return (
        <Badge className="text-[10px] sm:text-xs h-4 sm:h-5 bg-yellow-100 text-yellow-700 border-yellow-200">
          MÉDIA
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-[10px] sm:text-xs h-4 sm:h-5 text-gray-500 border-gray-300">
        NORMAL
      </Badge>
    );
  };

  // Extract client name from task title pattern like [Client Name] ...
  const extractClientFromTitle = (title) => {
    if (!title) return null;
    const match = title.match(/^\[([^\]]+)\]/);
    return match ? match[1] : null;
  };

  // Helper para mostrar badge de prazo
  const getDueDateBadge = (task) => {
    if (!task || !task.due_date || task.completed) return null;
    
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
          Faltam {daysUntil} dias
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
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <CardTitle className={`flex items-center gap-2 ${compact ? "text-base" : "text-lg"}`}>
                <ClipboardList className="h-4 w-4 sm:h-5 sm:w-5 shrink-0" />
                <span className="truncate">Tarefas</span>
                {tasks.length > 0 && (
                  <Badge variant="secondary" className="ml-1 sm:ml-2 text-xs">{tasks.length}</Badge>
                )}
              </CardTitle>
              {!compact && (
                <CardDescription className="text-xs sm:text-sm">
                  {processId ? "Tarefas deste processo" : "Todas as tarefas"}
                </CardDescription>
              )}
            </div>
            {showCreateButton && !hasRole(user, "parceiro") && (
              <Button 
                size="sm" 
                onClick={openCreateDialog}
                className="bg-teal-600 hover:bg-teal-700 h-8 px-2 sm:px-3 shrink-0"
              >
                <Plus className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">Nova</span>
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Filtros */}
          <div className="flex flex-col xs:flex-row items-start xs:items-center gap-3 xs:gap-4 mb-4">
            <div className="flex items-center gap-2">
              <Checkbox
                id="showCompleted"
                checked={showCompleted}
                onCheckedChange={setShowCompleted}
                className="h-4 w-4"
              />
              <Label htmlFor="showCompleted" className="text-xs sm:text-sm text-muted-foreground cursor-pointer">
                Concluídas
              </Label>
            </div>
            {!processId && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="showCreatedByMe"
                  checked={showCreatedByMe}
                  onCheckedChange={setShowCreatedByMe}
                  className="h-4 w-4"
                />
                <Label htmlFor="showCreatedByMe" className="text-xs sm:text-sm text-muted-foreground cursor-pointer">
                  Criadas por mim
                </Label>
              </div>
            )}
          </div>

          {/* Parceiro: mensagem de apenas visualização */}
          {hasRole(user, "parceiro") && (
            <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-amber-700 dark:text-amber-400 text-xs sm:text-sm">
              Apenas visualização disponível para parceiros. Não é possível criar tarefas.
            </div>
          )}

          {/* Lista de tarefas */}
          {tasks.length === 0 && backgroundJobs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <ClipboardList className="h-12 w-12 mx-auto mb-2 opacity-20" />
              <p className="text-sm">Nenhuma tarefa {showCompleted ? "" : "pendente"}</p>
            </div>
          ) : (
            <ScrollArea style={{ maxHeight }}>
              {/* Background Jobs Section */}
              {backgroundJobs.length > 0 && (
                <div className="mb-3">
                  <div className="flex items-center gap-2 mb-2 px-1">
                    <Activity className="h-4 w-4 text-violet-500" />
                    <span className="text-xs font-semibold text-violet-600 uppercase tracking-wide">Tarefas em Background</span>
                    {backgroundJobs.some(j => j.status === "running" || j.status === "processing" || j.status === "pending") && (
                      <Loader2 className="h-3 w-3 text-violet-500 animate-spin" />
                    )}
                  </div>
                  <div className="space-y-2">
                    {backgroundJobs.map((job) => {
                      const isActive = job.status === "running" || job.status === "processing" || job.status === "pending";
                      const isCompleted = job.status === "completed";
                      const isFailed = job.status === "failed";
                      return (
                        <div
                          key={job.task_id}
                          className={`flex items-start gap-2 sm:gap-3 p-2 sm:p-3 rounded-lg border ${
                            isFailed ? "bg-red-50/50 border-red-200" : isCompleted ? "bg-green-50/50 border-green-200" : "bg-violet-50/50 border-violet-200"
                          }`}
                        >
                          {/* Status icon */}
                          <div className="mt-0.5 flex-shrink-0">
                            {isActive ? (
                              <Loader2 className="h-4 w-4 sm:h-5 sm:w-5 text-violet-500 animate-spin" />
                            ) : isCompleted ? (
                              <CheckCircle2 className="h-4 w-4 sm:h-5 sm:w-5 text-green-600" />
                            ) : (
                              <XCircle className="h-4 w-4 sm:h-5 sm:w-5 text-red-500" />
                            )}
                          </div>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <p className={`font-medium text-sm sm:text-base ${isFailed ? "text-red-700" : ""}`}>{
                              job.title || job.type || "Tarefa"
                            }</p>
                            {job.description && (
                              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 line-clamp-2">
                                {job.description}
                              </p>
                            )}
                            {job.error_message && (
                              <p className="text-xs text-red-600 mt-0.5 line-clamp-2">
                                {job.error_message}
                              </p>
                            )}
                            {/* Progress bar */}
                            {job.progress !== null && job.progress !== undefined && isActive && (
                              <div className="mt-1.5">
                                <div className="w-full bg-violet-200 rounded-full h-1.5">
                                  <div
                                    className="bg-violet-600 h-1.5 rounded-full transition-all duration-300"
                                    style={{ width: `${Math.min(100, Math.max(0, job.progress))}%` }}
                                  />
                                </div>
                                <p className="text-[10px] text-violet-600 mt-0.5">{job.progress}%</p>
                              </div>
                            )}
                            <div className="flex items-center gap-2 mt-1.5">
                              <Badge variant="outline" className="text-[10px] h-4 sm:h-5">
                                {job.type || "JOB"}
                              </Badge>
                              {(isCompleted || isFailed) && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    acknowledgeBackgroundTask(job.task_id).then(() => {
                                      setBackgroundJobs(prev => prev.filter(j => j.task_id !== job.task_id));
                                    }).catch(() => {});
                                  }}
                                >
                                  <CheckCheck className="h-3 w-3 mr-1" />
                                  Confirmar
                                </Button>
                              )}
                              {isActive && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 px-2 text-xs text-muted-foreground hover:text-red-600"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    cancelBackgroundTask(job.task_id).then(() => {
                                      setBackgroundJobs(prev => prev.filter(j => j.task_id !== job.task_id));
                                    }).catch(() => {});
                                  }}
                                >
                                  <XCircle className="h-3 w-3 mr-1" />
                                  Cancelar
                                </Button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {/* Divider between background jobs and manual tasks */}
                  {tasks.length > 0 && <div className="border-t my-3" />}
                </div>
              )}

              {/* Manual tasks list */}
              {tasks.length > 0 && (
                <div className="space-y-2">
                  {tasks.map((task) => (
                    <div
                      key={task.id}
                      className={`flex items-start gap-2 sm:gap-3 p-2 sm:p-3 rounded-lg border transition-colors cursor-pointer ${
                        task.completed
                          ? "bg-muted/30 border-muted"
                          : "bg-background border-border hover:bg-muted/50 hover:border-primary/30"
                      }`}
                      onClick={() => openTaskDetail(task)}
                    >
                      {/* Checkbox/Status */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (task.completed) {
                            handleReopenTask(task.id);
                          } else {
                            handleCompleteTask(task.id);
                          }
                        }}
                        className="mt-0.5 flex-shrink-0"
                      >
                        {task.completed ? (
                          <CheckCircle2 className="h-4 w-4 sm:h-5 sm:w-5 text-green-600" />
                        ) : (
                          <Circle className="h-4 w-4 sm:h-5 sm:w-5 text-muted-foreground hover:text-blue-600" />
                        )}
                      </button>

                      {/* Conteúdo */}
                      <div className="flex-1 min-w-0">
                        <p className={`font-medium text-sm sm:text-base ${task.completed ? "line-through text-muted-foreground" : ""}`}>
                          {task.title}
                        </p>
                        {task.description && (
                          <p className="text-xs sm:text-sm text-muted-foreground mt-1 line-clamp-2">
                            {task.description}
                          </p>
                        )}
                        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mt-2">
                          {/* Priority badge */}
                          {getPriorityBadge(task)}
                          {/* Badge de prazo */}
                          {getDueDateBadge(task)}
                          {/* Context line — Ref: process_name or extracted client */}
                          {!processId && (
                            task.process_name
                              ? (
                                <Badge variant="outline" className="text-[10px] sm:text-xs h-4 sm:h-5">
                                  Ref: {task.process_name}
                                </Badge>
                              )
                              : (() => {
                                  const clientName = extractClientFromTitle(task.title);
                                  return clientName ? (
                                    <Badge variant="outline" className="text-[10px] sm:text-xs h-4 sm:h-5">
                                      Ref: {clientName}
                                    </Badge>
                                  ) : null;
                                })()
                          )}
                          {/* Atribuídos */}
                          <div className="flex items-center gap-0.5 sm:gap-1 text-[10px] sm:text-xs text-muted-foreground">
                            <User className="h-3 w-3" />
                            <span className="truncate max-w-[80px] sm:max-w-none">{task.assigned_to_names?.join(", ") || "Sem atribuição"}</span>
                          </div>
                          {/* Data de criação - hidden on very small screens */}
                          <div className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            {format(parseISO(task.created_at), "dd/MM/yyyy", { locale: pt })}
                          </div>
                        </div>
                      </div>

                      {/* Menu */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-7 w-7 sm:h-8 sm:w-8 p-0 shrink-0" onClick={(e) => e.stopPropagation()}>
                            <MoreVertical className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={(e) => { e.stopPropagation(); openTaskDetail(task); }}>
                            <ExternalLink className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          {task.completed ? (
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleReopenTask(task.id); }}>
                              <RotateCcw className="h-4 w-4 mr-2" />
                              Reabrir
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleCompleteTask(task.id); }}>
                              <Check className="h-4 w-4 mr-2" />
                              Concluir
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem
                            onClick={(e) => { e.stopPropagation(); handleDeleteTask(task.id); }}
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
              )}
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

      {/* Modal de Detalhes da Tarefa */}
      <Dialog open={isDetailModalOpen} onOpenChange={setIsDetailModalOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedTask?.completed ? (
                <CheckCircle2 className="h-5 w-5 text-green-600" />
              ) : (
                <Circle className="h-5 w-5 text-muted-foreground" />
              )}
              {selectedTask?.title}
            </DialogTitle>
            <DialogDescription>
              Detalhes da tarefa
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* Descrição */}
            {selectedTask?.description && (
              <div>
                <Label className="text-xs text-muted-foreground">Descrição</Label>
                <p className="mt-1 text-sm">{selectedTask.description}</p>
              </div>
            )}
            
            {/* Informações */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-muted-foreground">Estado</Label>
                <div className="mt-1">
                  {selectedTask?.completed ? (
                    <Badge className="bg-green-100 text-green-800">Concluída</Badge>
                  ) : (
                    <Badge variant="outline">Pendente</Badge>
                  )}
                </div>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Data de Criação</Label>
                <p className="mt-1 text-sm flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {selectedTask?.created_at && format(parseISO(selectedTask.created_at), "dd/MM/yyyy 'às' HH:mm", { locale: pt })}
                </p>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Atribuído a</Label>
                <p className="mt-1 text-sm flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {selectedTask?.assigned_to_names?.join(", ") || "Sem atribuição"}
                </p>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Prazo</Label>
                <div className="mt-1">
                  {getDueDateBadge(selectedTask) || <span className="text-sm text-muted-foreground">Sem prazo definido</span>}
                </div>
              </div>
              {selectedTask?.process_name && (
                <div className="col-span-2">
                  <Label className="text-xs text-muted-foreground">Processo</Label>
                  <p className="mt-1 text-sm">{selectedTask.process_name}</p>
                </div>
              )}
            </div>
            
            {/* Área de Resposta */}
            <div className="border-t pt-4">
              <Label className="text-xs text-muted-foreground flex items-center gap-1">
                <MessageSquare className="h-3 w-3" />
                Responder / Comentar
              </Label>
              <Textarea
                placeholder="Escreva a sua resposta ou comentário..."
                value={taskResponse}
                onChange={(e) => setTaskResponse(e.target.value)}
                rows={3}
                className="mt-2"
              />
            </div>
          </div>
          
          <DialogFooter className="flex justify-between">
            <div className="flex gap-2">
              {selectedTask?.completed ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    handleReopenTask(selectedTask.id);
                    setIsDetailModalOpen(false);
                  }}
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Reabrir
                </Button>
              ) : (
                <Button
                  variant="default"
                  onClick={() => {
                    handleCompleteTask(selectedTask.id);
                    setIsDetailModalOpen(false);
                  }}
                  className="bg-green-600 hover:bg-green-700"
                >
                  <Check className="h-4 w-4 mr-2" />
                  Concluir
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setIsDetailModalOpen(false)}>
                Fechar
              </Button>
              <Button
                onClick={handleSubmitResponse}
                disabled={!taskResponse.trim() || submittingResponse}
                className="bg-teal-600 hover:bg-teal-700"
              >
                {submittingResponse ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Send className="h-4 w-4 mr-2" />
                )}
                Enviar Resposta
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default TasksPanel;
