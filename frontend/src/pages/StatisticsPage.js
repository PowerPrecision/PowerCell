/**
 * StatisticsPage — Página de estatísticas e relatórios do CRM.
 *
 * PORQUÊ: Fornece dados agregados sobre o estado do sistema (processos por
 * macro-fase, gargalos, distribuição por consultor). Essencial para
 * acompanhar produtividade e identificar onde os processos ficam presos.
 *
 * A AGREGAÇÃO É DO SERVIDOR (Dashboard, Camada 2)
 *   Esta página fazia `getProcesses()` sem filtro, trazia os 12.450
 *   processos de produção para o browser e contava em JavaScript. Três
 *   consequências, todas reais:
 *
 *   1. A base de dados inteira pela rede para desenhar barras.
 *   2. Listas de nomes de fases CRAVADAS (`['concluidos','desistencias']`)
 *      — exactamente o que o Épico 10 implodiu no servidor.
 *   3. O agrupamento pelo valor CRU de `status` punha os 205 processos em
 *      `cpcv`/`escriturado` e as 12 gralhas `"Concluidos "` em barras
 *      próprias: o Kanban resolvia-os para a coluna certa e o gráfico não.
 *      Duas verdades sobre os mesmos dados, no mesmo produto.
 *
 *   Hoje consome `/stats/funil` e `/stats/sla`, onde a ponte com o motor de
 *   workflow garante que uma barra conta o mesmo que uma coluna do quadro.
 *   O que resta neste ficheiro é apresentação; as transformações puras
 *   vivem em `utils/statsFunil.js`, testadas.
 *
 * @context {AuthContext} — Consome user para permissões
 */

import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { 
  BarChart, Bar, PieChart, Pie, Cell, 
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";
import { 
  TrendingUp, TrendingDown, FileText, CheckCircle, 
  Clock, Euro, Target, Building, Trophy
} from "lucide-react";
import {
  getStats,
  getStatsConversion,
  getStatsFunil,
  getStatsLeads,
  getStatsSla,
  getUsers,
} from "../services/api";
import {
  avisosDaAmostra,
  barrasDeValor,
  barrasDoFunil,
  fatiasDePrioridade,
  linhasDeSla,
  linhasForaDoFunil,
} from "../utils/statsFunil";
import { toast } from "sonner";
import { hasAnyRole } from "../utils/roleUtils";
import SafeChartContainer from "../components/ui/SafeChartContainer";
import { Spinner } from "../components/ui/Spinner";

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const StatisticsPage = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [, setStats] = useState({});
  const [funil, setFunil] = useState(null);
  const [sla, setSla] = useState(null);
  const [users, setUsers] = useState([]);
  // "all" por omissão para quem vê tudo. Antes arrancava com o `user.id` e
  // o filtro era feito no cliente sobre `p.assigned_consultor` — um campo
  // que não existe nos processos —, pelo que a página abria VAZIA para um
  // administrador e só mostrava dados depois de ele escolher "Todos".
  const [selectedUser, setSelectedUser] = useState(
    hasAnyRole(user, ["admin", "ceo"]) ? "all" : user?.id,
  );
  const [timeRange, setTimeRange] = useState("30");
  
  // Estado para estatísticas de leads
  const [leadsStats, setLeadsStats] = useState(null);
  const [conversionStats, setConversionStats] = useState(null);

  const canViewAllStats = hasAnyRole(user, ["admin", "ceo"]);

  useEffect(() => {
    fetchData();
  }, [selectedUser, timeRange]);

  const fetchData = async () => {
    try {
      setLoading(true);
      // O `consultor_id` vai para o SERVIDOR. Antes, o filtro por
      // utilizador era feito no cliente sobre `p.assigned_consultor` — um
      // campo que não existe nos processos (os canónicos são
      // `assigned_consultor_id` / `consultor_id` / `consultant_id`), pelo
      // que escolher um utilizador esvaziava TODOS os gráficos sem dar
      // erro. Agora a condição é a canónica, do lado do servidor.
      const params = {};
      if (canViewAllStats && selectedUser && selectedUser !== "all") {
        params.consultor_id = selectedUser;
      }

      const [statsRes, funilRes, slaRes, usersRes] = await Promise.all([
        getStats(),
        getStatsFunil(params),
        getStatsSla(),
        canViewAllStats ? getUsers() : Promise.resolve({ data: [] }),
      ]);

      setStats(statsRes.data || {});
      setFunil(funilRes.data || null);
      setSla(slaRes.data || null);
      const usersData = usersRes.data;
      setUsers(Array.isArray(usersData) ? usersData : (usersData?.items || []));

      await fetchLeadsStats();
    } catch (error) {
      console.error("Erro ao carregar estatísticas:", error);
      toast.error("Erro ao carregar estatísticas");
    } finally {
      setLoading(false);
    }
  };

  const fetchLeadsStats = async () => {
    // Por AXIOS e não por `fetch`: um `fetch` cru não leva o
    // `X-Active-Role` que o interceptor injecta, e é por ele que o
    // servidor decide a permissão de estatísticas pelo PERFIL ACTIVO.
    try {
      const [leadsRes, convRes] = await Promise.all([
        getStatsLeads(),
        getStatsConversion(),
      ]);
      setLeadsStats(leadsRes.data || null);
      setConversionStats(convRes.data || null);
    } catch (error) {
      console.error("Erro ao carregar estatísticas de leads:", error);
    }
  };

  // ==================================================================
  // OS NÚMEROS VÊM DO SERVIDOR (Dashboard, Camada 2)
  // ==================================================================
  // Nenhuma lista de nomes de fases, nenhuma contagem sobre processos
  // crus. O que está aqui é escolha de etiqueta e formatação.
  const etapas = barrasDoFunil(funil);
  const foraDoFunil = linhasForaDoFunil(funil);
  const statusData = etapas.map((e) => ({ name: e.name, value: e.processos }))
    .concat(foraDoFunil.map((l) => ({ name: l.name, value: l.processos })));
  const prioridadeData = fatiasDePrioridade(funil);
  const valorPorFaseData = barrasDeValor(funil).map((b) => ({
    name: b.name,
    value: b.valor,
  }));
  const linhasSla = linhasDeSla(sla);
  const avisos = avisosDaAmostra(funil, sla);

  const totalProcessos = funil?.total_processos || 0;
  const concluidos = etapas.find((e) => e.key === "concluido")?.processos || 0;
  const perdidos = foraDoFunil.find((l) => l.key === "perdido")?.processos || 0;
  const emCurso = etapas
    .filter((e) => e.key !== "concluido")
    .reduce((soma, e) => soma + e.processos, 0);

  // Taxa sobre os DECIDIDOS (concluídos + perdidos), a mesma regra do
  // endpoint de redes: com o total no denominador, uma carteira jovem com
  // muitos processos em curso parecia pior do que uma antiga — media a
  // idade da carteira, não a eficiência.
  const taxaSucesso =
    concluidos + perdidos > 0
      ? ((concluidos / (concluidos + perdidos)) * 100).toFixed(1)
      : "—";

  const valorTotal = (funil?.etapas || []).reduce(
    (soma, etapa) => soma + (etapa.valor_imovel || 0),
    0,
  );
  const valorMedio = totalProcessos > 0 ? valorTotal / totalProcessos : 0;

  return (
    <DashboardLayout title="Estatísticas e Análise">
      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Spinner size="lg" className="text-muted-foreground" />
        </div>
      ) : (
      <div className="space-y-4 md:space-y-6">
        {/* Filtros */}
        <div className="flex flex-wrap gap-4">
          {canViewAllStats && (
            <Select value={selectedUser} onValueChange={setSelectedUser}>
              <SelectTrigger className="w-full sm:w-64">
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
            <SelectTrigger className="w-full sm:w-48">
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
                {emCurso} em curso
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
                {concluidos} concluídos vs {perdidos} perdidos
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

        {/*
          Avisos sobre a AMOSTRA, não sobre erros.

          Um gráfico que mistura medido com estimado sem o dizer é pior do
          que um gráfico vazio: o utilizador tira conclusões sobre um
          universo que não sabe qual é. As frases vêm de `avisosDaAmostra`,
          que é pura e testada — a UI não decide o que avisar.
        */}
        {avisos.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Sobre estes números</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {avisos.map((aviso) => (
                <p key={aviso} className="text-sm text-muted-foreground">
                  {aviso}
                </p>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Gráficos */}
        <Tabs defaultValue="status" className="space-y-4">
          <TabsList>
            <TabsTrigger value="status">Por Fase</TabsTrigger>
            <TabsTrigger value="sla">Gargalos</TabsTrigger>
            <TabsTrigger value="priority">Por Prioridade</TabsTrigger>
            <TabsTrigger value="value">Valor por Fase</TabsTrigger>
            <TabsTrigger value="leads">Funil de Leads</TabsTrigger>
            <TabsTrigger value="ranking">Ranking Consultores</TabsTrigger>
          </TabsList>

          {/*
            GARGALOS — permanência por macro-fase.

            A média vai ao lado da MEDIANA de propósito: num gargalo a média
            mente sempre no mesmo sentido (um processo esquecido há 400 dias
            arrasta-a) e o histograma mostra a forma real da distribuição.
            As macro-fases terminais não aparecem: um processo concluído não
            demora em concluído, fica lá.
          */}
          <TabsContent value="sla" className="space-y-4">
            {linhasSla.length === 0 ? (
              <Card>
                <CardContent className="py-10 text-center text-sm text-muted-foreground">
                  Sem dados de permanência para mostrar.
                </CardContent>
              </Card>
            ) : (
              linhasSla.map((linha) => (
                <Card key={linha.key}>
                  <CardHeader>
                    <CardTitle className="capitalize">{linha.key}</CardTitle>
                    <CardDescription>
                      {linha.emCurso} em curso
                      {linha.limiarDias
                        ? ` · ${linha.emRisco} acima de ${linha.limiarDias} dias`
                        : " · sem limiar configurado"}
                      {linha.bandaMediana
                        ? ` · mediana na banda ${linha.bandaMediana} dias`
                        : ""}
                      {linha.diasMedios !== null && linha.diasMedios !== undefined
                        ? ` · média ${linha.diasMedios} dias`
                        : ""}
                      {linha.amostraHistorico > 0
                        ? ` · histórico medido: ${linha.diasMediosHistorico} dias em ${linha.amostraHistorico} processos`
                        : ""}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <SafeChartContainer className="h-[200px] min-w-0">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={linha.bandas}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="name" />
                          <YAxis />
                          <Tooltip />
                          <Bar
                            dataKey="processos"
                            fill={COLORS[0]}
                            name="Processos"
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </SafeChartContainer>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          <TabsContent value="status" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Distribuição por Macro-Fase</CardTitle>
                <CardDescription>
                  Processos por grupo do funil, agrupados pelo motor de
                  workflow — inclui as fases legadas resolvidas para o grupo
                  correcto
                </CardDescription>
              </CardHeader>
              <CardContent>
                <SafeChartContainer className="h-[260px] min-w-0">
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
                </SafeChartContainer>
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
              <CardContent>
                <SafeChartContainer className="h-[260px] min-w-0">
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
                </SafeChartContainer>
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
              <CardContent>
                <SafeChartContainer className="h-[260px] min-w-0">
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
                </SafeChartContainer>
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
                <CardContent>
                  {leadsStats?.funnel_data && Array.isArray(leadsStats.funnel_data) && (
                    <SafeChartContainer className="h-[260px] min-w-0">
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
                    </SafeChartContainer>
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
                <CardContent>
                  {Array.isArray(leadsStats?.leads_by_source) && leadsStats.leads_by_source.length > 0 ? (
                    <SafeChartContainer className="h-[260px] min-w-0">
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
                    </SafeChartContainer>
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
                {Array.isArray(leadsStats?.top_consultors) && leadsStats.top_consultors.length > 0 ? (
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
      )}
    </DashboardLayout>
  );
};

export default StatisticsPage;

