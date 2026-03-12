/**
 * PendingItemsList - Lista de Todos os Itens Pendentes
 * Mostra tarefas e prazos pendentes numa única lista
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ScrollArea } from "../components/ui/scroll-area";
import { 
  ArrowLeft, ClipboardList, Calendar, AlertTriangle, Clock, 
  CheckCircle2, Circle, User, Loader2, Filter
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";
import { useAuth } from "../contexts/AuthContext";
import { getMyTasks, completeTask, getMyDeadlines } from "../services/api";

const PendingItemsList = () => {
  const navigate = useNavigate();
  const { isImpersonating } = useAuth();
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [activeTab, setActiveTab] = useState("all");

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      
      // Buscar tarefas e prazos em paralelo
      // Usar getMyDeadlines para obter apenas prazos onde o utilizador tem acesso
      const [tasksRes, deadlinesRes] = await Promise.all([
        getMyTasks(false), // apenas não concluídas
        getMyDeadlines()   // apenas prazos com acesso ao processo
      ]);
      
      // Filtrar tarefas não concluídas
      const pendingTasks = (tasksRes.data || []).filter(t => !t.completed);
      
      // Filtrar prazos não concluídos
      const pendingDeadlines = (deadlinesRes.data || []).filter(d => !d.completed);
      
      setTasks(pendingTasks);
      setDeadlines(pendingDeadlines);
    } catch (error) {
      console.error("Erro ao carregar pendentes:", error);
      toast.error("Erro ao carregar itens pendentes");
    } finally {
      setLoading(false);
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

  // Combinar e ordenar todos os itens por urgência
  const getAllPendingItems = () => {
    const items = [];
    
    // Adicionar tarefas
    tasks.forEach(task => {
      let urgency = 100; // Default baixa urgência
      let dueDate = null;
      
      if (task.due_date) {
        dueDate = parseISO(task.due_date);
        const days = task.days_until_due;
        if (days < 0) urgency = 0; // Atrasada
        else if (days === 0) urgency = 1; // Hoje
        else if (days === 1) urgency = 2; // Amanhã
        else if (days <= 3) urgency = 3; // 3 dias
        else if (days <= 7) urgency = 4; // 7 dias
        else urgency = 5 + days;
      }
      
      items.push({
        id: task.id,
        type: "task",
        title: task.title,
        description: task.description,
        dueDate: dueDate,
        daysUntilDue: task.days_until_due,
        isOverdue: task.is_overdue,
        urgency,
        processId: task.process_id,
        processName: task.process_name,
        assignedTo: task.assigned_to_names,
        original: task
      });
    });
    
    // Adicionar prazos
    deadlines.forEach(deadline => {
      let urgency = 100;
      let dueDate = null;
      let daysUntilDue = null;
      let isOverdue = false;
      
      if (deadline.date) {
        dueDate = parseISO(deadline.date);
        const now = new Date();
        daysUntilDue = differenceInDays(dueDate, now);
        isOverdue = daysUntilDue < 0;
        
        if (daysUntilDue < 0) urgency = 0;
        else if (daysUntilDue === 0) urgency = 1;
        else if (daysUntilDue === 1) urgency = 2;
        else if (daysUntilDue <= 3) urgency = 3;
        else if (daysUntilDue <= 7) urgency = 4;
        else urgency = 5 + daysUntilDue;
      }
      
      items.push({
        id: deadline.id,
        type: "deadline",
        title: deadline.title,
        description: deadline.description,
        dueDate: dueDate,
        daysUntilDue,
        isOverdue,
        urgency,
        processId: deadline.process_id,
        processName: deadline.client_name,
        participants: deadline.participant_names,
        original: deadline
      });
    });
    
    // Ordenar por urgência (mais urgente primeiro)
    return items.sort((a, b) => a.urgency - b.urgency);
  };

  const getUrgencyBadge = (item) => {
    if (item.dueDate === null) {
      return (
        <Badge variant="outline" className="text-xs text-muted-foreground">
          Sem prazo
        </Badge>
      );
    }
    
    if (item.isOverdue) {
      return (
        <Badge variant="destructive" className="text-xs">
          <AlertTriangle className="h-3 w-3 mr-1" />
          Atrasado ({Math.abs(item.daysUntilDue)}d)
        </Badge>
      );
    } else if (item.daysUntilDue === 0) {
      return (
        <Badge variant="destructive" className="text-xs">
          <Clock className="h-3 w-3 mr-1" />
          Hoje
        </Badge>
      );
    } else if (item.daysUntilDue === 1) {
      return (
        <Badge className="text-xs bg-orange-500 hover:bg-orange-600">
          <Clock className="h-3 w-3 mr-1" />
          Amanhã
        </Badge>
      );
    } else if (item.daysUntilDue <= 3) {
      return (
        <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">
          <Clock className="h-3 w-3 mr-1" />
          {item.daysUntilDue} dias
        </Badge>
      );
    } else if (item.daysUntilDue <= 7) {
      return (
        <Badge variant="outline" className="text-xs text-yellow-600 border-yellow-300">
          <Calendar className="h-3 w-3 mr-1" />
          {item.daysUntilDue} dias
        </Badge>
      );
    } else {
      return (
        <Badge variant="outline" className="text-xs text-muted-foreground">
          <Calendar className="h-3 w-3 mr-1" />
          {format(item.dueDate, "dd/MM", { locale: pt })}
        </Badge>
      );
    }
  };

  const getTypeBadge = (type) => {
    if (type === "task") {
      return (
        <Badge variant="secondary" className="text-xs bg-blue-100 text-blue-800">
          <ClipboardList className="h-3 w-3 mr-1" />
          Tarefa
        </Badge>
      );
    } else {
      return (
        <Badge variant="secondary" className="text-xs bg-purple-100 text-purple-800">
          <Calendar className="h-3 w-3 mr-1" />
          Prazo
        </Badge>
      );
    }
  };

  const allItems = getAllPendingItems();
  const filteredItems = activeTab === "all" 
    ? allItems 
    : allItems.filter(item => item.type === activeTab);

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header - ajusta top quando há banner de impersonate */}
      <header className={`border-b bg-blue-950 text-white sticky z-50 ${isImpersonating ? 'top-12' : 'top-0'}`}>
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <Button 
              variant="ghost" 
              size="icon"
              onClick={() => navigate(-1)}
              className="text-white hover:bg-teal-600"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Itens Pendentes</h1>
              <p className="text-sm text-blue-200">
                {allItems.length} item(ns) pendente(s)
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-4 py-6">
        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <Card 
            className={`cursor-pointer transition-colors ${activeTab === 'all' ? 'border-blue-500 bg-blue-50' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            <CardContent className="pt-4 pb-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">{allItems.length}</p>
                <p className="text-xs text-muted-foreground">Total</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className={`cursor-pointer transition-colors ${activeTab === 'task' ? 'border-blue-500 bg-blue-50' : ''}`}
            onClick={() => setActiveTab('task')}
          >
            <CardContent className="pt-4 pb-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-800">{tasks.length}</p>
                <p className="text-xs text-muted-foreground">Tarefas</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className={`cursor-pointer transition-colors ${activeTab === 'deadline' ? 'border-purple-500 bg-purple-50' : ''}`}
            onClick={() => setActiveTab('deadline')}
          >
            <CardContent className="pt-4 pb-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-purple-600">{deadlines.length}</p>
                <p className="text-xs text-muted-foreground">Prazos</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* List */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <Filter className="h-5 w-5" />
              {activeTab === 'all' && 'Todos os Pendentes'}
              {activeTab === 'task' && 'Tarefas Pendentes'}
              {activeTab === 'deadline' && 'Prazos Pendentes'}
              <Badge variant="secondary" className="ml-2">{filteredItems.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {filteredItems.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <CheckCircle2 className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <p className="text-lg">Nenhum item pendente!</p>
                <p className="text-sm">Está tudo em dia.</p>
              </div>
            ) : (
              <ScrollArea className="h-[500px]">
                <div className="space-y-3">
                  {filteredItems.map((item) => (
                    <div
                      key={`${item.type}-${item.id}`}
                      className={`flex items-start gap-3 p-4 rounded-lg border transition-colors hover:bg-muted/50 ${
                        item.isOverdue ? 'border-red-200 bg-red-50/50' : 'border-border'
                      }`}
                    >
                      {/* Checkbox para tarefas */}
                      {item.type === 'task' ? (
                        <button
                          onClick={() => handleCompleteTask(item.id)}
                          className="mt-0.5 flex-shrink-0"
                          title="Marcar como concluída"
                        >
                          <Circle className="h-5 w-5 text-muted-foreground hover:text-green-600" />
                        </button>
                      ) : (
                        <div className="mt-0.5 flex-shrink-0">
                          <Calendar className="h-5 w-5 text-purple-500" />
                        </div>
                      )}

                      {/* Conteúdo */}
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          {getTypeBadge(item.type)}
                          {getUrgencyBadge(item)}
                        </div>
                        
                        <p className="font-medium">{item.title}</p>
                        
                        {item.description && (
                          <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                            {item.description}
                          </p>
                        )}
                        
                        <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-muted-foreground">
                          {/* Processo/Cliente */}
                          {item.processName && (
                            <span 
                              className="cursor-pointer hover:text-blue-600"
                              onClick={() => item.processId && navigate(`/process/${item.processId}`)}
                            >
                              📁 {item.processName}
                            </span>
                          )}
                          
                          {/* Atribuídos (tarefas) */}
                          {item.assignedTo && item.assignedTo.length > 0 && (
                            <span className="flex items-center gap-1">
                              <User className="h-3 w-3" />
                              {item.assignedTo.join(", ")}
                            </span>
                          )}
                          
                          {/* Participantes (prazos) */}
                          {item.participants && item.participants.length > 0 && (
                            <span className="flex items-center gap-1">
                              <User className="h-3 w-3" />
                              {item.participants.join(", ")}
                            </span>
                          )}
                          
                          {/* Data */}
                          {item.dueDate && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {format(item.dueDate, "dd/MM/yyyy HH:mm", { locale: pt })}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Ação */}
                      {item.processId && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            // Verificar se é um prazo sem acesso ao processo
                            // Os prazos podem ter participantes que não têm acesso ao processo
                            navigate(`/process/${item.processId}`);
                          }}
                          className="flex-shrink-0"
                          title="Ver processo"
                        >
                          Ver
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default PendingItemsList;
