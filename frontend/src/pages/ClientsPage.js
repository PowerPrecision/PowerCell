/**
 * ClientsPage — Página de gestão de clientes do CRM PowerCell.
 *
 * PORQUÊ: Centraliza a listagem, pesquisa e gestão de todos os clientes. Permite ao admin e
 * consultores visualizar dados de contacto, NIF, e número de processos associados.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { toast } from "sonner";
import {
  Users,
  Plus,
  Search,
  MoreHorizontal,
  FileText,
  Phone,
  Mail,
  Hash,
  Building2,
  UserPlus,
  Eye,
  Trash2,
  Link2,
  RefreshCw,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Filter,
  CheckCircle,
  XCircle,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { TableSkeleton, StatsCardSkeleton } from "../components/ui/skeletons";
import SmartClientSearch, { PROCESS_TYPE_LABELS } from "../components/SmartClientSearch";

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Calcula a cor de texto (preto ou branco) com base na luminosidade da cor de fundo.
 * Garante contraste legível independentemente da cor do badge.
 */
const getContrastColor = (bgColor) => {
  if (!bgColor) return '#ffffff';

  // Mapeamento de nomes de cor para hex
  const namedColors = {
    yellow: '#EAB308',
    orange: '#F97316',
    blue: '#3B82F6',
    green: '#22C55E',
    red: '#EF4444',
    purple: '#A855F7',
    gray: '#6B7280',
    grey: '#6B7280',
  };

  let hex = namedColors[bgColor?.toLowerCase()] || bgColor;
  if (!hex.startsWith('#')) return '#ffffff';

  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);

  // Fórmula de luminosidade relativa (WCAG)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? '#1a1a1a' : '#ffffff';
};

export default function ClientsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [clients, setClients] = useState([]);
  const [filteredClients, setFilteredClients] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Sync filters with URL search params
  const searchTerm = searchParams.get("search") || "";
  const sortField = searchParams.get("sort") || "created_at";
  const sortOrder = searchParams.get("order") || "desc";
  const statusFilter = searchParams.get("status") || "active";
  const phaseFilter = searchParams.get("phase") || "all";
  const assignmentFilter = searchParams.get("assignment") || "all";
  const indexacaoFilter = searchParams.get("indexacao") || "all";
  
  const updateParam = (key, value) => {
    setSearchParams(prev => {
      if (value && value !== "all" && value !== "created_at_desc") {
        prev.set(key, value);
      } else {
        prev.delete(key);
      }
      return prev;
    }, { replace: true });
  };
  
  const setSearchTerm = (v) => updateParam("search", v);
  const setStatusFilter = (v) => updateParam("status", v);
  const setPhaseFilter = (v) => updateParam("phase", v);
  const setAssignmentFilter = (v) => updateParam("assignment", v);
  const setIndexacaoFilter = (v) => updateParam("indexacao", v);
  const setSortField = (v) => updateParam("sort", v);
  const setSortOrder = (v) => updateParam("order", v);
  
  const [availablePhases, setAvailablePhases] = useState([]); // Lista de fases disponíveis
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showProcessDialog, setShowProcessDialog] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);
  const [newClient, setNewClient] = useState({
    nome: "",
    email: "",
    telefone: "",
    nif: "",
  });
  const [newProcessType, setNewProcessType] = useState("credito_habitacao");
  
  // Verificar se pode eliminar clientes (apenas admin, ceo, diretor, administrativo)
  const canDeleteClients = ["admin", "ceo", "diretor", "administrativo"].includes(user?.role);
  
  // Verificar se pode criar processos - baseado em permissões
  const userActions = user?.permissions?.actions || [];
  const canCreateProcess = userActions.length > 0 
    ? userActions.includes("create_process")
    : user?.role !== "indexacao";
  
  // Verificar se pode criar clientes - baseado em permissões
  const canCreateClients = userActions.length > 0 
    ? userActions.includes("create_client")
    : true; // Por defeito todos podem criar

  const fetchClients = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const params = new URLSearchParams();
      params.append("show_all", "true"); // Mostrar todos os clientes da empresa
      params.append("limit", "500"); // Aumentar limite para ver todos
      if (searchTerm) params.append("search", searchTerm);
      // Filtro por processos activos
      if (statusFilter === "active") params.append("has_active_process", "true");
      if (statusFilter === "inactive") params.append("has_active_process", "false");
      // Filtro por fase
      if (phaseFilter && phaseFilter !== "all") params.append("status_filter", phaseFilter);
      // Filtro por atribuição
      if (assignmentFilter && assignmentFilter !== "all") params.append("assignment_filter", assignmentFilter);
      // Filtro por indexação
      if (indexacaoFilter && indexacaoFilter !== "all") params.append("indexacao_filter", indexacaoFilter);

      const response = await fetch(`${API_URL}/api/clients?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setClients(data.clients || []);
        setAvailablePhases(data.available_statuses || []);
      }
    } catch (error) {
      console.error("Erro ao carregar clientes:", error);
      toast.error("Erro ao carregar clientes");
    } finally {
      setLoading(false);
    }
  }, [searchTerm, statusFilter, phaseFilter, assignmentFilter, indexacaoFilter]);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  // Aplicar filtros e ordenação
  useEffect(() => {
    let result = [...clients];
    
    // Ordenar
    result.sort((a, b) => {
      let aVal, bVal;

      if (sortField === "contacto") {
        aVal = (a.contacto?.email || a.contacto?.telefone || "").toLowerCase();
        bVal = (b.contacto?.email || b.contacto?.telefone || "").toLowerCase();
      } else if (sortField === "nif") {
        aVal = a.dados_pessoais?.nif || "";
        bVal = b.dados_pessoais?.nif || "";
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      } else if (sortField === "fase") {
        aVal = (a.fase_principal?.status_label || "").toLowerCase();
        bVal = (b.fase_principal?.status_label || "").toLowerCase();
      } else {
        aVal = a[sortField];
        bVal = b[sortField];
      }
      
      // Handle dates
      if (sortField === "created_at" || sortField === "updated_at") {
        aVal = new Date(aVal || 0).getTime();
        bVal = new Date(bVal || 0).getTime();
      }
      
      // Handle strings
      if (typeof aVal === "string") {
        aVal = aVal.toLowerCase();
        bVal = (bVal || "").toLowerCase();
      }
      
      // Handle numbers
      if (sortField === "process_count") {
        aVal = aVal || 0;
        bVal = bVal || 0;
      }
      
      if (sortOrder === "asc") {
        return aVal > bVal ? 1 : -1;
      }
      return aVal < bVal ? 1 : -1;
    });
    
    setFilteredClients(result);
  }, [clients, sortField, sortOrder]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("asc");
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
    return sortOrder === "asc" 
      ? <ArrowUp className="h-3 w-3 ml-1" />
      : <ArrowDown className="h-3 w-3 ml-1" />;
  };

  const handleCreateClient = async () => {
    // Validação do nome (obrigatório)
    if (!newClient.nome.trim()) {
      toast.error("Nome é obrigatório");
      return;
    }

    // Validação do NIF (opcional, mas se preenchido deve ter 9 dígitos)
    const nifClean = newClient.nif ? newClient.nif.replace(/[^\d]/g, '') : '';
    if (newClient.nif && nifClean.length !== 9) {
      toast.error("NIF deve ter exatamente 9 dígitos");
      return;
    }

    try {
      const token = localStorage.getItem("token");
      
      // Construir payload apenas com campos preenchidos
      const payload = { nome: newClient.nome.trim() };
      if (newClient.email?.trim()) payload.email = newClient.email.trim();
      if (newClient.telefone?.trim()) payload.telefone = newClient.telefone.trim();
      if (nifClean) payload.nif = nifClean;
      
      const response = await fetch(`${API_URL}/api/clients`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        toast.success("Cliente criado com sucesso");
        setShowCreateDialog(false);
        setNewClient({ nome: "", email: "", telefone: "", nif: "" });
        fetchClients();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao criar cliente");
      }
    } catch (error) {
      console.error("Erro ao criar cliente:", error);
      toast.error("Erro ao criar cliente");
    }
  };

  const handleCreateProcess = async () => {
    if (!selectedClient) return;

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(
        `${API_URL}/api/clients/${selectedClient.id}/create-process?process_type=${newProcessType}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        toast.success(`Processo #${data.process_number} criado`);
        setShowProcessDialog(false);
        setSelectedClient(null);
        fetchClients();
        // Navegar para o novo processo
        navigate(`/process/${data.process_id}`);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao criar processo");
      }
    } catch (error) {
      console.error("Erro ao criar processo:", error);
      toast.error("Erro ao criar processo");
    }
  };

  const handleDeleteClient = async (clientId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este cliente?")) {
      return;
    }

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/clients/${clientId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        toast.success("Cliente eliminado");
        fetchClients();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao eliminar cliente");
      }
    } catch (error) {
      console.error("Erro ao eliminar cliente:", error);
      toast.error("Erro ao eliminar cliente");
    }
  };

  const openCreateProcessDialog = (client) => {
    setSelectedClient(client);
    setShowProcessDialog(true);
  };

  // Abrir dialog para criar novo cliente/processo
  const handleCreateNewProcess = () => {
    setShowCreateDialog(true);
  };

  return (
    <DashboardLayout>
      <div className="space-y-4 md:space-y-6" data-testid="clients-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              Gestão de Processos
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Gerir processos de compra e financiamento
            </p>
          </div>
        </div>

        {/* Search, Filters & Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="md:col-span-2">
            <CardContent className="pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative w-full sm:flex-1 sm:min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Pesquisar por nome, email ou NIF..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                    data-testid="search-clients-input"
                  />
                </div>
                <div className="flex flex-wrap gap-2 w-full sm:w-auto">
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-full sm:w-[150px]" data-testid="status-filter">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4" />
                        Todos os Clientes
                      </div>
                    </SelectItem>
                    <SelectItem value="active">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-green-600" />
                        Clientes Ativos
                      </div>
                    </SelectItem>
                    <SelectItem value="inactive">
                      <div className="flex items-center gap-2">
                        <XCircle className="h-4 w-4 text-gray-400" />
                        Clientes Inativos
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Select value={phaseFilter} onValueChange={setPhaseFilter}>
                  <SelectTrigger className="w-full sm:w-[150px]" data-testid="phase-filter">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Fase" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas as Fases</SelectItem>
                    {availablePhases.map((phase) => (
                      <SelectItem key={phase.name} value={phase.name}>
                        {phase.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={assignmentFilter} onValueChange={setAssignmentFilter}>
                  <SelectTrigger className="w-full sm:w-[150px]" data-testid="assignment-filter">
                    <Users className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Atribuição" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="both">Consultor + Intermediário</SelectItem>
                    <SelectItem value="consultor">Apenas Consultor</SelectItem>
                    <SelectItem value="intermediario">Apenas Intermediário</SelectItem>
                    <SelectItem value="none">Sem Atribuição</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={indexacaoFilter} onValueChange={setIndexacaoFilter}>
                  <SelectTrigger className="w-full sm:w-[150px]" data-testid="indexacao-filter">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Indexação" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="assigned">Com Indexação</SelectItem>
                    <SelectItem value="unassigned">Sem Indexação</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={`${sortField}_${sortOrder}`} onValueChange={(v) => {
                  const [field, order] = v.split('_');
                  setSortField(field);
                  setSortOrder(order);
                }}>
                  <SelectTrigger className="w-full sm:w-[150px]" data-testid="sort-field">
                    <ArrowUpDown className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Ordenar" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="created_at_desc">Mais Recentes</SelectItem>
                    <SelectItem value="created_at_asc">Mais Antigos</SelectItem>
                    <SelectItem value="nome_asc">Nome (A-Z)</SelectItem>
                    <SelectItem value="nome_desc">Nome (Z-A)</SelectItem>
                    <SelectItem value="process_count_desc">Mais Processos</SelectItem>
                    <SelectItem value="process_count_asc">Menos Processos</SelectItem>
                  </SelectContent>
                </Select>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <Users className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{clients.length}</p>
                  <p className="text-xs text-muted-foreground">Total Clientes</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <FileText className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">
                    {clients.filter((c) => c.active_processes_count > 0).length}
                  </p>
                  <p className="text-xs text-muted-foreground">Com Processos Activos</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Clients Table */}
        <Card>
          <CardHeader className="pb-3 sticky top-0 z-10 bg-card border-b">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Lista de Clientes</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={fetchClients}
                className="gap-2"
              >
                <RefreshCw className="h-4 w-4" />
                Actualizar
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-6">
                <TableSkeleton rows={8} columns={5} />
              </div>
            ) : filteredClients.length === 0 ? (
              <div className="text-center py-12">
                <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  {clients.length === 0 ? "Nenhum cliente encontrado" : "Nenhum cliente corresponde aos filtros"}
                </p>
                {clients.length === 0 && canCreateClients && (
                  <Button
                    variant="outline"
                    className="mt-4"
                    onClick={() => setShowCreateDialog(true)}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Criar primeiro cliente
                  </Button>
                )}
              </div>
            ) : (
              <>
              {/* O9 - Mobile: Card view */}
              <div className="md:hidden space-y-3 p-3">
                {filteredClients.map((client, idx) => (
                  <div key={`mobile-${client.id}-${idx}`} className="border rounded-lg p-3 bg-card space-y-2" data-testid={`client-card-${client.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                          <span className="text-xs font-medium text-primary">
                            {client.nome?.charAt(0)?.toUpperCase() || "?"}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <button
                            className="font-medium text-sm text-left hover:text-primary truncate block max-w-full"
                            onClick={() => client.process_ids?.[0] && navigate(`/process/${client.process_ids[0]}`)}
                            disabled={!client.process_ids?.length}
                          >
                            {client.nome}
                          </button>
                          {client.contacto?.email && (
                            <p className="text-xs text-muted-foreground truncate">{client.contacto.email}</p>
                          )}
                        </div>
                      </div>
                      {client.fase_principal ? (
                        <Badge 
                          className="shrink-0 text-[10px]"
                          style={{ 
                            backgroundColor: client.fase_principal.status_color || '#6B7280',
                            color: getContrastColor(client.fase_principal.status_color),
                          }}
                        >
                          {client.fase_principal.status_label}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <div className="flex items-center gap-3">
                        {client.contacto?.telefone && (
                          <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{client.contacto.telefone}</span>
                        )}
                        {client.dados_pessoais?.nif && (
                          <span className="flex items-center gap-1 font-mono"><Hash className="h-3 w-3" />{client.dados_pessoais.nif}</span>
                        )}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => client.process_ids?.[0] && navigate(`/process/${client.process_ids[0]}`)}
                            disabled={!client.process_ids?.length}
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            Ver Ficha
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => openCreateProcessDialog(client)}
                          >
                            <Plus className="h-4 w-4 mr-2" />
                            Iniciar Novo Processo
                          </DropdownMenuItem>
                          {canDeleteClients && (
                            <DropdownMenuItem onClick={() => handleDeleteClient(client.id)} className="text-red-600">
                              <Trash2 className="h-4 w-4 mr-2" />
                              Eliminar
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                ))}
              </div>

              {/* O9 - Desktop: Table */}
              <div className="hidden md:block max-h-[calc(100vh-350px)] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-card">
                    <TableRow className="bg-muted/50">
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("nome")}
                      >
                        <span className="flex items-center">
                          Cliente
                          <SortIcon field="nome" />
                        </span>
                      </TableHead>
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("contacto")}
                      >
                        <span className="flex items-center">
                          Contacto
                          <SortIcon field="contacto" />
                        </span>
                      </TableHead>
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("nif")}
                      >
                        <span className="flex items-center">
                          NIF
                          <SortIcon field="nif" />
                        </span>
                      </TableHead>
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("fase")}
                      >
                        <span className="flex items-center">
                          Fase
                          <SortIcon field="fase" />
                        </span>
                      </TableHead>
                      <TableHead className="text-right">Acções</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                  {filteredClients.map((client, idx) => (
                    <TableRow key={`${client.id}-${idx}`} data-testid={`client-row-${client.id}`}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
                            <span className="text-sm font-medium text-primary">
                              {client.nome?.charAt(0)?.toUpperCase() || "?"}
                            </span>
                          </div>
                          <div>
                            <button
                              className="font-medium text-left hover:text-primary hover:underline transition-colors cursor-pointer"
                              onClick={() => client.process_ids?.[0] && navigate(`/process/${client.process_ids[0]}`)}
                              disabled={!client.process_ids?.length}
                              data-testid={`client-name-${client.id}`}
                            >
                              {client.nome}
                            </button>
                            {client.fonte && (
                              <Badge variant="outline" className="text-xs mt-1">
                                {client.fonte}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {client.contacto?.email && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Mail className="h-3 w-3" />
                              {client.contacto.email}
                            </div>
                          )}
                          {client.contacto?.telefone && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Phone className="h-3 w-3" />
                              {client.contacto.telefone}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {client.dados_pessoais?.nif ? (
                          <div className="flex items-center gap-1">
                            <Hash className="h-3 w-3 text-muted-foreground" />
                            <span className="font-mono text-sm">
                              {client.dados_pessoais.nif}
                            </span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-sm">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {client.fase_principal ? (
                          <div className="flex flex-col gap-1">
                            <Badge 
                              style={{ 
                                backgroundColor: client.fase_principal.status_color || '#6B7280',
                                color: getContrastColor(client.fase_principal.status_color),
                                fontSize: '11px'
                              }}
                            >
                              {client.fase_principal.status_label}
                            </Badge>
                            {!client.fase_principal.is_active && (
                              <span className="text-xs text-muted-foreground">(Inactivo)</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-sm">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              data-testid={`client-actions-${client.id}`}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() =>
                                client.process_ids?.[0] &&
                                navigate(`/process/${client.process_ids[0]}`)
                              }
                              disabled={!client.process_ids?.length}
                            >
                              <Eye className="h-4 w-4 mr-2" />
                              Ver Ficha
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => openCreateProcessDialog(client)}
                            >
                              <Plus className="h-4 w-4 mr-2" />
                              Iniciar Novo Processo
                            </DropdownMenuItem>
                            {canDeleteClients && (
                              <DropdownMenuItem
                                onClick={() => handleDeleteClient(client.id)}
                                className="text-red-600"
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Eliminar
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Create Client Dialog - só visível para quem pode criar clientes */}
        {canCreateClients && (
        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5" />
                Novo Cliente
              </DialogTitle>
              <DialogDescription>
                Preencha os dados para criar um novo cliente.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={(e) => { e.preventDefault(); handleCreateClient(); }} className="space-y-4 py-4">
              {/* Campo Nome - Obrigatório */}
              <div className="space-y-2">
                <Label htmlFor="nome">
                  Nome <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="nome"
                  value={newClient.nome}
                  onChange={(e) =>
                    setNewClient({ ...newClient, nome: e.target.value })
                  }
                  placeholder="Nome completo do cliente"
                  required
                  autoFocus
                  data-testid="new-client-name"
                />
              </div>
              
              {/* Email e Telefone - Opcionais */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-muted-foreground">
                    Email <span className="text-xs font-normal">(Opcional)</span>
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    value={newClient.email}
                    onChange={(e) =>
                      setNewClient({ ...newClient, email: e.target.value })
                    }
                    placeholder="email@exemplo.pt"
                    data-testid="new-client-email"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="telefone" className="text-muted-foreground">
                    Telefone <span className="text-xs font-normal">(Opcional)</span>
                  </Label>
                  <Input
                    id="telefone"
                    value={newClient.telefone}
                    onChange={(e) =>
                      setNewClient({ ...newClient, telefone: e.target.value })
                    }
                    placeholder="912 345 678"
                    data-testid="new-client-phone"
                  />
                </div>
              </div>
              
              {/* NIF - Opcional mas com validação */}
              <div className="space-y-2">
                <Label htmlFor="nif" className="text-muted-foreground">
                  NIF <span className="text-xs font-normal">(Opcional)</span>
                </Label>
                <Input
                  id="nif"
                  value={newClient.nif}
                  onChange={(e) => {
                    // Permitir apenas dígitos
                    const value = e.target.value.replace(/[^\d]/g, '');
                    setNewClient({ ...newClient, nif: value });
                  }}
                  placeholder="123456789"
                  maxLength={9}
                  data-testid="new-client-nif"
                />
                <p className="text-xs text-muted-foreground">
                  Se preenchido, deve conter exatamente 9 dígitos
                </p>
              </div>
            </form>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setShowCreateDialog(false)}
              >
                Cancelar
              </Button>
              <Button onClick={handleCreateClient} data-testid="submit-new-client">
                Criar Cliente
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        )}

        {/* Create Process Dialog */}
        {canCreateProcess && (
        <Dialog open={showProcessDialog} onOpenChange={(open) => {
          if (!open) { setSelectedClient(null); setNewProcessType("credito_habitacao"); }
          setShowProcessDialog(open);
        }}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                {selectedClient?.nome ? `Novo Processo para ${selectedClient.nome}` : "Novo Processo"}
              </DialogTitle>
              <DialogDescription className="sr-only">
                Criar um novo processo para o cliente selecionado.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {selectedClient && (
                <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <span className="text-xs font-medium text-primary">
                      {selectedClient.nome?.charAt(0)?.toUpperCase() || "?"}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm">{selectedClient.nome}</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {selectedClient.dados_pessoais?.nif && <span>NIF: {selectedClient.dados_pessoais.nif}</span>}
                      {selectedClient.contacto?.email && <span>· {selectedClient.contacto.email}</span>}
                    </div>
                  </div>
                </div>
              )}
              {!selectedClient && (
                <p className="text-sm text-muted-foreground">
                  Selecione um cliente na lista (menu "⋯" → "Iniciar Novo Processo") para criar um processo.
                </p>
              )}
              <div className="space-y-2">
                <Label>Tipo de Processo</Label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { value: "credito_habitacao", label: "Crédito Habitação" },
                    { value: "credito_pessoal", label: "Crédito Pessoal" },
                    { value: "credito_consolidado", label: "Crédito Consolidado" },
                    { value: "credito_automovel", label: "Crédito Automóvel" },
                    { value: "transferencia_credito", label: "Transferência" },
                    { value: "imobiliario", label: "Imobiliário" },
                  ].map((type) => (
                    <Button
                      key={type.value}
                      variant={
                        newProcessType === type.value ? "default" : "outline"
                      }
                      size="sm"
                      className="justify-start text-xs h-9"
                      onClick={() => setNewProcessType(type.value)}
                    >
                      <Building2 className="h-3.5 w-3.5 mr-1.5" />
                      {type.label}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setShowProcessDialog(false)}
              >
                Cancelar
              </Button>
              <Button
                onClick={handleCreateProcess}
                disabled={!selectedClient}
                data-testid="submit-new-process"
              >
                <Plus className="h-4 w-4 mr-2" />
                Criar Processo
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        )}
      </div>
    </DashboardLayout>
  );
}

