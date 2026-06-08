/**
 * TeamPerformanceDashboard — Dashboard Executivo de Desempenho.
 *
 * Página exclusiva para Admin/CEO com visualizações avançadas:
 * - Gráfico de Barras: Tarefas Concluídas vs Atrasadas + Processos Movidos
 * - Filtro dropdown por utilizador
 * - Seletor de período (Esta Semana, Este Mês, etc.)
 * - Painel de detalhe individual com rácios
 * - Tabela refinada para visualização em detalhe
 */
import { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../components/ui/table";
import {
  Users, TrendingUp, CheckCircle, AlertTriangle, Clock, Loader2,
  Trophy, CalendarDays, RefreshCw, Activity, BarChart3,
  Target, UserCheck, ClipboardList,
} from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, Cell,
} from "recharts";
import { toast } from "sonner";
import { format, subDays, startOfWeek, startOfMonth, endOfWeek, endOfMonth } from "date-fns";
import { pt } from "date-fns/locale";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com";

// ── Mapeamento de roles para labels legíveis ──────────────────
const roleLabels = {
  consultor: "Consultor",
  intermediario: "Intermediário",
  administrativo: "Administrativo",
  indexacao: "Indexação",
  diretor: "Diretor",
  ceo: "CEO",
  admin: "Admin",
};

// ── Opções de período ──────────────────────────────────────
const PERIOD_OPTIONS = [
  { key: "this_week", label: "Esta Semana" },
  { key: "last_week", label: "Semana Passada" },
  { key: "this_month", label: "Este Mês" },
  { key: "last_month", label: "Mês Passado" },
  { key: "7d", label: "Últimos 7 dias" },
  { key: "14d", label: "Últimos 14 dias" },
  { key: "30d", label: "Últimos 30 dias" },
  { key: "90d", label: "Últimos 90 dias" },
];

// ── Helpers para datas ────────────────────────────────────
function getDateRange(periodKey) {
  const now = new Date();
  switch (periodKey) {
    case "this_week": {
      const start = format(startOfWeek(now, { weekStartsOn: 1 }), "yyyy-MM-dd");
      const end = format(now, "yyyy-MM-dd");
      return { start, end };
    }
    case "last_week": {
      const lw = subDays(now, 7);
      const start = format(startOfWeek(lw, { weekStartsOn: 1 }), "yyyy-MM-dd");
      const end = format(endOfWeek(lw, { weekStartsOn: 1 }), "yyyy-MM-dd");
      return { start, end };
    }
    case "this_month": {
      const start = format(startOfMonth(now), "yyyy-MM-dd");
      const end = format(now, "yyyy-MM-dd");
      return { start, end };
    }
    case "last_month": {
      const lm = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const start = format(startOfMonth(lm), "yyyy-MM-dd");
      const end = format(endOfMonth(lm), "yyyy-MM-dd");
      return { start, end };
    }
    case "7d": return { start: format(subDays(now, 7), "yyyy-MM-dd"), end: format(now, "yyyy-MM-dd") };
    case "14d": return { start: format(subDays(now, 14), "yyyy-MM-dd"), end: format(now, "yyyy-MM-dd") };
    case "30d": return { start: format(subDays(now, 30), "yyyy-MM-dd"), end: format(now, "yyyy-MM-dd") };
    case "90d": return { start: format(subDays(now, 90), "yyyy-MM-dd"), end: format(now, "yyyy-MM-dd") };
    default: return { start: format(subDays(now, 7), "yyyy-MM-dd"), end: format(now, "yyyy-MM-dd") };
  }
}

// ── Custom Tooltip para o BarChart ────────────────────────
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border bg-background p-3 shadow-md">
      <p className="font-semibold text-sm mb-1.5">{label}</p>
      {payload.map((entry, idx) => (
        <div key={idx} className="flex items-center gap-2 text-sm">
          <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-semibold">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Cores do gráfico ──────────────────────────────────────
const CHART_COLORS = {
  tasks_completed: "#22c55e",
  tasks_overdue: "#ef4444",
  processes_moved: "#0ea5e9",
};

// ════════════════════════════════════════════════════════════
// Componente Principal
// ════════════════════════════════════════════════════════════
const TeamPerformanceDashboard = () => {
  const token = localStorage.getItem("token");

  // Período
  const [period, setPeriod] = useState("this_week");
  const [startDate, setStartDate] = useState(() => getDateRange("this_week").start);
  const [endDate, setEndDate] = useState(() => getDateRange("this_week").end);

  // Dados
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Filtro de utilizador
  const [selectedUser, setSelectedUser] = useState("all");

  // ── Buscar dados do endpoint ──────────────────────────────
  const fetchPerformance = async (start, end) => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (start) params.set("start_date", start);
      if (end) params.set("end_date", end);

      const res = await fetch(
        `${BACKEND_URL}/api/admin/team-performance?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Erro ao carregar dados de desempenho");
      }

      const json = await res.json();
      setData(json);
    } catch (error) {
      console.error("[TeamPerformanceDashboard]", error);
      toast.error(error.message || "Erro ao carregar desempenho da equipa");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPerformance(startDate, endDate);
  }, [startDate, endDate]);

  // ── Handler: mudar período ────────────────────────────────
  const handlePeriodChange = (key) => {
    setPeriod(key);
    const { start, end } = getDateRange(key);
    setStartDate(start);
    setEndDate(end);
    setSelectedUser("all");
  };

  const handleRefresh = () => {
    fetchPerformance(startDate, endDate);
  };

  // ── Dados derivados ───────────────────────────────────────
  const summary = data?.summary || {};
  const allUsers = data?.users || [];

  // Filtro por utilizador
  const filteredUsers = useMemo(() => {
    if (selectedUser === "all") return allUsers;
    return allUsers.filter((u) => u.user_id === selectedUser);
  }, [allUsers, selectedUser]);

  // Utilizador seleccionado (para painel de detalhe)
  const selectedUserData = useMemo(() => {
    if (selectedUser === "all") return null;
    return allUsers.find((u) => u.user_id === selectedUser) || null;
  }, [allUsers, selectedUser]);

  // Dados para o gráfico de barras
  const chartData = useMemo(() => {
    return filteredUsers.map((u) => ({
      name: u.name?.split(" ")[0] || u.name || "N/A",
      fullName: u.name || "N/A",
      "Tarefas Concluídas": u.tasks_completed || 0,
      "Tarefas Atrasadas": u.tasks_overdue || 0,
      "Processos Movidos": u.processes_moved || 0,
    }));
  }, [filteredUsers]);

  // Top performers
  const topPerformers = useMemo(() => {
    return [...allUsers]
      .sort((a, b) => (b.processes_moved + b.tasks_completed) - (a.processes_moved + a.tasks_completed))
      .slice(0, 3);
  }, [allUsers]);

  const medals = ["🥇", "🥈", "🥉"];

  // ── Rácios do utilizador seleccionado ──────────────────────
  const userRatios = useMemo(() => {
    if (!selectedUserData) return null;
    const u = selectedUserData;
    const totalTasks = u.tasks_completed + u.tasks_overdue + u.tasks_pending;
    const completionRate = totalTasks > 0 ? ((u.tasks_completed / totalTasks) * 100).toFixed(1) : "0.0";
    const overdueRate = totalTasks > 0 ? ((u.tasks_overdue / totalTasks) * 100).toFixed(1) : "0.0";
    const efficiency = u.tasks_completed > 0
      ? ((u.processes_moved / u.tasks_completed) * 100).toFixed(1)
      : "0.0";
    return { completionRate, overdueRate, efficiency, totalTasks };
  }, [selectedUserData]);

  // ── Period label para exibição ─────────────────────────────
  const periodLabel = PERIOD_OPTIONS.find((p) => p.key === period)?.label || period;
  const dateRangeLabel = data?.period_start
    ? `${format(new Date(data.period_start), "dd/MM/yy", { locale: pt })} — ${format(new Date(data.period_end), "dd/MM/yy", { locale: pt })}`
    : "";

  return (
    <DashboardLayout title="Desempenho da Equipa">
    <div className="space-y-6 p-1">
      {/* ══ CABEÇALHO ══════════════════════════════════════ */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6 text-blue-500" />
            Desempenho da Equipa
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Dashboard Executivo — {periodLabel}
            {dateRangeLabel && <span className="ml-1">({dateRangeLabel})</span>}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Seletor de período */}
          <Select value={period} onValueChange={handlePeriodChange}>
            <SelectTrigger className="w-[160px]">
              <CalendarDays className="h-4 w-4 mr-2 text-muted-foreground" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((opt) => (
                <SelectItem key={opt.key} value={opt.key}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Filtro de utilizador */}
          <Select value={selectedUser} onValueChange={setSelectedUser}>
            <SelectTrigger className="w-[180px]">
              <Users className="h-4 w-4 mr-2 text-muted-foreground" />
              <SelectValue placeholder="Todos" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toda a Equipa</SelectItem>
              {allUsers.map((u) => (
                <SelectItem key={u.user_id} value={u.user_id}>
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Botão actualizar */}
          <Button size="sm" onClick={handleRefresh} disabled={loading} className="gap-1.5">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Actualizar
          </Button>
        </div>
      </div>

      {/* ══ KPI SUMMARY CARDS ═════════════════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-teal-500">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-teal-50 dark:bg-teal-950/50 flex items-center justify-center shrink-0">
                <TrendingUp className="h-5 w-5 text-teal-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {selectedUser === "all"
                    ? (summary.total_processes_moved ?? "—")
                    : (selectedUserData?.processes_moved ?? "—")}
                </p>
                <p className="text-xs text-muted-foreground">Processos Avançados</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-500">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-green-50 dark:bg-green-950/50 flex items-center justify-center shrink-0">
                <CheckCircle className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {selectedUser === "all"
                    ? (summary.total_tasks_completed ?? "—")
                    : (selectedUserData?.tasks_completed ?? "—")}
                </p>
                <p className="text-xs text-muted-foreground">Tarefas Concluídas</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-red-50 dark:bg-red-950/50 flex items-center justify-center shrink-0">
                <AlertTriangle className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-red-600">
                  {selectedUser === "all"
                    ? (summary.total_tasks_overdue ?? "—")
                    : (selectedUserData?.tasks_overdue ?? "—")}
                </p>
                <p className="text-xs text-muted-foreground">Tarefas Atrasadas</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-amber-50 dark:bg-amber-950/50 flex items-center justify-center shrink-0">
                <Clock className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-amber-600">
                  {selectedUser === "all"
                    ? (summary.total_tasks_pending ?? "—")
                    : (selectedUserData?.tasks_pending ?? "—")}
                </p>
                <p className="text-xs text-muted-foreground">Tarefas Pendentes</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ══ PAINEL DE DETALHE INDIVIDUAL ══════════════════ */}
      {selectedUserData && userRatios && (
        <Card className="bg-gradient-to-r from-blue-50/50 to-indigo-50/50 dark:from-blue-950/20 dark:to-indigo-950/20 border-blue-200 dark:border-blue-900">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <UserCheck className="h-5 w-5 text-blue-500" />
              {selectedUserData.name}
              <Badge variant="outline" className="ml-2">
                {roleLabels[selectedUserData.role] || selectedUserData.role}
              </Badge>
            </CardTitle>
            <CardDescription>Rácios individuais no período seleccionado</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center p-3 rounded-lg bg-white/50 dark:bg-black/10">
                <Target className="h-5 w-5 mx-auto mb-1 text-green-500" />
                <p className="text-xl font-bold text-green-600">{userRatios.completionRate}%</p>
                <p className="text-xs text-muted-foreground">Taxa de Conclusão</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-white/50 dark:bg-black/10">
                <AlertTriangle className="h-5 w-5 mx-auto mb-1 text-red-500" />
                <p className="text-xl font-bold text-red-600">{userRatios.overdueRate}%</p>
                <p className="text-xs text-muted-foreground">Taxa de Atraso</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-white/50 dark:bg-black/10">
                <BarChart3 className="h-5 w-5 mx-auto mb-1 text-teal-500" />
                <p className="text-xl font-bold text-teal-600">{userRatios.efficiency}%</p>
                <p className="text-xs text-muted-foreground">Eficiência (Proc/Tarefa)</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-white/50 dark:bg-black/10">
                <ClipboardList className="h-5 w-5 mx-auto mb-1 text-blue-500" />
                <p className="text-xl font-bold">{userRatios.totalTasks}</p>
                <p className="text-xs text-muted-foreground">Total Tarefas</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ══ TOP PERFORMERS ════════════════════════════════ */}
      {selectedUser === "all" && topPerformers.length > 0 && topPerformers.some((p) => p.processes_moved + p.tasks_completed > 0) && (
        <Card className="bg-gradient-to-r from-emerald-50/50 to-teal-50/50 dark:from-emerald-950/20 dark:to-teal-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Trophy className="h-4 w-4 text-amber-500" />
              Top Performers
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-wrap gap-4">
              {topPerformers.map((tp, i) => {
                const score = tp.processes_moved + tp.tasks_completed;
                if (score === 0) return null;
                return (
                  <div key={tp.user_id} className="flex items-center gap-2">
                    <span className="text-xl">{medals[i]}</span>
                    <span className="font-semibold text-sm">{tp.name}</span>
                    <Badge variant="outline" className="text-xs">{score} acções</Badge>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ══ GRÁFICO DE BARRAS ════════════════════════════ */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-blue-500" />
            Tarefas Concluídas vs Atrasadas & Processos Movidos
          </CardTitle>
          <CardDescription>
            {selectedUser === "all"
              ? `${filteredUsers.length} colaborador${filteredUsers.length !== 1 ? "es" : ""} no período`
              : `Detalhe de ${selectedUserData?.name || "utilizador"}`}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <span className="ml-3 text-muted-foreground">A carregar dados...</span>
            </div>
          ) : chartData.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              Sem dados para o período seleccionado
            </div>
          ) : (
            <div className="h-[350px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 12 }}
                    interval={0}
                    angle={chartData.length > 8 ? -30 : 0}
                    textAnchor={chartData.length > 8 ? "end" : "middle"}
                    height={chartData.length > 8 ? 60 : 30}
                  />
                  <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    wrapperStyle={{ paddingTop: 8, fontSize: 12 }}
                  />
                  <Bar
                    dataKey="Tarefas Concluídas"
                    fill={CHART_COLORS.tasks_completed}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={40}
                  />
                  <Bar
                    dataKey="Tarefas Atrasadas"
                    fill={CHART_COLORS.tasks_overdue}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={40}
                  />
                  <Bar
                    dataKey="Processos Movidos"
                    fill={CHART_COLORS.processes_moved}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={40}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ══ TABELA REFINADA ══════════════════════════════ */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-5 w-5 text-blue-500" />
            Desempenho por Colaborador
          </CardTitle>
          <CardDescription>
            {filteredUsers.length} colaborador{filteredUsers.length !== 1 ? "es" : ""} no período
            {dateRangeLabel && <span className="ml-1">({dateRangeLabel})</span>}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <span className="ml-2 text-muted-foreground text-sm">A carregar dados...</span>
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">
              Sem dados de desempenho para o período seleccionado
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">#</TableHead>
                    <TableHead>Nome</TableHead>
                    <TableHead>Cargo</TableHead>
                    <TableHead className="text-center">Processos Avançados</TableHead>
                    <TableHead className="text-center">Tarefas Fechadas</TableHead>
                    <TableHead className="text-center">Tarefas Atrasadas</TableHead>
                    <TableHead className="text-center">Tarefas Pendentes</TableHead>
                    <TableHead className="text-center">Taxa Conclusão</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredUsers.map((u, idx) => {
                    const score = u.processes_moved + u.tasks_completed;
                    const totalTasks = u.tasks_completed + u.tasks_overdue + u.tasks_pending;
                    const completionRate = totalTasks > 0
                      ? ((u.tasks_completed / totalTasks) * 100).toFixed(0) + "%"
                      : "—";
                    return (
                      <TableRow
                        key={u.user_id}
                        className={`cursor-pointer hover:bg-muted/50 ${selectedUser === u.user_id ? "bg-blue-50/50 dark:bg-blue-950/20" : ""}`}
                        onClick={() => setSelectedUser(selectedUser === u.user_id ? "all" : u.user_id)}
                      >
                        <TableCell className="text-muted-foreground">{idx + 1}</TableCell>
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            {u.name}
                            {score >= 10 && (
                              <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300 text-[10px] px-1.5">
                                Top
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {roleLabels[u.role] || u.role}
                        </TableCell>
                        <TableCell className="text-center font-semibold text-teal-600">
                          {u.processes_moved}
                        </TableCell>
                        <TableCell className="text-center font-semibold text-green-600">
                          {u.tasks_completed}
                        </TableCell>
                        <TableCell
                          className={`text-center font-semibold ${
                            u.tasks_overdue > 0
                              ? "bg-red-50 dark:bg-red-950/30 text-red-600"
                              : "text-muted-foreground"
                          }`}
                        >
                          {u.tasks_overdue > 0 ? (
                            <span className="flex items-center justify-center gap-1">
                              <AlertTriangle className="h-3.5 w-3.5" />
                              {u.tasks_overdue}
                            </span>
                          ) : (
                            "0"
                          )}
                        </TableCell>
                        <TableCell
                          className={`text-center font-semibold ${
                            u.tasks_pending > 0
                              ? "bg-amber-50 dark:bg-amber-950/30 text-amber-600"
                              : "text-muted-foreground"
                          }`}
                        >
                          {u.tasks_pending > 0 ? u.tasks_pending : "0"}
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge
                            variant="outline"
                            className={
                              totalTasks > 0 && (u.tasks_completed / totalTasks) >= 0.8
                                ? "border-green-300 text-green-600"
                                : totalTasks > 0 && (u.tasks_completed / totalTasks) >= 0.5
                                ? "border-amber-300 text-amber-600"
                                : totalTasks > 0
                                ? "border-red-300 text-red-600"
                                : ""
                            }
                          >
                            {completionRate}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
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

export default TeamPerformanceDashboard;
