/**
 * CalendarTab - Componente de Calendário para Admin Dashboard
 * Layout: Calendário mensal à esquerda, Próximos eventos à direita
 * CEO pode ver calendário de todos os utilizadores
 */
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Label } from "../ui/label";
import { ScrollArea } from "../ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Calendar } from "../ui/calendar";
import { Plus, Trash2, Eye, CalendarDays, Users } from "lucide-react";

const priorityOrder = { high: 1, medium: 2, low: 3 };
const priorityLabels = { high: "Alta", medium: "Média", low: "Baixa" };
const priorityColors = {
  high: "bg-red-100 text-red-800 border-red-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-green-100 text-green-800 border-green-200"
};

const CalendarTab = ({ 
  calendarDeadlines, 
  consultors, 
  intermediarios, 
  users,
  currentUser,
  onCreateEvent,
  onDeleteEvent
}) => {
  const navigate = useNavigate();
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [userFilter, setUserFilter] = useState("all");
  const [consultorFilter, setConsultorFilter] = useState("all");

  // Verificar se é CEO ou Admin (pode ver todos os calendários)
  const canViewAllCalendars = currentUser?.role === "ceo" || currentUser?.role === "admin";

  // Lista de utilizadores para filtro (excluindo clientes)
  const staffUsers = useMemo(() => {
    return users?.filter(u => u.role !== "cliente") || [];
  }, [users]);

  // Ordenar e filtrar eventos do calendário
  const sortedCalendarDeadlines = useMemo(() => {
    let filtered = [...calendarDeadlines];
    
    // Filtro por prioridade
    if (priorityFilter !== "all") {
      filtered = filtered.filter(d => d.priority === priorityFilter);
    }
    
    // Filtro por utilizador (participantes ou atribuído)
    if (userFilter !== "all") {
      filtered = filtered.filter(d => {
        // Verifica se o utilizador é participante
        if (d.participants?.includes(userFilter)) return true;
        // Verifica se é consultor ou mediador atribuído
        if (d.assigned_consultor_id === userFilter) return true;
        if (d.assigned_mediador_id === userFilter) return true;
        // Verifica se criou o evento
        if (d.created_by === userFilter) return true;
        return false;
      });
    }
    
    // Filtro por consultor
    if (consultorFilter !== "all") {
      filtered = filtered.filter(d => d.assigned_consultor_id === consultorFilter);
    }
    
    return filtered.sort((a, b) => {
      const dateCompare = new Date(a.due_date) - new Date(b.due_date);
      if (dateCompare !== 0) return dateCompare;
      return (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3);
    });
  }, [calendarDeadlines, priorityFilter, userFilter, consultorFilter]);

  // Próximos 10 eventos
  const upcomingDeadlines = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    return sortedCalendarDeadlines
      .filter(d => new Date(d.due_date) >= today)
      .slice(0, 10);
  }, [sortedCalendarDeadlines]);

  // Prazos para a data selecionada
  const deadlinesForDate = useMemo(() => {
    const dateStr = selectedDate.toISOString().split('T')[0];
    return sortedCalendarDeadlines
      .filter(d => d.due_date === dateStr)
      .sort((a, b) => (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3));
  }, [sortedCalendarDeadlines, selectedDate]);

  // Datas com prazos para highlight no calendário
  const datesWithDeadlines = useMemo(() => {
    return calendarDeadlines.map(d => new Date(d.due_date));
  }, [calendarDeadlines]);

  const getUserName = (userId) => {
    const user = users.find(u => u.id === userId);
    return user ? user.name : "-";
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Calendário Mensal - Lado Esquerdo */}
      <Card className="border-border lg:col-span-1">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <CalendarDays className="h-5 w-5" />
              Calendário
            </CardTitle>
            <Button size="sm" onClick={() => onCreateEvent(selectedDate)} className="bg-teal-600 hover:bg-teal-700">
              <Plus className="h-4 w-4 mr-1" />Evento
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Calendar
            mode="single"
            selected={selectedDate}
            onSelect={(date) => date && setSelectedDate(date)}
            className="rounded-md border mx-auto"
            modifiers={{ hasDeadline: datesWithDeadlines }}
            modifiersStyles={{ hasDeadline: { backgroundColor: "rgb(254 202 202)", fontWeight: "bold" } }}
          />
          
          {/* Filtros */}
          <div className="space-y-3 pt-4 border-t">
            <h4 className="font-medium text-sm">Filtros</h4>
            <div className="grid grid-cols-1 gap-2">
              {/* Filtro por Utilizador - Apenas para CEO/Admin */}
              {canViewAllCalendars && (
                <div className="space-y-1">
                  <Label className="text-xs flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    Utilizador
                  </Label>
                  <Select value={userFilter} onValueChange={setUserFilter}>
                    <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Todos" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">👥 Todos os utilizadores</SelectItem>
                      {staffUsers.map((u) => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.role})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="space-y-1">
                <Label className="text-xs">Prioridade</Label>
                <Select value={priorityFilter} onValueChange={setPriorityFilter}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Todas" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="high">🔴 Alta</SelectItem>
                    <SelectItem value="medium">🟡 Média</SelectItem>
                    <SelectItem value="low">🟢 Baixa</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Consultor</Label>
                <Select value={consultorFilter} onValueChange={setConsultorFilter}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Todos" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    {consultors.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          
          {/* Eventos do dia selecionado */}
          {deadlinesForDate.length > 0 && (
            <div className="space-y-2 pt-4 border-t">
              <h4 className="font-medium text-sm">
                {selectedDate.toLocaleDateString('pt-PT', { day: 'numeric', month: 'short' })}
              </h4>
              {deadlinesForDate.map((deadline) => (
                <div 
                  key={deadline.id} 
                  className={`p-2 rounded border text-xs ${priorityColors[deadline.priority] || 'bg-gray-50'}`}
                >
                  <div className="flex justify-between items-start">
                    <span className="font-medium truncate flex-1">{deadline.title}</span>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-5 w-5 shrink-0"
                      onClick={() => onDeleteEvent(deadline.id)}
                    >
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Próximos Eventos - Lado Direito */}
      <Card className="border-border lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <CalendarDays className="h-5 w-5" />
            Próximos Eventos
          </CardTitle>
          <CardDescription>
            {upcomingDeadlines.length} evento(s) agendado(s)
            {priorityFilter !== "all" && ` • Filtro: ${priorityLabels[priorityFilter]}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {upcomingDeadlines.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <CalendarDays className="h-12 w-12 mx-auto mb-3 opacity-20" />
              <p>Nenhum evento agendado</p>
              <Button variant="outline" className="mt-4" onClick={() => onCreateEvent(selectedDate)}>
                <Plus className="h-4 w-4 mr-2" />Criar Evento
              </Button>
            </div>
          ) : (
            <ScrollArea className="h-[500px]">
              <div className="space-y-3 pr-4">
                {upcomingDeadlines.map((deadline) => {
                  const deadlineDate = new Date(deadline.due_date);
                  const today = new Date();
                  today.setHours(0, 0, 0, 0);
                  const daysUntil = Math.ceil((deadlineDate - today) / (1000 * 60 * 60 * 24));
                  
                  return (
                    <div 
                      key={deadline.id} 
                      className="flex items-start justify-between p-4 bg-muted/30 rounded-lg border hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex gap-4">
                        {/* Data */}
                        <div className="text-center min-w-[60px]">
                          <div className="text-2xl font-bold text-blue-900">
                            {deadlineDate.getDate()}
                          </div>
                          <div className="text-xs text-muted-foreground uppercase">
                            {deadlineDate.toLocaleDateString('pt-PT', { month: 'short' })}
                          </div>
                          <Badge 
                            variant="outline" 
                            className={`mt-1 text-[10px] ${
                              daysUntil === 0 ? 'bg-red-100 text-red-800 border-red-200' : 
                              daysUntil <= 3 ? 'bg-amber-100 text-amber-800 border-amber-200' : ''
                            }`}
                          >
                            {daysUntil === 0 ? 'Hoje' : daysUntil === 1 ? 'Amanhã' : `${daysUntil} dias`}
                          </Badge>
                        </div>
                        
                        {/* Detalhes */}
                        <div className="space-y-1">
                          <p className="font-medium">{deadline.title}</p>
                          <p className="text-sm text-muted-foreground">
                            {deadline.client_name !== "Evento Geral" ? deadline.client_name : "Evento Geral"}
                          </p>
                          {deadline.description && (
                            <p className="text-xs text-muted-foreground line-clamp-2">{deadline.description}</p>
                          )}
                          <div className="flex gap-2 mt-2 flex-wrap">
                            <Badge className={priorityColors[deadline.priority]} variant="outline">
                              {priorityLabels[deadline.priority] || deadline.priority}
                            </Badge>
                            {deadline.participants?.length > 0 && (
                              <Badge variant="outline" className="text-xs">
                                {deadline.participants.length} participante(s)
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      
                      {/* Ações */}
                      <div className="flex items-center gap-1">
                        {deadline.process_id && (
                          <Button 
                            variant="ghost" 
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => navigate(`/process/${deadline.process_id}`)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        )}
                        <Button 
                          variant="ghost" 
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => onDeleteEvent(deadline.id)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CalendarTab;
