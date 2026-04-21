/**
 * MyClientsPage — Página de clientes atribuídos ao utilizador actual.
 *
 * PORQUÊ: Cada consultor/mediador precisa de uma vista filtrada dos seus próprios clientes,
 * sem ver os de outros utilizadores. Lista apenas clientes associados ao utilizador autenticado.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { TableSkeleton } from "../components/ui/skeletons";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { getMyClients, getWorkflowStatuses } from "../services/api";
import {
  Search, Eye, CheckCircle2, AlertTriangle, FileText, 
  Clock, Users, Building2, Phone, Mail, Calendar, Filter, X, Plus, ArrowUpDown
} from "lucide-react";
import { CreateClientModal } from "../components/kanban";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

/**
 * Calcula a cor de texto (preto ou branco) com base na luminosidade da cor de fundo.
 */
const getContrastColor = (bgColor) => {
  if (!bgColor) return '#ffffff';
  const namedColors = {
    yellow: '#EAB308', orange: '#F97316', blue: '#3B82F6',
    green: '#22C55E', red: '#EF4444', purple: '#A855F7', gray: '#6B7280',
  };
  let hex = namedColors[bgColor?.toLowerCase()] || bgColor;
  if (!hex.startsWith('#')) return '#ffffff';
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? '#1a1a1a' : '#ffffff';
};

const MyClientsPage = () => {
  const [clients, setClients] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  // Sync filters with URL
  const searchTerm = searchParams.get("search") || "";
  const statusFilter = searchParams.get("status") || "all";
  const showInactive = searchParams.get("show_inactive") === "true";
  const sortField = searchParams.get("sort") || "updated_at";
  const sortOrder = searchParams.get("order") || "desc";

  const updateParam = (key, value) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value && value !== "all") {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      return next;
    }, { replace: true });
  };

  const setSearchTerm = (value) => updateParam("search", value);
  const setStatusFilter = (value) => updateParam("status", value);
  const setShowInactive = (value) => updateParam("show_inactive", value ? "true" : "");
  const setSortField = (v) => updateParam("sort", v);
  const setSortOrder = (v) => updateParam("order", v);

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateSuccess = useCallback(() => {
    setShowCreateModal(false);
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [clientsRes, statusesRes] = await Promise.all([
        getMyClients(),
        getWorkflowStatuses()
      ]);
      
      setClients(clientsRes.data.clients || []);
      setWorkflowStatuses(statusesRes.data || []);
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast.error("Erro ao carregar lista de clientes");
    } finally {
      setLoading(false);
    }
  };

  // Status terminais que são excluídos por padrão
  const TERMINAL_STATUSES = ["concluido", "concluidos", "arquivo", "perdido", "desistencia", "desistencias", "cancelado", "eliminado", "eliminados", "inativo"];

  const filteredClients = useMemo(() => {
    const normalizedSearch = searchTerm
      ? searchTerm.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
      : "";

    let result = clients.filter((client) => {
      // Excluir status terminais por padrão (a menos que o toggle esteja ativo)
      if (!showInactive && TERMINAL_STATUSES.includes(client.status)) {
        return false;
      }

      const matchesSearch = !normalizedSearch || 
        client.client_name?.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().includes(normalizedSearch) ||
        client.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        client.process_number?.toString().includes(searchTerm);
      
      const matchesStatus = statusFilter === "all" || client.status === statusFilter;
      
      return matchesSearch && matchesStatus;
    });

    // Aplicar ordenação
    result.sort((a, b) => {
      let aVal, bVal;

      if (sortField === "client_name") {
        aVal = (a.client_name || "").toLowerCase();
        bVal = (b.client_name || "").toLowerCase();
      } else if (sortField === "status") {
        aVal = (a.status_label || a.status || "").toLowerCase();
        bVal = (b.status_label || b.status || "").toLowerCase();
      } else {
        // Data fields: updated_at, created_at, etc.
        aVal = new Date(a[sortField] || 0).getTime();
        bVal = new Date(b[sortField] || 0).getTime();
      }

      if (sortOrder === "asc") {
        return aVal > bVal ? 1 : -1;
      }
      return aVal < bVal ? 1 : -1;
    });

    return result;
  }, [clients, searchTerm, statusFilter, showInactive, sortField, sortOrder]);

  const getPriorityColor = (priority) => {
    switch (priority) {
      case "high": return "bg-red-500";
      case "medium": return "bg-yellow-500";
      default: return "bg-blue-500";
    }
  };

  const getActionIcon = (type) => {
    switch (type) {
      case "task": return <CheckCircle2 className="w-3 h-3" />;
      case "document": return <FileText className="w-3 h-3" />;
      default: return <AlertTriangle className="w-3 h-3" />;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "-";
    try {
      return format(parseISO(dateString), "dd MMM yyyy", { locale: pt });
    } catch {
      return dateString;
    }
  };

  // Estatísticas rápidas
  const stats = useMemo(() => {
    const activeClients = clients.filter(c => !TERMINAL_STATUSES.includes(c.status));
    const total = activeClients.length;
    const withPendingTasks = activeClients.filter(c => c.pending_count > 0).length;
    const withProperty = activeClients.filter(c => c.has_property).length;
    
    return { total, withPendingTasks, withProperty };
  }, [clients]);

  if (loading) {
    return (
      <DashboardLayout title="Os Meus Clientes">
        <div className="space-y-6" data-testid="loading-spinner">
          <div className="h-8 w-48 bg-muted animate-pulse rounded" />
          <TableSkeleton rows={8} columns={5} />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Os Meus Clientes">
      <div className="space-y-6" data-testid="my-clients-page">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Os Meus Clientes</h1>
            <p className="text-gray-500 text-sm mt-1">
              Clientes atribuídos ao meu perfil
            </p>
          </div>
          <Button
            onClick={() => setShowCreateModal(true)}
            className="gap-2"
            data-testid="btn-novo-cliente"
          >
            <Plus className="h-4 w-4" />
            Novo Cliente
          </Button>
        </div>

        {/* Estatísticas rápidas */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card data-testid="stat-total">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <Users className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{stats.total}</p>
                  <p className="text-sm text-gray-500">Total de Clientes</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card data-testid="stat-pending">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-100 rounded-lg">
                  <Clock className="w-5 h-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{stats.withPendingTasks}</p>
                  <p className="text-sm text-gray-500">Com Tarefas Pendentes</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card data-testid="stat-property">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 rounded-lg">
                  <Building2 className="w-5 h-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{stats.withProperty}</p>
                  <p className="text-sm text-gray-500">Com Imóvel Associado</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filtros */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                <Input
                  placeholder="Pesquisar por nome, email ou nº processo..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                  data-testid="search-input"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-full md:w-[200px]" data-testid="status-filter">
                  <SelectValue placeholder="Filtrar por fase" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas as fases</SelectItem>
                  {workflowStatuses.map((status) => (
                    <SelectItem key={status.name} value={status.name}>
                      {status.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* Ordenação */}
              <Select value={`${sortField}_${sortOrder}`} onValueChange={(v) => {
                const lastIdx = v.lastIndexOf('_');
                setSortField(v.substring(0, lastIdx));
                setSortOrder(v.substring(lastIdx + 1));
              }}>
                <SelectTrigger className="w-full md:w-[155px]">
                  <ArrowUpDown className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Ordenar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="updated_at_desc">Mais Recentes</SelectItem>
                  <SelectItem value="updated_at_asc">Mais Antigos</SelectItem>
                  <SelectItem value="client_name_asc">Nome (A-Z)</SelectItem>
                  <SelectItem value="client_name_desc">Nome (Z-A)</SelectItem>
                </SelectContent>
              </Select>
              {/* Toggle: Mostrar inativos */}
              <Button
                variant={showInactive ? "default" : "outline"}
                size="sm"
                className={`h-10 w-full md:w-auto gap-2 ${showInactive ? "bg-amber-500 hover:bg-amber-600 text-white" : ""}`}
                onClick={() => setShowInactive(!showInactive)}
                data-testid="toggle-inactive"
              >
                {showInactive ? <X className="w-4 h-4" /> : <Filter className="w-4 h-4" />}
                {showInactive ? "Ocultar Concluídos" : "Mostrar Concluídos"}
              </Button>
            </div>
            {showInactive && (
              <p className="text-xs text-amber-600 mt-2 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                A mostrar todos os processos, incluindo concluídos e desistências
              </p>
            )}
          </CardContent>
        </Card>

        {/* Tabela de Clientes */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Lista de Clientes ({filteredClients.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {filteredClients.length === 0 ? (
              <div className="text-center py-12 text-gray-500" data-testid="empty-state">
                <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Nenhum cliente encontrado</p>
                {searchTerm && (
                  <p className="text-sm mt-2">
                    Tente ajustar os filtros de pesquisa
                  </p>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table data-testid="clients-table">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[50px]">Nº</TableHead>
                      <TableHead>Cliente</TableHead>
                      <TableHead>Fase</TableHead>
                      <TableHead>Ações Pendentes</TableHead>
                      <TableHead>Última Atualização</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredClients.map((client) => (
                      <TableRow 
                        key={client.id} 
                        className="cursor-pointer hover:bg-gray-50"
                        data-testid={`client-row-${client.id}`}
                        onClick={() => navigate(`/processo/${client.id}`)}
                      >
                        <TableCell className="font-medium text-gray-500">
                          #{client.process_number || "-"}
                        </TableCell>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="font-medium text-blue-600 hover:text-blue-800 hover:underline">{client.client_name}</div>
                            <div className="flex items-center gap-3 text-xs text-gray-500">
                              {client.client_email && (
                                <span className="flex items-center gap-1">
                                  <Mail className="w-3 h-3" />
                                  {client.client_email}
                                </span>
                              )}
                              {client.client_phone && (
                                <span className="flex items-center gap-1">
                                  <Phone className="w-3 h-3" />
                                  {client.client_phone}
                                </span>
                              )}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge 
                            style={{ 
                              backgroundColor: client.status_color || '#6B7280',
                              color: getContrastColor(client.status_color),
                              border: 'none',
                              fontSize: '11px'
                            }}
                          >
                            {client.status_label}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {client.pending_actions?.length > 0 ? (
                            <div className="space-y-1">
                              {client.pending_actions.slice(0, 3).map((action, idx) => (
                                <div 
                                  key={idx}
                                  className="flex items-center gap-2 text-xs"
                                >
                                  <span className={`w-2 h-2 rounded-full ${getPriorityColor(action.priority)}`} />
                                  {getActionIcon(action.type)}
                                  <span className="text-gray-700 truncate max-w-[200px]">
                                    {action.title}
                                  </span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-gray-400 text-sm flex items-center gap-1">
                              <CheckCircle2 className="w-4 h-4 text-green-500" />
                              Sem pendências
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-gray-500 text-sm">
                          <div className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(client.updated_at)}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/processo/${client.id}`);
                            }}
                            data-testid={`view-client-${client.id}`}
                          >
                            <Eye className="w-4 h-4 mr-1" />
                            Ver
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Create Client Modal */}
        <CreateClientModal
          open={showCreateModal}
          onOpenChange={setShowCreateModal}
          onSuccess={handleCreateSuccess}
        />
      </div>
    </DashboardLayout>
  );
};

export default MyClientsPage;

