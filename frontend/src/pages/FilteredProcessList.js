/**
 * FilteredProcessList - Lista de Processos Filtrada
 * Página para mostrar processos filtrados por status/critério
 */
import { useState, useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { ScrollArea } from "../components/ui/scroll-area";
import { 
  ArrowLeft, Search, Eye, Loader2, Users, CheckCircle, 
  XCircle, Clock, TrendingUp, AlertTriangle 
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";
import { getProcesses, getWorkflowStatuses, getCalendarDeadlines } from "../services/api";

const filterConfig = {
  active: {
    title: "Processos Ativos",
    description: "Processos em curso (excluindo concluídos e desistências)",
    icon: TrendingUp,
    color: "text-blue-600",
    bgColor: "bg-blue-50",
    filter: (p) => !["concluidos", "desistencias"].includes(p.status)
  },
  concluded: {
    title: "Processos Concluídos",
    description: "Processos finalizados com sucesso",
    icon: CheckCircle,
    color: "text-emerald-600",
    bgColor: "bg-emerald-50",
    filter: (p) => p.status === "concluidos"
  },
  dropped: {
    title: "Desistências",
    description: "Processos cancelados ou desistidos",
    icon: XCircle,
    color: "text-red-600",
    bgColor: "bg-red-50",
    filter: (p) => p.status === "desistencias"
  },
  pending_deadlines: {
    title: "Prazos Pendentes",
    description: "Processos com prazos a aproximar-se ou vencidos",
    icon: Clock,
    color: "text-orange-600",
    bgColor: "bg-orange-50",
    filter: null, // Filtro especial via deadlines
    showDeadlineInfo: true
  },
  waiting: {
    title: "Clientes em Espera",
    description: "Processos no estado inicial de espera",
    icon: Users,
    color: "text-amber-600",
    bgColor: "bg-amber-50",
    filter: (p) => p.status === "clientes_espera"
  },
  waiting_long: {
    title: "Em Espera Há Muito Tempo",
    description: "Processos em espera há mais de 15 dias",
    icon: AlertTriangle,
    color: "text-red-600",
    bgColor: "bg-red-50",
    filter: (p) => {
      if (p.status !== "clientes_espera") return false;
      const created = new Date(p.created_at);
      const now = new Date();
      const days = Math.floor((now - created) / (1000 * 60 * 60 * 24));
      return days >= 15;
    }
  }
};

const FilteredProcessList = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const filterType = searchParams.get("filter") || "active";
  
  const [loading, setLoading] = useState(true);
  const [processes, setProcesses] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");

  const config = filterConfig[filterType] || filterConfig.active;
  const IconComponent = config.icon;

  useEffect(() => {
    fetchData();
  }, [filterType]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [processesRes, statusesRes, deadlinesRes] = await Promise.all([
        getProcesses(),
        getWorkflowStatuses(),
        getCalendarDeadlines()
      ]);
      setProcesses(processesRes.data);
      setWorkflowStatuses(statusesRes.data);
      setDeadlines(deadlinesRes.data);
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast.error("Erro ao carregar processos");
    } finally {
      setLoading(false);
    }
  };

  // Filtrar processos
  const getFilteredProcesses = () => {
    let filtered = processes;

    // Filtro especial para prazos pendentes
    if (filterType === "pending_deadlines") {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const upcomingDeadlines = deadlines.filter(d => {
        const deadlineDate = new Date(d.due_date);
        const daysUntil = Math.ceil((deadlineDate - today) / (1000 * 60 * 60 * 24));
        return daysUntil <= 7; // Próximos 7 dias ou vencidos
      });
      const processIds = [...new Set(upcomingDeadlines.map(d => d.process_id))];
      filtered = processes.filter(p => processIds.includes(p.id));
    } else if (config.filter) {
      filtered = processes.filter(config.filter);
    }

    // Filtro de pesquisa
    if (searchTerm.length >= 2) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(p =>
        p.client_name?.toLowerCase().includes(term) ||
        p.client_email?.toLowerCase().includes(term) ||
        p.client_phone?.includes(term)
      );
    }

    return filtered;
  };

  const filteredProcesses = getFilteredProcesses();

  const getStatusInfo = (statusName) => {
    const status = workflowStatuses.find(s => s.name === statusName);
    return status || { label: statusName, color: "gray" };
  };

  const getDeadlineInfo = (processId) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const processDeadlines = deadlines.filter(d => d.process_id === processId);
    if (processDeadlines.length === 0) return null;

    const upcoming = processDeadlines
      .map(d => ({
        ...d,
        daysUntil: Math.ceil((new Date(d.due_date) - today) / (1000 * 60 * 60 * 24))
      }))
      .filter(d => d.daysUntil <= 7)
      .sort((a, b) => a.daysUntil - b.daysUntil);

    return upcoming[0] || null;
  };

  const formatCurrency = (value) => {
    if (!value) return "-";
    return new Intl.NumberFormat('pt-PT', { 
      style: 'currency', 
      currency: 'EUR',
      maximumFractionDigits: 0 
    }).format(value);
  };

  if (loading) {
    return (
      <DashboardLayout title="Processos">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title={config.title}>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className={`p-3 rounded-lg ${config.bgColor}`}>
            <IconComponent className={`h-6 w-6 ${config.color}`} />
          </div>
          <div>
            <h1 className="text-2xl font-bold">{config.title}</h1>
            <p className="text-muted-foreground">{config.description}</p>
          </div>
          <Badge variant="secondary" className="ml-auto text-lg px-4 py-1">
            {filteredProcesses.length}
          </Badge>
        </div>

        {/* Search */}
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Pesquisar por nome, email ou telefone..."
            className="pl-10"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        {/* Lista */}
        <Card className="border-border">
          <CardContent className="p-0">
            <ScrollArea className="h-[600px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Contacto</TableHead>
                    <TableHead>Fase</TableHead>
                    <TableHead>Valor</TableHead>
                    {config.showDeadlineInfo && <TableHead>Prazo</TableHead>}
                    <TableHead>Data Criação</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredProcesses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={config.showDeadlineInfo ? 7 : 6} className="text-center py-12">
                        <div className="text-muted-foreground">
                          <IconComponent className="h-12 w-12 mx-auto mb-4 opacity-20" />
                          <p>Nenhum processo encontrado</p>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredProcesses.map((process) => {
                      const statusInfo = getStatusInfo(process.status);
                      const deadlineInfo = config.showDeadlineInfo ? getDeadlineInfo(process.id) : null;
                      
                      return (
                        <TableRow
                          key={process.id}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => navigate(`/process/${process.id}`)}
                        >
                          <TableCell>
                            <div>
                              <p className="font-medium">{process.client_name}</p>
                              {process.under_35 && (
                                <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700 mt-1">
                                  &lt;35 anos
                                </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm">
                              <p>{process.client_phone || "-"}</p>
                              <p className="text-muted-foreground text-xs truncate max-w-[150px]">
                                {process.client_email}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge 
                              variant="outline"
                              className={`bg-${statusInfo.color}-50 text-${statusInfo.color}-700 border-${statusInfo.color}-200`}
                            >
                              {statusInfo.label}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-medium">
                            {formatCurrency(process.property_value)}
                          </TableCell>
                          {config.showDeadlineInfo && (
                            <TableCell>
                              {deadlineInfo ? (
                                <div>
                                  <p className="text-sm font-medium truncate max-w-[150px]">
                                    {deadlineInfo.title}
                                  </p>
                                  <Badge 
                                    variant="outline"
                                    className={
                                      deadlineInfo.daysUntil <= 0 
                                        ? "bg-red-100 text-red-800 border-red-200" 
                                        : deadlineInfo.daysUntil <= 3 
                                        ? "bg-amber-100 text-amber-800 border-amber-200"
                                        : "bg-blue-100 text-blue-800 border-blue-200"
                                    }
                                  >
                                    {deadlineInfo.daysUntil <= 0 
                                      ? "Vencido" 
                                      : deadlineInfo.daysUntil === 1 
                                      ? "Amanhã" 
                                      : `${deadlineInfo.daysUntil} dias`}
                                  </Badge>
                                </div>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </TableCell>
                          )}
                          <TableCell className="text-sm text-muted-foreground">
                            {process.created_at 
                              ? format(parseISO(process.created_at), "dd/MM/yyyy", { locale: pt })
                              : "-"
                            }
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
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default FilteredProcessList;
