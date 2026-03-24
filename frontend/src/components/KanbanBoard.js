import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { ScrollArea, ScrollBar } from "../components/ui/scroll-area";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Loader2, Search, Phone, Mail, User, Users, GripVertical, Eye, ChevronLeft, ChevronRight, AlertCircle, MapPin, Home, Euro, Calendar, ExternalLink, List, LayoutGrid, Plus, UserPlus, UserMinus } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { toast } from "sonner";
import { createClientProcess } from "../services/api";
import { Skeleton } from "../components/ui/skeleton";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Função para abrir cliente de email com dados preenchidos
const openEmailClient = (email, clientName) => {
  if (!email) {
    toast.error("Cliente não tem email registado");
    return;
  }
  
  const subject = encodeURIComponent(`Processo de Crédito - ${clientName}`);
  const body = encodeURIComponent(`Olá ${clientName},\n\nEsperamos que esteja tudo bem.\n\n`);
  
  window.open(`mailto:${email}?subject=${subject}&body=${body}`, '_blank');
};

const statusColors = {
  yellow: "bg-yellow-100 border-yellow-300 text-yellow-900 dark:bg-yellow-900/40 dark:border-yellow-700 dark:text-yellow-100",
  blue: "bg-blue-100 border-blue-300 dark:bg-blue-900/40 dark:border-blue-700",
  purple: "bg-purple-100 border-purple-300 dark:bg-purple-900/40 dark:border-purple-700",
  orange: "bg-orange-100 border-orange-300 dark:bg-orange-900/40 dark:border-orange-700",
  green: "bg-green-100 border-green-300 dark:bg-green-900/40 dark:border-green-700",
  red: "bg-red-100 border-red-300 dark:bg-red-900/40 dark:border-red-700",
};

const statusHeaderColors = {
  yellow: "bg-yellow-500 text-yellow-900",
  blue: "bg-blue-500",
  purple: "bg-purple-500",
  orange: "bg-orange-500",
  green: "bg-green-500",
  red: "bg-red-500",
};

// Status relacionados com bancos - ao mover para estas colunas, verificar créditos ativos
const BANK_RELATED_STATUSES = ["enviado_bruno", "enviado_luis", "enviado_bcp_rui", "fase_bancaria", "entradas_precision"];

const KanbanBoard = ({ token, user, consultorFilter = "all", mediadorFilter = "all" }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [kanbanData, setKanbanData] = useState({ columns: [], total_processes: 0 });
  const [searchTerm, setSearchTerm] = useState("");
  const [draggingCard, setDraggingCard] = useState(null);
  const [dragOverColumn, setDragOverColumn] = useState(null);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [selectedProcess, setSelectedProcess] = useState(null);
  const [showProcessDialog, setShowProcessDialog] = useState(false);
  const [collapsedColumns, setCollapsedColumns] = useState(new Set()); // Colunas colapsadas
  
  // O7 - Filtros do Kanban
  const [dateFilter, setDateFilter] = useState("all"); // all, today, week, month
  const [urgencyFilter, setUrgencyFilter] = useState("all"); // all, overdue, urgent, normal
  
  // Estado para aviso de bancos com créditos ativos
  const [showBankWarning, setShowBankWarning] = useState(false);
  const [pendingMove, setPendingMove] = useState(null);
  
  // Estado para criação de novo cliente
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newClient, setNewClient] = useState({
    client_name: "",
    client_email: "",
    client_phone: "",
    process_type: "credito_habitacao"
  });
  
  // Estado para atribuição de processos
  const [showAssignDialog, setShowAssignDialog] = useState(false);
  const [assigningProcess, setAssigningProcess] = useState(null);
  const [appUsers, setAppUsers] = useState([]);
  const [selectedConsultor, setSelectedConsultor] = useState("");
  const [selectedMediador, setSelectedMediador] = useState("");
  const [savingAssignment, setSavingAssignment] = useState(false);
  
  // Verificar se o utilizador pode criar clientes
  const canCreateClient = user && ["intermediario", "mediador"].includes(user.role);
  
  const handleCreateClient = async () => {
    if (!newClient.client_name.trim()) {
      toast.error("Por favor, introduza o nome do cliente");
      return;
    }
    
    setCreating(true);
    try {
      await createClientProcess({
        client_name: newClient.client_name,
        client_email: newClient.client_email,
        process_type: newClient.process_type,
        personal_data: {
          nome_completo: newClient.client_name,
          email: newClient.client_email,
          telefone: newClient.client_phone
        }
      });
      
      toast.success(`Cliente "${newClient.client_name}" criado com sucesso!`);
      setShowCreateDialog(false);
      setNewClient({
        client_name: "",
        client_email: "",
        client_phone: "",
        process_type: "credito_habitacao"
      });
      fetchKanbanData();
    } catch (error) {
      console.error("Erro ao criar cliente:", error);
      toast.error(error.response?.data?.detail || "Erro ao criar cliente");
    } finally {
      setCreating(false);
    }
  };

  // Buscar utilizadores da aplicação
  const fetchUsers = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const users = await response.json();
        // Filtrar: ativos, não admin, não ceo
        setAppUsers(users.filter(u => 
          u.is_active !== false && 
          u.role !== "admin" && 
          u.role !== "ceo"
        ));
      }
    } catch (error) {
      console.error("Erro ao buscar utilizadores:", error);
    }
  };

  // Abrir dialog de atribuição
  const openAssignDialog = (process, e) => {
    if (e) e.stopPropagation();
    setAssigningProcess(process);
    setSelectedConsultor(process.assigned_consultor_id || "");
    setSelectedMediador(process.assigned_mediador_id || "");
    setShowAssignDialog(true);
    if (appUsers.length === 0) {
      fetchUsers();
    }
  };

  // Guardar atribuições
  const handleSaveAssignment = async () => {
    if (!assigningProcess) return;
    
    setSavingAssignment(true);
    try {
      // Construir query params
      const params = new URLSearchParams();
      params.append("consultor_id", selectedConsultor || "");
      params.append("mediador_id", selectedMediador || "");
      
      const response = await fetch(`${API_URL}/api/processes/${assigningProcess.id}/assign?${params.toString()}`, {
        method: "POST",
        headers: { 
          Authorization: `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        toast.success("Atribuições actualizadas com sucesso");
        setShowAssignDialog(false);
        fetchKanbanData();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao actualizar atribuições");
      }
    } catch (error) {
      console.error("Erro ao guardar atribuições:", error);
      toast.error("Erro ao guardar atribuições");
    } finally {
      setSavingAssignment(false);
    }
  };

  const fetchKanbanData = useCallback(async () => {
    try {
      // Construir URL com filtros
      const params = new URLSearchParams();
      if (consultorFilter && consultorFilter !== "all") {
        if (consultorFilter === "none") {
          params.append("consultor_id", "none");
        } else {
          params.append("consultor_id", consultorFilter);
        }
      }
      if (mediadorFilter && mediadorFilter !== "all") {
        if (mediadorFilter === "none") {
          params.append("mediador_id", "none");
        } else {
          params.append("mediador_id", mediadorFilter);
        }
      }
      
      const url = params.toString() 
        ? `${API_URL}/api/processes/kanban?${params.toString()}`
        : `${API_URL}/api/processes/kanban`;
      
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Failed to fetch kanban data");
      const data = await response.json();
      setKanbanData(data);
    } catch (error) {
      console.error("Error fetching kanban:", error);
      toast.error("Erro ao carregar dados do Kanban");
    } finally {
      setLoading(false);
    }
  }, [token, consultorFilter, mediadorFilter]);

  useEffect(() => {
    fetchKanbanData();
    
    // Polling para atualizar dados a cada 10 segundos (sync com Trello)
    const pollInterval = setInterval(() => {
      fetchKanbanData();
    }, 10000);
    
    return () => clearInterval(pollInterval);
  }, [fetchKanbanData]);

  const handleDragStart = (e, process, columnName) => {
    setDraggingCard({ process, sourceColumn: columnName });
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e, columnName) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverColumn(columnName);
  };

  const handleDragLeave = () => {
    setDragOverColumn(null);
  };

  // Função para obter bancos com créditos ativos do processo
  const getActiveBanks = (process) => {
    // Os bancos com créditos ativos estão em financial_data.bancos_creditos
    if (process.financial_data?.bancos_creditos && Array.isArray(process.financial_data.bancos_creditos)) {
      return process.financial_data.bancos_creditos.filter(banco => banco && banco.trim() !== "");
    }
    return [];
  };

  // Função para executar a movimentação do processo
  const executeMoveProcess = async (process, targetColumn, sourceColumn) => {
    // Optimistic update
    setKanbanData((prev) => {
      const newColumns = prev.columns.map((col) => {
        if (col.name === sourceColumn) {
          return {
            ...col,
            processes: col.processes.filter((p) => p.id !== process.id),
            count: col.count - 1,
          };
        }
        if (col.name === targetColumn) {
          return {
            ...col,
            processes: [...col.processes, { ...process, status: targetColumn }],
            count: col.count + 1,
          };
        }
        return col;
      });
      return { ...prev, columns: newColumns };
    });

    // API call to move process
    try {
      const response = await fetch(
        `${API_URL}/api/processes/kanban/${process.id}/move?new_status=${targetColumn}`,
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        throw new Error("Failed to move process");
      }

      toast.success("Processo movido com sucesso");
    } catch (error) {
      console.error("Error moving process:", error);
      toast.error("Erro ao mover processo");
      // Revert on error
      fetchKanbanData();
    }
  };

  const handleDrop = async (e, targetColumn) => {
    e.preventDefault();
    setDragOverColumn(null);

    if (!draggingCard || draggingCard.sourceColumn === targetColumn) {
      setDraggingCard(null);
      return;
    }

    const { process, sourceColumn } = draggingCard;
    setDraggingCard(null);

    // Verificar se está a mover para uma coluna relacionada com bancos
    if (BANK_RELATED_STATUSES.includes(targetColumn)) {
      const activeBanks = getActiveBanks(process);
      if (activeBanks.length > 0) {
        // Mostrar aviso com os bancos onde o cliente tem créditos ativos
        setPendingMove({ process, targetColumn, sourceColumn, activeBanks });
        setShowBankWarning(true);
        return;
      }
    }

    // Se não há créditos ativos ou não é coluna de banco, mover diretamente
    await executeMoveProcess(process, targetColumn, sourceColumn);
  };

  // Confirmar movimentação após aviso de bancos
  const handleConfirmBankMove = async () => {
    if (pendingMove) {
      const { process, targetColumn, sourceColumn } = pendingMove;
      await executeMoveProcess(process, targetColumn, sourceColumn);
    }
    setShowBankWarning(false);
    setPendingMove(null);
  };

  // Cancelar movimentação
  const handleCancelBankMove = () => {
    setShowBankWarning(false);
    setPendingMove(null);
  };

  const filteredColumns = kanbanData.columns.map((column) => ({
    ...column,
    processes: column.processes.filter((process) => {
      // Text search filter
      const matchesSearch = 
        process.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        process.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        process.client_phone?.includes(searchTerm) ||
        process.consultor_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        process.mediador_name?.toLowerCase().includes(searchTerm.toLowerCase());
      
      // O7 - Date filter
      let matchesDate = true;
      if (dateFilter !== "all" && process.created_at) {
        const created = new Date(process.created_at);
        const now = new Date();
        if (dateFilter === "today") {
          matchesDate = created.toDateString() === now.toDateString();
        } else if (dateFilter === "week") {
          const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
          matchesDate = created >= weekAgo;
        } else if (dateFilter === "month") {
          const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
          matchesDate = created >= monthAgo;
        }
      }
      
      // O7 - Urgency filter (based on days since creation without update)
      let matchesUrgency = true;
      if (urgencyFilter !== "all") {
        const lastUpdate = process.updated_at || process.created_at;
        if (lastUpdate) {
          const daysSinceUpdate = Math.floor((Date.now() - new Date(lastUpdate).getTime()) / (1000 * 60 * 60 * 24));
          if (urgencyFilter === "overdue") {
            matchesUrgency = daysSinceUpdate > 14;
          } else if (urgencyFilter === "urgent") {
            matchesUrgency = daysSinceUpdate > 7 && daysSinceUpdate <= 14;
          } else if (urgencyFilter === "normal") {
            matchesUrgency = daysSinceUpdate <= 7;
          }
        }
      }
      
      return matchesSearch && matchesDate && matchesUrgency;
    }),
  }));

  // Obter todos os processos filtrados para vista de lista
  const allFilteredProcesses = searchTerm.length >= 2 
    ? filteredColumns.flatMap(col => col.processes.map(p => ({ ...p, columnLabel: col.label, columnColor: col.color })))
    : [];

  const [viewMode, setViewMode] = useState("kanban"); // kanban ou list

  const scrollContainer = (direction) => {
    const container = document.getElementById("kanban-scroll-container");
    if (container) {
      const scrollAmount = 350;
      const newPosition = direction === "left" 
        ? scrollPosition - scrollAmount 
        : scrollPosition + scrollAmount;
      container.scrollTo({ left: newPosition, behavior: "smooth" });
      setScrollPosition(newPosition);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4" data-testid="kanban-loading">
        {/* Header Skeleton */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <Skeleton className="h-7 w-[250px] mb-2" />
            <Skeleton className="h-4 w-[180px]" />
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Skeleton className="h-10 w-full sm:w-64" />
            <Skeleton className="h-10 w-10" />
            <Skeleton className="h-10 w-10" />
          </div>
        </div>
        {/* Kanban Columns Skeleton */}
        <div className="flex gap-4 overflow-hidden">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex-shrink-0 w-[320px]">
              <Skeleton className="h-12 w-full rounded-t-lg" />
              <div className="bg-muted/30 min-h-[60vh] rounded-b-lg p-2 space-y-2">
                {[1, 2, 3].map((j) => (
                  <Skeleton key={j} className="h-24 w-full rounded-lg" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="kanban-board">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold">Quadro Geral de Processos</h2>
          <p className="text-sm text-muted-foreground">
            {kanbanData.total_processes} processos • Arraste para mover entre fases ou clique para ver detalhes
          </p>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar cliente..."
              className="pl-10"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          {/* Toggle View Mode quando há pesquisa */}
          {searchTerm.length >= 2 && (
            <div className="flex gap-1 border rounded-md p-1">
              <Button 
                variant={viewMode === "kanban" ? "default" : "ghost"} 
                size="icon"
                className="h-8 w-8"
                onClick={() => setViewMode("kanban")}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
              <Button 
                variant={viewMode === "list" ? "default" : "ghost"} 
                size="icon"
                className="h-8 w-8"
                onClick={() => setViewMode("list")}
              >
                <List className="h-4 w-4" />
              </Button>
            </div>
          )}
          <div className="flex gap-1">
            <Button variant="outline" size="icon" onClick={() => scrollContainer("left")} aria-label="Deslocar para a esquerda">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" onClick={() => scrollContainer("right")} aria-label="Deslocar para a direita">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* O7 - Kanban Filters */}
      <div className="flex flex-wrap items-center gap-2" data-testid="kanban-filters">
        <Select value={dateFilter} onValueChange={setDateFilter}>
          <SelectTrigger className="h-8 w-[130px] text-xs" data-testid="kanban-date-filter">
            <Calendar className="h-3 w-3 mr-1" />
            <SelectValue placeholder="Data" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as datas</SelectItem>
            <SelectItem value="today">Hoje</SelectItem>
            <SelectItem value="week">Última semana</SelectItem>
            <SelectItem value="month">Último mês</SelectItem>
          </SelectContent>
        </Select>
        <Select value={urgencyFilter} onValueChange={setUrgencyFilter}>
          <SelectTrigger className="h-8 w-[130px] text-xs" data-testid="kanban-urgency-filter">
            <AlertCircle className="h-3 w-3 mr-1" />
            <SelectValue placeholder="Urgência" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas</SelectItem>
            <SelectItem value="overdue">Atrasados (&gt;14d)</SelectItem>
            <SelectItem value="urgent">Urgentes (7-14d)</SelectItem>
            <SelectItem value="normal">Recentes (&lt;7d)</SelectItem>
          </SelectContent>
        </Select>
        {(dateFilter !== "all" || urgencyFilter !== "all") && (
          <Button 
            variant="ghost" 
            size="sm" 
            className="h-8 text-xs"
            onClick={() => { setDateFilter("all"); setUrgencyFilter("all"); }}
            data-testid="kanban-clear-filters"
          >
            Limpar filtros
          </Button>
        )}
        <span className="text-xs text-muted-foreground ml-auto">
          {filteredColumns.reduce((acc, col) => acc + col.processes.length, 0)} processos visíveis
        </span>
      </div>

      {/* Search Results List View */}
      {searchTerm.length >= 2 && viewMode === "list" && (
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <Search className="h-5 w-5" />
              Resultados da Pesquisa
              <Badge variant="secondary">{allFilteredProcesses.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[500px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Contacto</TableHead>
                    <TableHead>Fase</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Consultor</TableHead>
                    <TableHead>Intermediário</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allFilteredProcesses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                        Nenhum resultado para &quot;{searchTerm}&quot;
                      </TableCell>
                    </TableRow>
                  ) : (
                    allFilteredProcesses.map((process) => (
                      <TableRow
                        key={process.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => navigate(`/process/${process.id}`)}
                      >
                        <TableCell>
                          <div>
                            <p className="font-medium">{process.client_name}</p>
                            <p className="text-xs text-muted-foreground font-semibold">
                              #{process.process_number || '—'}
                            </p>
                            {process.under_35 && (
                              <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700 mt-1">
                                &lt;35 anos
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm">
                            <p className="flex items-center gap-1">
                              <Phone className="h-3 w-3" />
                              {process.client_phone || "-"}
                            </p>
                            <p className="text-muted-foreground text-xs truncate max-w-[150px]">
                              {process.client_email}
                            </p>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge 
                            className={`${statusColors[process.columnColor]} border text-xs`}
                          >
                            {process.columnLabel}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium">
                          {process.property_value 
                            ? `€${process.property_value.toLocaleString('pt-PT')}`
                            : "-"
                          }
                        </TableCell>
                        <TableCell className="text-sm">
                          {process.consultor_name || "-"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {process.mediador_name || "-"}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/process/${process.id}`);
                            }}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Kanban Board - Mostrar quando não há pesquisa ou viewMode é kanban */}
      {(searchTerm.length < 2 || viewMode === "kanban") && (
      <div className="relative">
        <ScrollArea className="w-full whitespace-nowrap rounded-md">
          <div
            id="kanban-scroll-container"
            className="flex gap-4 pb-4 min-h-[70vh]"
            onScroll={(e) => setScrollPosition(e.currentTarget.scrollLeft)}
          >
            {filteredColumns.map((column) => {
              const isCollapsed = collapsedColumns.has(column.id);
              const isEmpty = column.count === 0;
              
              // Toggle collapse
              const toggleCollapse = () => {
                setCollapsedColumns(prev => {
                  const newSet = new Set(prev);
                  if (newSet.has(column.id)) {
                    newSet.delete(column.id);
                  } else {
                    newSet.add(column.id);
                  }
                  return newSet;
                });
              };
              
              return (
              <div
                key={column.id}
                className={`flex-shrink-0 ${isCollapsed ? 'w-[60px]' : 'w-[320px]'} rounded-lg border-2 transition-all ${
                  dragOverColumn === column.name
                    ? "border-primary border-dashed bg-primary/5"
                    : "border-transparent"
                }`}
                onDragOver={(e) => handleDragOver(e, column.name)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, column.name)}
              >
                {/* Column Header */}
                <div 
                  className={`${statusHeaderColors[column.color] || "bg-gray-500"} rounded-t-lg px-4 py-3 cursor-pointer`}
                  onClick={isEmpty ? toggleCollapse : undefined}
                  title={isEmpty ? (isCollapsed ? "Expandir" : "Minimizar") : ""}
                >
                  <div className="flex items-center justify-between">
                    {isCollapsed ? (
                      <div className="flex flex-col items-center w-full">
                        <Badge variant="secondary" className="bg-white/20 text-white hover:bg-white/30 mb-1">
                          {column.count}
                        </Badge>
                        <span className="text-white text-xs writing-mode-vertical transform -rotate-90 whitespace-nowrap mt-4">
                          {column.label}
                        </span>
                      </div>
                    ) : (
                      <>
                        <h3 className="font-semibold text-white text-sm truncate">
                          {column.label}
                        </h3>
                        <div className="flex items-center gap-1">
                          <Badge variant="secondary" className="bg-white/20 text-white hover:bg-white/30">
                            {column.count}
                          </Badge>
                          {isEmpty && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-white/70 hover:text-white hover:bg-white/20"
                              onClick={(e) => { e.stopPropagation(); toggleCollapse(); }}
                            >
                              <ChevronLeft className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>

                {/* Column Content - Hidden when collapsed */}
                {!isCollapsed && (
                <div className={`${statusColors[column.color] || "bg-gray-100"} min-h-[60vh] rounded-b-lg p-2`}>
                  <ScrollArea className="h-[60vh]">
                    <div className="space-y-2 pr-2">
                      {column.processes.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground text-sm">
                          <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                          <p>Nenhum processo</p>
                        </div>
                      ) : (
                        column.processes.map((process) => (
                          <Card
                            key={process.id}
                            className={`cursor-pointer hover:shadow-md transition-shadow ${
                              draggingCard?.process.id === process.id ? "opacity-50" : ""
                            }`}
                            draggable
                            onDragStart={(e) => handleDragStart(e, process, column.name)}
                            onClick={(e) => {
                              // Não navegar se estiver arrastando
                              if (!draggingCard) {
                                setSelectedProcess(process);
                                setShowProcessDialog(true);
                              }
                            }}
                            data-testid={`process-card-${process.id}`}
                          >
                            <CardContent className="p-2">
                              {/* Layout com nome visível */}
                              <div className="space-y-1.5">
                                {/* Linha 1: Número do processo */}
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-1.5">
                                    <GripVertical className="h-3 w-3 text-muted-foreground flex-shrink-0 cursor-grab" />
                                    <span className="text-[10px] font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                      #{process.process_number || '—'}
                                    </span>
                                    {process.prioridade && (
                                      <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4">!</Badge>
                                    )}
                                  </div>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-5 w-5 flex-shrink-0"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      navigate(`/process/${process.id}`);
                                    }}
                                    title="Ver processo"
                                    data-testid={`view-process-${process.id}`}
                                  >
                                    <Eye className="h-3 w-3" />
                                  </Button>
                                </div>
                                {/* Linha 2: Nome do cliente - SEMPRE VISÍVEL */}
                                <p 
                                  className="font-semibold text-sm leading-snug break-words whitespace-normal min-w-0" 
                                  style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}
                                  title={process.client_name}
                                >
                                  {process.client_name}
                                </p>
                                {/* Linha 3: Consultor (se existir) */}
                                {process.consultor_name && (
                                  <div className="flex items-center gap-1">
                                    <User className="h-3 w-3 text-muted-foreground" />
                                    <span className="text-[10px] text-muted-foreground truncate">
                                      {process.consultor_name}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </div>
                )}
              </div>
            );
            })}
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
      </div>
      )}

      {/* Process Details Dialog */}
      <Dialog open={showProcessDialog} onOpenChange={setShowProcessDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" aria-describedby="process-dialog-description">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Detalhes do Processo</span>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => {
                  setShowProcessDialog(false);
                  navigate(`/process/${selectedProcess?.id}`);
                }}
              >
                Abrir Página Completa
              </Button>
            </DialogTitle>
            <DialogDescription id="process-dialog-description" className="sr-only">
              Visualização resumida dos detalhes do processo do cliente
            </DialogDescription>
          </DialogHeader>
          
          {selectedProcess && (
            <div className="space-y-6 mt-4">
              {/* Cliente Info */}
              <div className="space-y-3">
                <h3 className="font-semibold text-lg flex items-center gap-2">
                  <User className="h-5 w-5 text-primary" />
                  Informações do Cliente
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-muted-foreground">Nome</p>
                    <p className="font-medium">{selectedProcess.client_name}</p>
                  </div>
                  {selectedProcess.client_email && (
                    <div>
                      <p className="text-muted-foreground">Email</p>
                      <p className="font-medium flex items-center gap-1">
                        <Mail className="h-3 w-3" />
                        {selectedProcess.client_email}
                      </p>
                    </div>
                  )}
                  {selectedProcess.client_phone && (
                    <div>
                      <p className="text-muted-foreground">Telefone</p>
                      <p className="font-medium flex items-center gap-1">
                        <Phone className="h-3 w-3" />
                        {selectedProcess.client_phone}
                      </p>
                    </div>
                  )}
                  {selectedProcess.client_nif && (
                    <div>
                      <p className="text-muted-foreground">NIF</p>
                      <p className="font-medium">{selectedProcess.client_nif}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Imóvel Info */}
              <div className="space-y-3">
                <h3 className="font-semibold text-lg flex items-center gap-2">
                  <Home className="h-5 w-5 text-primary" />
                  Informações do Imóvel
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {selectedProcess.property_type && (
                    <div>
                      <p className="text-muted-foreground">Tipo</p>
                      <p className="font-medium capitalize">{selectedProcess.property_type}</p>
                    </div>
                  )}
                  {selectedProcess.property_location && (
                    <div>
                      <p className="text-muted-foreground">Localização</p>
                      <p className="font-medium flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {selectedProcess.property_location}
                      </p>
                    </div>
                  )}
                  {selectedProcess.property_value && (
                    <div>
                      <p className="text-muted-foreground">Valor do Imóvel</p>
                      <p className="font-medium text-emerald-600 flex items-center gap-1">
                        <Euro className="h-3 w-3" />
                        {selectedProcess.property_value.toLocaleString('pt-PT')}€
                      </p>
                    </div>
                  )}
                  {selectedProcess.loan_amount && (
                    <div>
                      <p className="text-muted-foreground">Valor Financiado</p>
                      <p className="font-medium flex items-center gap-1">
                        <Euro className="h-3 w-3" />
                        {selectedProcess.loan_amount.toLocaleString('pt-PT')}€
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Status e Prioridade */}
              <div className="space-y-3">
                <h3 className="font-semibold text-lg">Estado e Prioridade</h3>
                <div className="flex gap-2 flex-wrap">
                  <Badge variant="outline" className="capitalize">
                    {selectedProcess.status?.replace(/_/g, ' ')}
                  </Badge>
                  {selectedProcess.priority && (
                    <Badge 
                      variant={selectedProcess.priority === 'high' ? 'destructive' : 'secondary'}
                      className="capitalize"
                    >
                      {selectedProcess.priority === 'high' ? 'Alta' : selectedProcess.priority === 'medium' ? 'Média' : 'Baixa'}
                    </Badge>
                  )}
                  {selectedProcess.service_type && (
                    <Badge variant="outline" className="capitalize">
                      {selectedProcess.service_type.replace(/_/g, ' ')}
                    </Badge>
                  )}
                </div>
              </div>

              {/* Atribuições */}
              {(selectedProcess.assigned_consultor_name || selectedProcess.assigned_intermediario_name) && (
                <div className="space-y-3">
                  <h3 className="font-semibold text-lg flex items-center gap-2">
                    <Users className="h-5 w-5 text-primary" />
                    Atribuições
                  </h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    {selectedProcess.assigned_consultor_name && (
                      <div>
                        <p className="text-muted-foreground">Consultor</p>
                        <p className="font-medium">{selectedProcess.assigned_consultor_name}</p>
                      </div>
                    )}
                    {selectedProcess.assigned_intermediario_name && (
                      <div>
                        <p className="text-muted-foreground">Intermediário</p>
                        <p className="font-medium">{selectedProcess.assigned_intermediario_name}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Notas */}
              {selectedProcess.notes && (
                <div className="space-y-3">
                  <h3 className="font-semibold text-lg">Notas</h3>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{selectedProcess.notes}</p>
                </div>
              )}

              {/* Datas */}
              <div className="space-y-3">
                <h3 className="font-semibold text-lg flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-primary" />
                  Datas
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {selectedProcess.created_at && (
                    <div>
                      <p className="text-muted-foreground">Criado em</p>
                      <p className="font-medium">{new Date(selectedProcess.created_at).toLocaleDateString('pt-PT')}</p>
                    </div>
                  )}
                  {selectedProcess.updated_at && (
                    <div>
                      <p className="text-muted-foreground">Última atualização</p>
                      <p className="font-medium">{new Date(selectedProcess.updated_at).toLocaleDateString('pt-PT')}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Dialog para criar novo cliente */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-[500px]" aria-describedby="create-client-description">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="h-5 w-5" />
              Criar Novo Cliente
            </DialogTitle>
            <DialogDescription id="create-client-description">
              Preencha os dados para criar um novo cliente no sistema.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="client_name">Nome do Cliente *</Label>
              <Input
                id="client_name"
                placeholder="Nome completo do cliente"
                value={newClient.client_name}
                onChange={(e) => setNewClient({ ...newClient, client_name: e.target.value })}
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="client_email">Email</Label>
                <Input
                  id="client_email"
                  type="email"
                  placeholder="email@exemplo.com"
                  value={newClient.client_email}
                  onChange={(e) => setNewClient({ ...newClient, client_email: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="client_phone">Telefone</Label>
                <Input
                  id="client_phone"
                  placeholder="+351 000 000 000"
                  value={newClient.client_phone}
                  onChange={(e) => setNewClient({ ...newClient, client_phone: e.target.value })}
                />
              </div>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="process_type">Tipo de Processo</Label>
              <Select 
                value={newClient.process_type} 
                onValueChange={(v) => setNewClient({ ...newClient, process_type: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="credito_habitacao">Crédito Habitação</SelectItem>
                  <SelectItem value="credito_pessoal">Crédito Pessoal</SelectItem>
                  <SelectItem value="credito_consolidado">Crédito Consolidado</SelectItem>
                  <SelectItem value="credito_automovel">Crédito Automóvel</SelectItem>
                  <SelectItem value="transferencia_credito">Transferência de Crédito</SelectItem>
                  <SelectItem value="imobiliario">Imobiliário</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleCreateClient} 
              disabled={creating || !newClient.client_name.trim()}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {creating ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  A criar...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-2" />
                  Criar Cliente
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog para atribuir utilizadores ao processo */}
      <Dialog open={showAssignDialog} onOpenChange={setShowAssignDialog}>
        <DialogContent className="sm:max-w-[500px]" aria-describedby="assign-users-description">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-purple-600" />
              Gerir Atribuições
            </DialogTitle>
            <DialogDescription id="assign-users-description">
              Atribua consultores e mediadores a este processo.
            </DialogDescription>
          </DialogHeader>
          
          {assigningProcess && (
            <div className="space-y-4">
              <div className="p-3 bg-gray-50 rounded-lg">
                <p className="font-medium">{assigningProcess.client_name}</p>
                <p className="text-sm text-muted-foreground">
                  #{assigningProcess.process_number || '—'}
                </p>
              </div>
              
              <div className="space-y-3">
                <div>
                  <Label className="text-sm font-medium">Consultor</Label>
                  <Select value={selectedConsultor || "none"} onValueChange={(v) => setSelectedConsultor(v === "none" ? "" : v)}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Seleccionar consultor..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Nenhum</SelectItem>
                      {appUsers
                        .filter(u => ["consultor", "consultor_intermediario", "diretor", "admin", "ceo"].includes(u.role))
                        .map(u => (
                          <SelectItem key={u.id} value={u.id}>
                            {u.name} ({u.role})
                          </SelectItem>
                        ))
                      }
                    </SelectContent>
                  </Select>
                </div>
                
                <div>
                  <Label className="text-sm font-medium">Intermediário / Mediador</Label>
                  <Select value={selectedMediador || "none"} onValueChange={(v) => setSelectedMediador(v === "none" ? "" : v)}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Seleccionar intermediário..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Nenhum</SelectItem>
                      {appUsers
                        .filter(u => ["mediador", "intermediario", "consultor_intermediario", "intermediario_credito", "diretor"].includes(u.role))
                        .map(u => (
                          <SelectItem key={u.id} value={u.id}>
                            {u.name} ({u.role})
                          </SelectItem>
                        ))
                      }
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}
          
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setShowAssignDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleSaveAssignment}
              disabled={savingAssignment}
              className="bg-purple-600 hover:bg-purple-700"
            >
              {savingAssignment ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  A guardar...
                </>
              ) : (
                "Guardar"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* AlertDialog para aviso de bancos com créditos ativos */}
      <AlertDialog open={showBankWarning} onOpenChange={setShowBankWarning}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-amber-600">
              <AlertCircle className="h-5 w-5" />
              Aviso: Créditos Ativos
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  O cliente <strong>{pendingMove?.process?.client_name}</strong> tem créditos ativos nos seguintes bancos:
                </p>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <ul className="list-disc list-inside space-y-1">
                    {pendingMove?.activeBanks?.map((bank, index) => (
                      <li key={index} className="font-medium text-amber-800">{bank}</li>
                    ))}
                  </ul>
                </div>
                <p className="text-sm text-muted-foreground">
                  Tem a certeza que deseja enviar este processo para balcões?
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleCancelBankMove}>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmBankMove} className="bg-amber-600 hover:bg-amber-700">
              Confirmar Envio
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default KanbanBoard;
