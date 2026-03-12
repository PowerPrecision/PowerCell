import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
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
  Clock, Users, Building2, Phone, Mail, Calendar
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

const MyClientsPage = () => {
  const [clients, setClients] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const navigate = useNavigate();

  useEffect(() => {
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

  const filteredClients = useMemo(() => {
    return clients.filter((client) => {
      const matchesSearch = 
        client.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        client.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        client.process_number?.toString().includes(searchTerm);
      
      const matchesStatus = statusFilter === "all" || client.status === statusFilter;
      
      return matchesSearch && matchesStatus;
    });
  }, [clients, searchTerm, statusFilter]);

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
    const total = clients.length;
    const withPendingTasks = clients.filter(c => c.pending_count > 0).length;
    const withProperty = clients.filter(c => c.has_property).length;
    
    return { total, withPendingTasks, withProperty };
  }, [clients]);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64" data-testid="loading-spinner">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="my-clients-page">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Os Meus Clientes</h1>
            <p className="text-gray-500 text-sm mt-1">
              Visão geral dos processos atribuídos a si
            </p>
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
                      {status.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
                      >
                        <TableCell className="font-medium text-gray-500">
                          #{client.process_number || "-"}
                        </TableCell>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="font-medium">{client.client_name}</div>
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
                            variant="outline"
                            style={{ 
                              borderColor: client.status_color,
                              color: client.status_color 
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
                            onClick={() => navigate(`/processo/${client.id}`)}
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
      </div>
    </DashboardLayout>
  );
};

export default MyClientsPage;
