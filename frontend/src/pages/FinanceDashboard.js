import React, { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Building2,
  Users,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import DashboardLayout from "../layouts/DashboardLayout";
import { useAuth } from "../contexts/AuthContext";
import {
  getFinanceSummary,
  getFinanceMonthly,
  getFinanceCommissions,
  getFinancePerformance,
} from "../services/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  LineChart,
  Line,
} from "recharts";

// ====================================================================
// HELPERS
// ====================================================================

const formatCurrency = (value) => {
  if (value == null || isNaN(value)) return "0,00 €";
  return new Intl.NumberFormat("pt-PT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(value);
};

const formatNumber = (value) => {
  if (value == null || isNaN(value)) return "0";
  return new Intl.NumberFormat("pt-PT").format(value);
};

const VariationIndicator = ({ value }) => {
  if (value === null || value === undefined) {
    return (
      <span className="flex items-center text-sm text-muted-foreground">
        <Minus className="h-3 w-3 mr-1" />
        s/ dados
      </span>
    );
  }
  if (value > 0) {
    return (
      <span className="flex items-center text-sm text-green-600">
        <ArrowUpRight className="h-3 w-3 mr-1" />
        +{value}%
      </span>
    );
  }
  if (value < 0) {
    return (
      <span className="flex items-center text-sm text-red-600">
        <ArrowDownRight className="h-3 w-3 mr-1" />
        {value}%
      </span>
    );
  }
  return (
    <span className="flex items-center text-sm text-muted-foreground">
      <Minus className="h-3 w-3 mr-1" />
      0%
    </span>
  );
};

// ====================================================================
// CUSTOM TOOLTIP PARA CHARTS
// ====================================================================

const FinanceTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-background border rounded-lg shadow-lg p-3 text-sm">
      <p className="font-medium mb-1">{label}</p>
      {payload.map((entry, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">{formatCurrency(entry.value)}</span>
        </div>
      ))}
    </div>
  );
};

// ====================================================================
// STAT CARD (inline para reaproveitar padrão AdminPageShared)
// ====================================================================

const FinanceStatCard = ({ title, value, subtitle, icon: Icon, color, variation }) => (
  <Card>
    <CardContent className="p-5">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className={`text-2xl font-bold mt-1 ${color || ""}`}>{value}</p>
          <div className="mt-1">
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
            {variation !== undefined && <VariationIndicator value={variation} />}
          </div>
        </div>
        <div
          className={`p-3 rounded-xl ${color === "text-green-600" ? "bg-green-50" : color === "text-red-600" ? "bg-red-50" : color === "text-blue-600" ? "bg-blue-50" : "bg-purple-50"}`}
        >
          <Icon
            className={`h-6 w-6 ${color === "text-green-600" ? "text-green-600" : color === "text-red-600" ? "text-red-600" : color === "text-blue-600" ? "text-blue-600" : "text-purple-600"}`}
          />
        </div>
      </div>
    </CardContent>
  </Card>
);

// ====================================================================
// MAIN COMPONENT
// ====================================================================

const FinanceDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dados
  const [summary, setSummary] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [commissions, setCommissions] = useState(null);
  const [performance, setPerformance] = useState(null);

  // Filtros
  const currentYear = new Date().getFullYear();
  const yearParam = parseInt(searchParams.get("year")) || currentYear;
  const [selectedYear, setSelectedYear] = useState(yearParam);

  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { year: selectedYear };
      const [summaryRes, monthlyRes, commissionsRes, performanceRes] =
        await Promise.all([
          getFinanceSummary(params),
          getFinanceMonthly(params),
          getFinanceCommissions(params),
          getFinancePerformance(params),
        ]);
      setSummary(summaryRes.data);
      setMonthly(monthlyRes.data);
      setCommissions(commissionsRes.data);
      setPerformance(performanceRes.data);
    } catch (err) {
      console.error("Erro ao carregar dados financeiros:", err);
      setError(err.response?.data?.detail || "Erro ao carregar dados financeiros.");
    } finally {
      setLoading(false);
    }
  }, [selectedYear]);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  const handleYearChange = (direction) => {
    const newYear = selectedYear + direction;
    if (newYear >= 2020 && newYear <= currentYear + 1) {
      setSelectedYear(newYear);
      setSearchParams({ year: newYear });
    }
  };

  // Data para gráfico mensal
  const monthlyChartData = (monthly?.monthly || []).map((m) => ({
    name: m.month_label,
    Receita: m.receita,
    Despesas: m.despesas,
    Lucro: m.lucro,
  }));

  // Data para gráfico de valor de imóveis por mês
  const imoveisChartData = (monthly?.monthly || []).map((m) => ({
    name: m.month_label,
    "Valor Imóveis": m.valor_imoveis,
    Processos: m.num_processos,
  }));

  if (loading) {
    return (
      <DashboardLayout>
        <div className="p-4 md:p-6 space-y-4 md:space-y-6">
          <div className="flex items-center gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
            <span className="text-muted-foreground">
              A carregar dados financeiros...
            </span>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="p-4 md:p-6 space-y-4 md:space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <BarChart3 className="h-6 w-6 text-purple-600" />
              Dashboard Financeiro
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Visão geral financeira da empresa — exclusivo para Administração
            </p>
          </div>

          {/* Selector de Ano */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => handleYearChange(-1)}
              disabled={selectedYear <= 2020}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2 px-4 py-2 border rounded-lg bg-background">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <span className="font-semibold">{selectedYear}</span>
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={() => handleYearChange(1)}
              disabled={selectedYear >= currentYear + 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-4">
              <p className="text-red-600 text-sm">{error}</p>
            </CardContent>
          </Card>
        )}

        {/* KPIs Principais */}
        {summary && performance && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <FinanceStatCard
              title="Receita Total"
              value={formatCurrency(summary.total_receita)}
              subtitle={`${summary.processos_com_comissao} processos com comissão`}
              icon={TrendingUp}
              color="text-green-600"
              variation={performance.variations?.receita}
            />
            <FinanceStatCard
              title="Despesas Estimadas"
              value={formatCurrency(summary.total_despesas)}
              subtitle="Comissões de colaboradores"
              icon={TrendingDown}
              color="text-red-600"
              variation={performance.variations?.receita !== undefined ? (performance.variations.receita > 0 ? performance.variations.receita * 0.5 : performance.variations.receita) : undefined}
            />
            <FinanceStatCard
              title="Lucro Líquido"
              value={formatCurrency(summary.lucro_liquido)}
              subtitle={`Margem: ${summary.taxa_margem}%`}
              icon={DollarSign}
              color="text-blue-600"
              variation={performance.variations?.lucro}
            />
            <FinanceStatCard
              title="Valor Total Imóveis"
              value={formatCurrency(summary.total_valor_imoveis)}
              subtitle={`${summary.total_processos_concluidos} processos concluídos`}
              icon={Building2}
              color="text-purple-600"
              variation={performance.variations?.valor_imoveis}
            />
          </div>
        )}

        {/* Tabs com conteúdo detalhado */}
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="grid w-full grid-cols-3 lg:w-auto lg:inline-grid">
            <TabsTrigger value="overview">Visão Geral</TabsTrigger>
            <TabsTrigger value="monthly">Mensal</TabsTrigger>
            <TabsTrigger value="commissions">Comissões</TabsTrigger>
          </TabsList>

          {/* TAB: Visão Geral */}
          <TabsContent value="overview" className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Gráfico de Receita/Despesas/Lucro */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Receitas vs Despesas vs Lucro
                  </CardTitle>
                  <CardDescription>
                    Evolução mensal em {selectedYear}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="h-[200px] sm:h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={monthlyChartData}>
                        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                        <XAxis dataKey="name" fontSize={12} />
                        <YAxis
                          fontSize={12}
                          tickFormatter={(v) =>
                            v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v
                          }
                        />
                        <Tooltip content={<FinanceTooltip />} />
                        <Legend />
                        <Bar
                          dataKey="Receita"
                          fill="#22c55e"
                          radius={[4, 4, 0, 0]}
                        />
                        <Bar
                          dataKey="Despesas"
                          fill="#ef4444"
                          radius={[4, 4, 0, 0]}
                        />
                        <Bar
                          dataKey="Lucro"
                          fill="#3b82f6"
                          radius={[4, 4, 0, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>

              {/* Gráfico de Valor Imóveis */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Valor de Imóveis por Mês
                  </CardTitle>
                  <CardDescription>
                    Volume de negócios imobiliários em {selectedYear}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="h-[200px] sm:h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={imoveisChartData}>
                        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                        <XAxis dataKey="name" fontSize={12} />
                        <YAxis
                          fontSize={12}
                          yAxisId="left"
                          tickFormatter={(v) =>
                            v >= 1000000
                              ? `${(v / 1000000).toFixed(1)}M`
                              : v >= 1000
                              ? `${(v / 1000).toFixed(0)}k`
                              : v
                          }
                        />
                        <YAxis
                          fontSize={12}
                          yAxisId="right"
                          orientation="right"
                          tickFormatter={(v) => v}
                        />
                        <Tooltip content={<FinanceTooltip />} />
                        <Legend />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="Valor Imóveis"
                          stroke="#8b5cf6"
                          strokeWidth={2}
                          dot={{ r: 4 }}
                        />
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey="Processos"
                          stroke="#f59e0b"
                          strokeWidth={2}
                          dot={{ r: 3 }}
                          strokeDasharray="5 5"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Top Processos por Comissão */}
            {summary && summary.processes && summary.processes.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Top Processos por Comissão
                  </CardTitle>
                  <CardDescription>
                    Processos concluídos com maior valor de comissão
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                            Processo
                          </th>
                          <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                            Cliente
                          </th>
                          <th className="text-right py-2 px-3 font-medium text-muted-foreground">
                            Comissão
                          </th>
                          <th className="text-right py-2 px-3 font-medium text-muted-foreground">
                            Valor Imóvel
                          </th>
                          <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                            Consultor
                          </th>
                          <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                            Mediador
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.processes
                          .filter((p) => p.comissao > 0)
                          .slice(0, 15)
                          .map((p, idx) => (
                            <tr
                              key={p.id || idx}
                              className="border-b hover:bg-muted/50 cursor-pointer"
                              onClick={() => p.id && navigate(`/processo/${p.id}`)}
                            >
                              <td className="py-2 px-3 font-mono text-xs">
                                #{p.process_number || "—"}
                              </td>
                              <td className="py-2 px-3">{p.client_name}</td>
                              <td className="py-2 px-3 text-right font-semibold text-green-600">
                                {formatCurrency(p.comissao)}
                              </td>
                              <td className="py-2 px-3 text-right">
                                {p.valor_imovel > 0
                                  ? formatCurrency(p.valor_imovel)
                                  : "—"}
                              </td>
                              <td className="py-2 px-3">
                                <div className="flex flex-wrap gap-1">
                                  {Array.isArray(p.consultor) &&
                                    p.consultor.map((c, i) =>
                                      c ? (
                                        <Badge
                                          key={i}
                                          variant="outline"
                                          className="text-xs"
                                        >
                                          {c}
                                        </Badge>
                                      ) : null
                                    )}
                                </div>
                              </td>
                              <td className="py-2 px-3">
                                <div className="flex flex-wrap gap-1">
                                  {Array.isArray(p.mediador) &&
                                    p.mediador.map((m, i) =>
                                      m ? (
                                        <Badge
                                          key={i}
                                          variant="outline"
                                          className="text-xs"
                                        >
                                          {m}
                                        </Badge>
                                      ) : null
                                    )}
                                </div>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Estado dos dados */}
            <Card className="border-amber-200 bg-amber-50">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <BarChart3 className="h-5 w-5 text-amber-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-amber-800">
                      Nota sobre os dados financeiros
                    </p>
                    <p className="text-xs text-amber-700 mt-1">
                      Os valores são calculados com base no campo{" "}
                      <code className="bg-amber-100 px-1 rounded">
                        comissao_mediacao
                      </code>{" "}
                      dos processos concluídos. As despesas são estimadas em
                      50% da receita (comissões de colaboradores). Para dados
                      mais precisos, certifique-se de que os valores de comissão
                      estão preenchidos nos processos.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* TAB: Mensal */}
          <TabsContent value="monthly" className="space-y-4">
            {monthly && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <FinanceStatCard
                    title="Receita Anual"
                    value={formatCurrency(monthly.total_receita)}
                    subtitle="Total de comissões"
                    icon={TrendingUp}
                    color="text-green-600"
                  />
                  <FinanceStatCard
                    title="Despesas Anuais"
                    value={formatCurrency(monthly.total_despesas)}
                    subtitle="Estimativa de comissões pagas"
                    icon={TrendingDown}
                    color="text-red-600"
                  />
                  <FinanceStatCard
                    title="Processos Concluídos"
                    value={formatNumber(monthly.total_processos)}
                    subtitle={`Imóveis: ${formatCurrency(monthly.total_valor_imoveis)}`}
                    icon={Calendar}
                    color="text-purple-600"
                  />
                </div>

                {/* Tabela mensal detalhada */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">
                      Detalhe Mensal — {selectedYear}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                              Mês
                            </th>
                            <th className="text-right py-2 px-3 font-medium text-muted-foreground">
                              Processos
                            </th>
                            <th className="text-right py-2 px-3 font-medium text-muted-foreground">
                              Valor Imóveis
                            </th>
                            <th className="text-right py-2 px-3 font-medium text-green-600">
                              Receita
                            </th>
                            <th className="text-right py-2 px-3 font-medium text-red-600">
                              Despesas
                            </th>
                            <th className="text-right py-2 px-3 font-medium text-blue-600">
                              Lucro
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {monthly.monthly.map((m) => (
                            <tr
                              key={m.month}
                              className="border-b hover:bg-muted/50"
                            >
                              <td className="py-2 px-3 font-medium">
                                {m.month_label}
                              </td>
                              <td className="py-2 px-3 text-right">
                                {m.num_processos}
                              </td>
                              <td className="py-2 px-3 text-right">
                                {m.valor_imoveis > 0
                                  ? formatCurrency(m.valor_imoveis)
                                  : "—"}
                              </td>
                              <td className="py-2 px-3 text-right text-green-600 font-medium">
                                {m.receita > 0
                                  ? formatCurrency(m.receita)
                                  : "—"}
                              </td>
                              <td className="py-2 px-3 text-right text-red-600">
                                {m.despesas > 0
                                  ? formatCurrency(m.despesas)
                                  : "—"}
                              </td>
                              <td className="py-2 px-3 text-right text-blue-600 font-semibold">
                                {m.lucro > 0
                                  ? formatCurrency(m.lucro)
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr className="font-bold border-t-2">
                            <td className="py-3 px-3">Total</td>
                            <td className="py-3 px-3 text-right">
                              {monthly.total_processos}
                            </td>
                            <td className="py-3 px-3 text-right">
                              {formatCurrency(monthly.total_valor_imoveis)}
                            </td>
                            <td className="py-3 px-3 text-right text-green-600">
                              {formatCurrency(monthly.total_receita)}
                            </td>
                            <td className="py-3 px-3 text-right text-red-600">
                              {formatCurrency(monthly.total_despesas)}
                            </td>
                            <td className="py-3 px-3 text-right text-blue-600">
                              {formatCurrency(monthly.total_lucro)}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </CardContent>
                </Card>

                {/* Gráfico acumulado */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">
                      Evolução Mensal Acumulada
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[200px] sm:h-[300px] lg:h-[350px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={monthlyChartData}>
                          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                          <XAxis dataKey="name" fontSize={12} />
                          <YAxis
                            fontSize={12}
                            tickFormatter={(v) =>
                              v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v
                            }
                          />
                          <Tooltip content={<FinanceTooltip />} />
                          <Legend />
                          <Bar
                            dataKey="Receita"
                            fill="#22c55e"
                            radius={[4, 4, 0, 0]}
                            stackId="a"
                          />
                          <Bar
                            dataKey="Despesas"
                            fill="#ef4444"
                            radius={[4, 4, 0, 0]}
                            stackId="b"
                          />
                          <Bar
                            dataKey="Lucro"
                            fill="#3b82f6"
                            radius={[4, 4, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>

          {/* TAB: Comissões */}
          <TabsContent value="commissions" className="space-y-4">
            {commissions && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <FinanceStatCard
                    title="Total Comissões Pagas"
                    value={formatCurrency(commissions.total_comissoes_pagas)}
                    subtitle="Estimativa de pagamentos a colaboradores"
                    icon={Users}
                    color="text-red-600"
                  />
                  <FinanceStatCard
                    title="Colaboradores Activos"
                    value={commissions.collaborators.length}
                    subtitle="Consultores e intermediários com processos"
                    icon={Users}
                    color="text-blue-600"
                  />
                </div>

                {/* Ranking de colaboradores */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">
                      Ranking de Colaboradores — {selectedYear}
                    </CardTitle>
                    <CardDescription>
                      Comissões associadas a processos concluídos
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {commissions.collaborators.length === 0 ? (
                      <p className="text-center text-muted-foreground py-8">
                        Sem dados de comissões para este período.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b">
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground w-8">
                                #
                              </th>
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                                Colaborador
                              </th>
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                                Função
                              </th>
                              <th className="text-right py-2 px-3 font-medium text-muted-foreground">
                                Processos
                              </th>
                              <th className="text-right py-2 px-3 font-medium text-muted-foreground">
                                Comissão Total
                              </th>
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                                Tipos
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {commissions.collaborators.map((c, idx) => (
                              <tr
                                key={c.name}
                                className="border-b hover:bg-muted/50"
                              >
                                <td className="py-2 px-3 text-muted-foreground font-mono">
                                  {idx + 1}
                                </td>
                                <td className="py-2 px-3 font-medium">
                                  {c.name}
                                </td>
                                <td className="py-2 px-3">
                                  <Badge
                                    variant={
                                      c.role === "consultor"
                                        ? "default"
                                        : "secondary"
                                    }
                                    className="text-xs"
                                  >
                                    {c.role === "consultor"
                                      ? "Consultor"
                                      : "Intermediário"}
                                  </Badge>
                                </td>
                                <td className="py-2 px-3 text-right">
                                  {c.num_processos}
                                </td>
                                <td className="py-2 px-3 text-right font-semibold text-green-600">
                                  {formatCurrency(c.total_comissao)}
                                </td>
                                <td className="py-2 px-3">
                                  <div className="flex flex-wrap gap-1">
                                    {c.tipos_processo.map((t, i) => (
                                      <Badge
                                        key={i}
                                        variant="outline"
                                        className="text-xs capitalize"
                                      >
                                        {t}
                                      </Badge>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default FinanceDashboard;
