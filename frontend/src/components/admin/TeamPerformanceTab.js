/**
 * TeamPerformanceTab — Separador de Desempenho da Equipa.
 *
 * Mostra uma tabela shadcn/ui com métricas por colaborador:
 * - Nome, Cargo, Processos Avançados, Tarefas Fechadas, Tarefas Atrasadas
 * - Células de tarefas atrasadas destacadas a vermelho
 * - Seletor de datas para escolher o período de análise
 * - Resumo de KPIs no topo
 *
 * @param {string} token — JWT para chamadas à API
 */
import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCaption
} from "../ui/table";
import {
  Users, TrendingUp, CheckCircle, AlertTriangle, Clock, Loader2,
  Trophy, CalendarDays, RefreshCw
} from "lucide-react";
import { toast } from "sonner";
import { format, subDays } from "date-fns";
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

const TeamPerformanceTab = ({ token }) => {
  // Período por defeito: última semana
  const [startDate, setStartDate] = useState(() => format(subDays(new Date(), 7), "yyyy-MM-dd"));
  const [endDate, setEndDate] = useState(() => format(new Date(), "yyyy-MM-dd"));

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

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
      console.error("[TeamPerformance]", error);
      toast.error(error.message || "Erro ao carregar desempenho da equipa");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPerformance(startDate, endDate);
  }, []);

  // ── Handler: actualizar período ───────────────────────────
  const handleRefresh = () => {
    fetchPerformance(startDate, endDate);
  };

  // ── Quick-range buttons ───────────────────────────────────
  const setQuickRange = (days) => {
    const end = format(new Date(), "yyyy-MM-dd");
    const start = format(subDays(new Date(), days), "yyyy-MM-dd");
    setStartDate(start);
    setEndDate(end);
    fetchPerformance(start, end);
  };

  const summary = data?.summary || {};
  const users = data?.users || [];

  // ── Top performers (top 3 por score) ──────────────────────
  const topPerformers = [...users]
    .sort((a, b) => (b.processes_moved + b.tasks_completed) - (a.processes_moved + a.tasks_completed))
    .slice(0, 3);

  const medals = ["🥇", "🥈", "🥉"];

  return (
    <div className="space-y-4">
      {/* ── Date selector + quick ranges ──────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-blue-500" />
            Período de Análise
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
            <div className="flex items-center gap-2">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">De</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                />
              </div>
              <span className="text-muted-foreground mt-5">—</span>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Até</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                />
              </div>
            </div>

            <div className="flex items-center gap-2 mt-2 sm:mt-0">
              <Button variant="outline" size="sm" onClick={() => setQuickRange(7)}>
                Última semana
              </Button>
              <Button variant="outline" size="sm" onClick={() => setQuickRange(14)}>
                14 dias
              </Button>
              <Button variant="outline" size="sm" onClick={() => setQuickRange(30)}>
                30 dias
              </Button>
              <Button
                size="sm"
                onClick={handleRefresh}
                disabled={loading}
                className="gap-1.5"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Actualizar
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── KPI Summary Cards ─────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-teal-500">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-teal-50 dark:bg-teal-950/50 flex items-center justify-center shrink-0">
                <TrendingUp className="h-5 w-5 text-teal-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{summary.total_processes_moved ?? "—"}</p>
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
                <p className="text-2xl font-bold">{summary.total_tasks_completed ?? "—"}</p>
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
                <p className="text-2xl font-bold text-red-600">{summary.total_tasks_overdue ?? "—"}</p>
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
                <p className="text-2xl font-bold text-amber-600">{summary.total_tasks_pending ?? "—"}</p>
                <p className="text-xs text-muted-foreground">Tarefas Pendentes</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Top Performers ────────────────────────────────── */}
      {topPerformers.length > 0 && topPerformers.some(p => p.processes_moved + p.tasks_completed > 0) && (
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

      {/* ── Performance Table ─────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-5 w-5 text-blue-500" />
            Desempenho por Colaborador
          </CardTitle>
          <CardDescription>
            {users.length} colaborador{users.length !== 1 ? "es" : ""} no período
            {data?.period_start && (
              <span className="ml-1">
                ({format(new Date(data.period_start), "dd/MM/yy", { locale: pt })} —{" "}
                {format(new Date(data.period_end), "dd/MM/yy", { locale: pt })})
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <span className="ml-2 text-muted-foreground text-sm">A carregar dados...</span>
            </div>
          ) : users.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">
              Sem dados de desempenho para o período seleccionado
            </div>
          ) : (
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u, idx) => {
                  const score = u.processes_moved + u.tasks_completed;
                  return (
                    <TableRow key={u.user_id}>
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
                      {/* ── Atrasadas: destaque vermelho ── */}
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
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default TeamPerformanceTab;
