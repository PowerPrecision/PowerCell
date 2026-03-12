import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { 
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, 
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  FunnelChart, Funnel, LabelList
} from "recharts";
import { 
  TrendingUp, TrendingDown, Users, FileText, CheckCircle, 
  Clock, AlertCircle, Euro, Calendar, Target, Building, Trophy
} from "lucide-react";
import { getStats, getProcesses, getUsers } from "../services/api";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const StatisticsPage = () => {
  const { user, token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [processes, setProcesses] = useState([]);
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(user?.id);
  const [timeRange, setTimeRange] = useState("30");
  
  // Estado para estatísticas de leads
  const [leadsStats, setLeadsStats] = useState(null);
  const [conversionStats, setConversionStats] = useState(null);

  const canViewAllStats = user?.role === "admin" || user?.role === "ceo";

  useEffect(() => {
    fetchData();
  }, [selectedUser, timeRange]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statsRes, processesRes, usersRes] = await Promise.all([
        getStats(),
        getProcesses(),
        canViewAllStats ? getUsers() : Promise.resolve({ data: [] })
      ]);

      setStats(statsRes.data);
      setProcesses(processesRes.data);
      setUsers(usersRes.data);
      
      // Fetch estatísticas de leads
      await fetchLeadsStats();
    } catch (error) {
      toast.error("Erro ao carregar estatísticas");
    } finally {
      setLoading(false);
    }
  };

  const fetchLeadsStats = async () => {
    try {
      const [leadsRes, convRes] = await Promise.all([
        fetch(`${API_URL}/api/stats/leads`, {
          headers: { Authorization: `Bearer ${token}` }
        }),
        fetch(`${API_URL}/api/stats/conversion`, {
          headers: { Authorization: `Bearer ${token}` }
        })
      ]);
      
      if (leadsRes.ok) {
        const data = await leadsRes.json();
        setLeadsStats(data);
      }
      
      if (convRes.ok) {
        const data = await convRes.json();
        setConversionStats(data);
      }
    } catch (error) {
      console.error("Erro ao carregar estatísticas de leads:", error);
    }
  };

  // Filtrar processos baseado no utilizador selecionado
  const filteredProcesses = processes.filter(p => {
    if (!canViewAllStats || selectedUser === "all") return true;
    return p.assigned_consultor === selectedUser || p.assigned_intermediario === selectedUser;
  });

  // Calcular estatísticas personalizadas
  const totalProcessos = filteredProcesses.length;
  const processosAtivos = filteredProcesses.filter(p => !['concluidos', 'desistencias'].includes(p.status)).length;
  const processosConcluidos = filteredProcesses.filter(p => p.status === 'concluidos').length;
  const desistencias = filteredProcesses.filter(p => p.status === 'desistencias').length;
  
  const valorTotal = filteredProcesses.reduce((sum, p) => sum + (p.property_value || 0), 0);
  const valorMedio = totalProcessos > 0 ? valorTotal / totalProcessos : 0;
  
  const taxaSucesso = totalProcessos > 0 
    ? ((processosConcluidos / (processosConcluidos + desistencias)) * 100).toFixed(1)
    : 0;

  // Dados para gráficos
  const statusData = Object.entries(
    filteredProcesses.reduce((acc, p) => {
      acc[p.status] = (acc[p.status] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name, value }));

  const prioridadeData = [
    { name: 'Alta', value: filteredProcesses.filter(p => p.priority === 'high').length },
    { name: 'Média', value: filteredProcesses.filter(p => p.priority === 'medium').length },
    { name: 'Baixa', value: filteredProcesses.filter(p => p.priority === 'low').length },
  ].filter(d => d.value > 0);

  const valorPorFaseData = Object.entries(
    filteredProcesses.reduce((acc, p) => {
      if (!acc[p.status]) acc[p.status] = 0;
      acc[p.status] += p.property_value || 0;
      return acc;
    }, {})
  ).map(([name, value]) => ({ 
    name, 
    value: Math.round(value / 1000) // em milhares
  })).slice(0, 10);

  return (
    <DashboardLayout title="Estatísticas e Análise">
      <div className="space-y-6 p-6">
        {/* Filtros */}
        <div className="flex flex-wrap gap-4">
          {canViewAllStats && (
            <Select value={selectedUser} onValueChange={setSelectedUser}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Selecionar utilizador" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os Utilizadores</SelectItem>
                {users.map(u => (
                  <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Período" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Últimos 7 dias</SelectItem>
              <SelectItem value="30">Últimos 30 dias</SelectItem>
              <SelectItem value="90">Últimos 90 dias</SelectItem>
              <SelectItem value="365">Último ano</SelectItem>
              <SelectItem value="all">Todo o período</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* KPIs Principais */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Total de Processos</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{totalProcessos}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {processosAtivos} ativos
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Taxa de Sucesso</CardTitle>
              <Target className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{taxaSucesso}%</div>
              <p className="text-xs text-muted-foreground mt-1">
                {processosConcluidos} concluídos vs {desistencias} desistências
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Valor Total</CardTitle>
              <Euro className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                €{(valorTotal / 1000000).toFixed(1)}M
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Média: €{Math.round(valorMedio / 1000)}k
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Total de Leads</CardTitle>
              <Building className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{leadsStats?.total_leads || 0}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {leadsStats?.leads_by_status?.novo || 0} novos
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Gráficos */}
        <Tabs defaultValue="status" className="space-y-4">
          <TabsList>
            <TabsTrigger value="status">Por Fase</TabsTrigger>
            <TabsTrigger value="priority">Por Prioridade</TabsTrigger>
            <TabsTrigger value="value">Valor por Fase</TabsTrigger>
            <TabsTrigger value="leads">Funil de Leads</TabsTrigger>
            <TabsTrigger value="ranking">Ranking Consultores</TabsTrigger>
          </TabsList>

          <TabsContent value="status" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Distribuição por Fase</CardTitle>
                <CardDescription>
                  Número de processos em cada fase do workflow
                </CardDescription>
              </CardHeader>
              <CardContent className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={statusData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="value" fill="#3b82f6" name="Processos" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="priority" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Distribuição por Prioridade</CardTitle>
                <CardDescription>
                  Processos organizados por nível de prioridade
                </CardDescription>
              </CardHeader>
              <CardContent className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={prioridadeData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={(entry) => `${entry.name}: ${entry.value}`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {prioridadeData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="value" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Valor por Fase (em milhares €)</CardTitle>
                <CardDescription>
                  Valor total de imóveis em cada fase
                </CardDescription>
              </CardHeader>
              <CardContent className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={valorPorFaseData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="value" fill="#10b981" name="Valor (k€)" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="leads" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              {/* Funil de Vendas */}
              <Card>
                <CardHeader>
                  <CardTitle>Funil de Vendas (Leads)</CardTitle>
                  <CardDescription>
                    Leads em cada fase do processo de venda
                  </CardDescription>
                </CardHeader>
                <CardContent className="h-80">
                  {leadsStats?.funnel_data && (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={leadsStats.funnel_data} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" />
                        <YAxis dataKey="stage" type="category" width={100} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#3b82f6" name="Leads">
                          {leadsStats.funnel_data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              {/* Origem das Leads */}
              <Card>
                <CardHeader>
                  <CardTitle>Origem das Leads</CardTitle>
                  <CardDescription>
                    Distribuição por fonte de origem
                  </CardDescription>
                </CardHeader>
                <CardContent className="h-80">
                  {leadsStats?.leads_by_source && leadsStats.leads_by_source.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={leadsStats.leads_by_source}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={(entry) => `${entry.source}: ${entry.count}`}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="count"
                          nameKey="source"
                        >
                          {leadsStats.leads_by_source.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                      Sem dados de origem disponíveis
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* KPIs de Conversão */}
            {conversionStats && (
              <div className="grid gap-4 md:grid-cols-4">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Tempo Médio Conversão</CardTitle>
                    <Clock className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{conversionStats.avg_conversion_days} dias</div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Desde criação até proposta
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Leads Convertidos</CardTitle>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{conversionStats.total_converted}</div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Chegaram a proposta/reserva
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Conversão Mais Rápida</CardTitle>
                    <TrendingUp className="h-4 w-4 text-green-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{conversionStats.min_days} dias</div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Conversão Mais Lenta</CardTitle>
                    <TrendingDown className="h-4 w-4 text-orange-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{conversionStats.max_days} dias</div>
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          <TabsContent value="ranking" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Trophy className="h-5 w-5 text-yellow-500" />
                  Ranking de Consultores
                </CardTitle>
                <CardDescription>
                  Top 5 consultores com mais leads angariados
                </CardDescription>
              </CardHeader>
              <CardContent>
                {leadsStats?.top_consultors && leadsStats.top_consultors.length > 0 ? (
                  <div className="space-y-4">
                    {leadsStats.top_consultors.map((consultor, index) => (
                      <div key={index} className="flex items-center gap-4">
                        <div className={`flex items-center justify-center w-8 h-8 rounded-full font-bold text-white ${
                          index === 0 ? 'bg-yellow-500' :
                          index === 1 ? 'bg-gray-400' :
                          index === 2 ? 'bg-amber-600' :
                          'bg-blue-500'
                        }`}>
                          {index + 1}
                        </div>
                        <div className="flex-1">
                          <p className="font-medium">{consultor.name}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-2xl font-bold text-blue-600">{consultor.leads_count}</p>
                          <p className="text-xs text-muted-foreground">leads</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center text-muted-foreground py-8">
                    Sem dados de ranking disponíveis
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default StatisticsPage;
