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
import { safeLabel } from "../components/dashboard/DashboardShared";
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
import { getMyClients, getWorkflowStatuses, getExportPermission } from "../services/api";
import {
  Search, Eye, CheckCircle2, AlertTriangle, FileText,
  Clock, Users, Building2, Phone, Mail, Calendar, Filter, X, Plus, ArrowUpDown, Download, Trash2
} from "lucide-react";
import CreateClientModal from "../components/kanban/CreateClientModal";
// PACOTE CP — ClientDetailsModal reutilizável
import ClientDetailsModal from "../components/ClientDetailsModal";
import { toast } from "sonner";
import * as XLSX from 'xlsx';
import { pt } from "date-fns/locale";
import { safeFormat } from "../lib/utils";
import { useAuth } from "../contexts/AuthContext";
import { hasAnyRole } from "../utils/roleUtils";

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

/**
 * PACOTE BI: Bolinhas de notificação silenciosas (indicadores visuais).
 * Mesmo padrão visual do Kanban (KanbanCard.jsx) e do FilteredProcessList:
 * azul = mensagens não lidas, verde = novos documentos do portal.
 * Renderiza apenas se houver sinal positivo (sem ruído visual).
 */
const NotificationDots = ({ hasUnreadMessages, hasNewDocuments }) => {
  if (!hasUnreadMessages && !hasNewDocuments) return null;
  return (
    <span className="inline-flex items-center gap-1 ml-1.5 align-middle" data-testid="notification-dots">
      {hasUnreadMessages && (
        <span
          className="relative flex h-2.5 w-2.5"
          title="Mensagens não lidas do cliente"
          role="img"
          aria-label="Mensagens não lidas"
        >
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
        </span>
      )}
      {hasNewDocuments && (
        <span
          className="relative flex h-2.5 w-2.5"
          title="Novos documentos do cliente"
          role="img"
          aria-label="Novos documentos"
        >
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
        </span>
      )}
    </span>
  );
};

const MyClientsPage = () => {
  const { user } = useAuth();
  const [clients, setClients] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allowExcelExport, setAllowExcelExport] = useState(true);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showCreateModal, setShowCreateModal] = useState(false);
  // PACOTE CP — estado para ClientDetailsModal
  const [clientDetailsModal, setClientDetailsModal] = useState({ open: false, clientId: null });
  
  // Admin/CEO sempre podem exportar
  const canExportExcel = allowExcelExport || hasAnyRole(user, ['admin', 'ceo']);
  
  // Sync filters with URL
  const searchTerm = searchParams.get("search") || "";
  const statusFilter = searchParams.get("status") || "all";
  const showInactive = searchParams.get("show_inactive") === "true";
  const showDeleted = searchParams.get("view_mode") === "deleted";
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
  const setShowDeleted = (value) => updateParam("view_mode", value ? "deleted" : "");
  const setSortField = (v) => updateParam("sort", v);
  const setSortOrder = (v) => updateParam("order", v);

  useEffect(() => {
    fetchData();
    checkExportPermission();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInactive, showDeleted]);

  const checkExportPermission = async () => {
    try {
      const res = await getExportPermission();
      setAllowExcelExport(res.data.allow_excel_export !== false);
    } catch {
      // Em caso de erro, manter default (true)
    }
  };

  const handleCreateSuccess = useCallback(() => {
    setShowCreateModal(false);
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      // Passar show_inactive ao backend para que os processos terminais
      // (concluídos/desistências) também sejam retornados quando o toggle
      // "Mostrar Concluídos" está ativo. Sem isto, o cliente cujo único
      // processo ficou terminal desaparece da lista mesmo com o toggle on.
      const [clientsRes, statusesRes] = await Promise.all([
        getMyClients({
          show_inactive: showInactive ? "true" : "false",
          ...(showDeleted ? { view_mode: "deleted" } : {}),
        }),
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
      // Excluir status terminais por padrão (a menos que o toggle esteja ativo).
      // PACOTE CW: quando showDeleted=true, o backend já retorna apenas
      // eliminados — não aplicar o filtro terminal local.
      if (!showInactive && !showDeleted && TERMINAL_STATUSES.includes(client.status)) {
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
        // Use Infinity/-Infinity for null dates to sort them to the end, avoiding 01/01/1970 epoch
        const getDateVal = (item, field) => {
          const val = item[field];
          if (!val) return sortOrder === "asc" ? Infinity : -Infinity;
          const parsed = new Date(val);
          return isNaN(parsed.getTime()) ? (sortOrder === "asc" ? Infinity : -Infinity) : parsed.getTime();
        };
        aVal = getDateVal(a, sortField);
        bVal = getDateVal(b, sortField);
      }

      if (sortOrder === "asc") {
        return aVal > bVal ? 1 : -1;
      }
      return aVal < bVal ? 1 : -1;
    });

    return result;
  }, [clients, searchTerm, statusFilter, showInactive, showDeleted, sortField, sortOrder]);

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

  const handleExportExcel = () => {
    if (filteredClients.length === 0) {
      toast.error('Nenhum cliente para exportar');
      return;
    }
    try {
      const rows = filteredClients.map(c => ({
        'Processo': c.process_number || '',
        'Nome': c.client_name || '',
        'NIF': c.client_nif || c.dados_pessoais?.nif || '',
        'Email': c.client_email || c.contacto?.email || '',
        'Telefone': c.client_phone || c.contacto?.telefone || '',
        'Estado Civil': c.dados_pessoais?.estado_civil || '',
        'Profissão': c.dados_pessoais?.profissao || '',
        'Nacionalidade': c.dados_pessoais?.nacionalidade || '',
        'Morada Completa': c.dados_pessoais?.morada_fiscal || c.morada || '',
        'Código Postal': c.dados_pessoais?.codigo_postal || c.cod_postal || '',
        'Localidade': c.dados_pessoais?.localidade || c.localidade || '',
        'Nome Titular 2': c.titular2_data?.name || c.titular2_name || '',
        'NIF Titular 2': c.titular2_data?.nif || c.titular2_nif || '',
        'Email Titular 2': c.titular2_data?.email || c.titular2_email || '',
        'Telefone Titular 2': c.titular2_data?.phone || c.titular2_phone || '',
        'Fonte': c.fonte || '',
        'Fase': c.status_label || (c.status || '').replace(/_/g, ' '),
        'Valor Imóvel': c.real_estate_data?.valor_imovel || c.property_value || '',
        'Data de Registo': c.created_at || '',
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      ws['!cols'] = [
        { wch: 10 }, // Processo
        { wch: 30 }, // Nome
        { wch: 12 }, // NIF
        { wch: 30 }, // Email
        { wch: 15 }, // Telefone
        { wch: 14 }, // Estado Civil
        { wch: 20 }, // Profissão
        { wch: 16 }, // Nacionalidade
        { wch: 35 }, // Morada Completa
        { wch: 10 }, // Código Postal
        { wch: 18 }, // Localidade
        { wch: 30 }, // Nome Titular 2
        { wch: 12 }, // NIF Titular 2
        { wch: 30 }, // Email Titular 2
        { wch: 15 }, // Telefone Titular 2
        { wch: 14 }, // Fonte
        { wch: 18 }, // Fase
        { wch: 14 }, // Valor Imóvel
        { wch: 18 }, // Data de Registo
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Clientes');
      XLSX.writeFile(wb, 'meus_clientes_powercell_export.xlsx');
      toast.success(`${rows.length} clientes exportados com sucesso!`);
    } catch (err) {
      console.error('Erro ao exportar Excel:', err);
      toast.error('Erro ao exportar Excel');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "-";
    return safeFormat(dateString, "dd MMM yyyy", { locale: pt });
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
          <div className="flex items-center gap-2">
            {canExportExcel && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportExcel}
                className="gap-2"
                disabled={filteredClients.length === 0}
              >
                <Download className="h-4 w-4" />
                Exportar Excel
              </Button>
            )}
            <Button
              onClick={() => setShowCreateModal(true)}
              className="gap-2"
              data-testid="btn-novo-cliente"
            >
              <Plus className="h-4 w-4" />
              Novo Cliente
            </Button>
          </div>
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
                      {safeLabel(status.label)}
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
              {/* PACOTE CW — Toggle: Mostrar Eliminados (view_mode=deleted) */}
              <Button
                variant={showDeleted ? "default" : "outline"}
                size="sm"
                className={`h-10 w-full md:w-auto gap-2 ${showDeleted ? "bg-gray-700 hover:bg-gray-800 text-white" : ""}`}
                onClick={() => setShowDeleted(!showDeleted)}
                data-testid="toggle-deleted"
              >
                {showDeleted ? <X className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
                {showDeleted ? "Ocultar Eliminados" : "Mostrar Eliminados"}
              </Button>
            </div>
            {showInactive && (
              <p className="text-xs text-amber-600 mt-2 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                A mostrar todos os processos, incluindo concluídos e desistências
              </p>
            )}
            {showDeleted && (
              <p className="text-xs text-gray-600 mt-2 flex items-center gap-1">
                <Trash2 className="w-3 h-3" />
                A mostrar apenas processos eliminados (recuperação administrativa)
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
                      {/* PACOTE CG — coluna Notas com latest_activity_note */}
                      <TableHead className="min-w-[140px] max-w-[220px]">Notas</TableHead>
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
                        onClick={() => navigate(`/cliente/${client.client_id || client.id}`)}
                      >
                        <TableCell className="font-medium text-gray-500">
                          #{client.process_number || "-"}
                        </TableCell>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span
                                className="cursor-pointer text-primary hover:underline"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (client.client_id || client.id) {
                                    setClientDetailsModal({ open: true, clientId: client.client_id || client.id });
                                  }
                                }}
                              >
                                {client.client_name}
                                {client.has_unread_messages && <span className="w-2 h-2 rounded-full bg-blue-500 inline-block ml-2" title="Nova Mensagem"></span>}
                                {client.has_new_documents && <span className="w-2 h-2 rounded-full bg-green-500 inline-block ml-2" title="Novo Ficheiro"></span>}
                              </span>
                              {TERMINAL_STATUSES.includes(client.status) && (
                                <Badge variant="outline" className="text-amber-700 border-amber-300 bg-amber-50 text-[10px]">
                                  {client.status_label || "Inativo"}
                                </Badge>
                              )}
                            </div>
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
                        {/* PACOTE CZ — coluna Notas: lê a atividade mais recente PRIMEIRO (não client.notes estático) */}
                        <TableCell className="min-w-[140px] max-w-[220px]">
                          {(() => {
                            const noteText = client.latest_activity_preview || client.latest_activity_note || client.latest_note || "";
                            if (noteText) {
                              return (
                                <div className="line-clamp-2 text-sm text-gray-500" title={noteText}>
                                  {noteText.length > 60 ? noteText.substring(0, 60) + '…' : noteText}
                                </div>
                              );
                            }
                            return <span className="text-xs text-gray-400">Sem notas recentes</span>;
                          })()}
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
                              navigate(`/cliente/${client.client_id || client.id}`);
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

      {/* PACOTE CP — ClientDetailsModal reutilizável */}
      <ClientDetailsModal
        open={clientDetailsModal.open}
        clientId={clientDetailsModal.clientId}
        onClose={() => setClientDetailsModal({ open: false, clientId: null })}
        onNavigateToProcess={(pid) => navigate(`/process/${pid}`)}
      />
    </DashboardLayout>
  );
};

export default MyClientsPage;

