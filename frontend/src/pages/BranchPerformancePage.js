import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  TrendingUp,
  Zap,
  BarChart3,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { FullPageSkeleton } from "../components/ui/skeletons";
import { useTheme } from "../contexts/ThemeContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { formatCurrency as formatCurrencyShared } from "../utils/formatCurrency";
import { PageHeader } from "../components/shared/PageHeader";
import { Spinner } from "../components/ui/Spinner";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// ====================================================================
// Helpers
// ====================================================================

/** Formata um número como moeda europeia (ex: 250.000,00 €) */
function formatCurrency(value) {
  return formatCurrencyShared(value, { fallback: "0,00 €" });
}

/** Formata percentagem com 1 casa decimal */
function formatPercent(value) {
  if (value == null || isNaN(value)) return "0,0%";
  return `${value.toFixed(1).replace(".", ",")}%`;
}

/** Formata dias */
function formatDays(value) {
  if (value == null || isNaN(value) || value === 0) return "—";
  return `${value.toFixed(1).replace(".", ",")} dias`;
}

// ====================================================================
// Sortable Table Header
// ====================================================================

function SortableHeader({ label, sortKey, sortConfig, onSort }) {
  const isActive = sortConfig?.key === sortKey;
  const Icon = isActive ? (sortConfig.direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <th
      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider cursor-pointer hover:bg-muted/50 transition-colors select-none"
      onClick={() => onSort(sortKey)}
    >
      <div className="flex items-center gap-1.5">
        {label}
        <Icon className={`h-3.5 w-3.5 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
      </div>
    </th>
  );
}

// ====================================================================
// Top Card
// ====================================================================

function TopCard({ icon: Icon, label, value, subValue, color }) {
  const { isDark } = useTheme();
  return (
    <Card className={isDark ? "bg-slate-800/50 border-slate-700" : "bg-white border-slate-200"}>
      <CardContent className="p-5">
        <div className="flex items-start gap-3">
          <div className={`rounded-lg p-2.5 ${color}`}>
            <Icon className="h-5 w-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
              {label}
            </p>
            <p className="text-lg font-bold truncate">{value || "—"}</p>
            {subValue && (
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{subValue}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ====================================================================
// Approval Rate Bar
// ====================================================================

function ApprovalBar({ rate }) {
  const color =
    rate >= 70 ? "bg-emerald-500" : rate >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden max-w-[100px]">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${Math.min(rate, 100)}%` }}
        />
      </div>
      <span className="text-sm font-medium w-14 text-right">{formatPercent(rate)}</span>
    </div>
  );
}

// ====================================================================
// Main Component
// ====================================================================

export default function BranchPerformancePage() {
  const { isDark } = useTheme();
  const [sortConfig, setSortConfig] = useState({ key: "total_volume", direction: "desc" });

  // ── Server state via TanStack Query ──
  // fetchData é o refetch da query (usado no botão "Atualizar" e no retry).
  const {
    data,
    isFetching: loading,
    error: queryError,
    refetch: fetchData,
  } = useQuery({
    queryKey: ["stats-branches"],
    queryFn: async () => {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/stats/branches`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Erro ${res.status}: ${res.statusText}`);
      return res.json();
    },
  });
  // Manter `error` como string (o JSX renderiza-o diretamente).
  const error = queryError ? queryError.message : null;

  // ── Sort handler ──
  const handleSort = useCallback((key) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === "asc" ? "desc" : "asc" };
      }
      return { key, direction: "desc" };
    });
  }, []);

  // ── Sorted branches ──
  const sortedBranches = useMemo(() => {
    if (!data?.branches) return [];
    const sorted = [...data.branches];
    const { key, direction } = sortConfig;
    sorted.sort((a, b) => {
      const aVal = a[key] ?? 0;
      const bVal = b[key] ?? 0;
      // String comparison for bank_name / bank_branch
      if (typeof aVal === "string" && typeof bVal === "string") {
        return direction === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return direction === "asc" ? aVal - bVal : bVal - aVal;
    });
    return sorted;
  }, [data, sortConfig]);

  // ── Summary ──
  const { summary } = data || {};
  const fastestLabel = summary?.fastest_bank
    ? `${summary.fastest_bank.bank_branch} (${summary.fastest_bank.bank_name})`
    : null;
  const fastestSub = summary?.fastest_bank
    ? `${summary.fastest_bank.avg_closing_time_days} dias de fecho medio`
    : null;
  const volumeLabel = summary?.highest_volume_branch
    ? `${summary.highest_volume_branch.bank_branch} (${summary.highest_volume_branch.bank_name})`
    : null;
  const volumeSub = summary?.highest_volume_branch
    ? formatCurrency(summary.highest_volume_branch.total_volume)
    : null;

  // ── Loading / Error ──
  if (loading && !data) return <FullPageSkeleton />;
  if (error && !data) {
    return (
      <div className="p-8 text-center">
        <p className="text-destructive mb-4">{error}</p>
        <Button variant="outline" onClick={fetchData}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  return (
    <DashboardLayout title="Performance de Balcões">
    <div className="space-y-6 max-w-7xl mx-auto overflow-visible">
      {/* ── Header ── */}
      <PageHeader
        icon={Building2}
        title="Performance de Balcoes"
        description="Analise de eficiencia dos parceiros bancarios"
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            disabled={loading}
            className="w-fit"
          >
            {loading ? <Spinner size="sm" className="mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
            Atualizar
          </Button>
        }
      />

      {/* ── Top Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <TopCard
          icon={Zap}
          label="Banco Mais Rapido"
          value={fastestLabel}
          subValue={fastestSub}
          color="bg-blue-600"
        />
        <TopCard
          icon={TrendingUp}
          label="Balcao com Maior Volume"
          value={volumeLabel}
          subValue={volumeSub}
          color="bg-emerald-600"
        />
        <TopCard
          icon={BarChart3}
          label="Taxa de Aprovacao Global"
          value={formatPercent(summary?.global_approval_rate)}
          subValue={`${(data?.branches || []).length} balcoes com dados`}
          color="bg-purple-600"
        />
      </div>

      {/* ── DataTable ── */}
      <Card className={isDark ? "bg-slate-800/50 border-slate-700" : "bg-white border-slate-200"}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Building2 className="h-4 w-4" />
            Detalhe por Balcao
          </CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {sortedBranches.length === 0 ? (
            <div className="py-16 text-center text-muted-foreground">
              <Building2 className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Sem dados de balcoes disponiveis.</p>
              <p className="text-xs mt-1">
                Associe um banco aos processos para ver metricas aqui.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border">
                  <tr className={isDark ? "bg-slate-800" : "bg-slate-50"}>
                    <SortableHeader label="Balcao" sortKey="bank_branch" sortConfig={sortConfig} onSort={handleSort} />
                    <SortableHeader label="Banco" sortKey="bank_name" sortConfig={sortConfig} onSort={handleSort} />
                    <SortableHeader label="Processos Ativos" sortKey="active_processes" sortConfig={sortConfig} onSort={handleSort} />
                    <SortableHeader label="Taxa de Aprovacao" sortKey="approval_rate" sortConfig={sortConfig} onSort={handleSort} />
                    <SortableHeader label="Tempo Medio (Dias)" sortKey="avg_closing_time_days" sortConfig={sortConfig} onSort={handleSort} />
                    <SortableHeader label="Volume Financiado" sortKey="total_volume" sortConfig={sortConfig} onSort={handleSort} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {sortedBranches.map((branch, idx) => (
                    <tr
                      key={`${branch.bank_name}-${branch.bank_branch}-${idx}`}
                      className={`hover:${isDark ? "bg-slate-700/40" : "bg-slate-50"} transition-colors`}
                    >
                      <td className="px-4 py-3 font-medium">
                        <div className="flex items-center gap-2">
                          <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="truncate max-w-[180px]">{branch.bank_branch}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {branch.bank_name}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={branch.active_processes > 0 ? "default" : "secondary"}>
                          {branch.active_processes}
                        </Badge>
                        <span className="text-xs text-muted-foreground ml-1.5">
                          / {branch.total_processes}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <ApprovalBar rate={branch.approval_rate} />
                      </td>
                      <td className="px-4 py-3 font-medium">
                        {formatDays(branch.avg_closing_time_days)}
                      </td>
                      <td className="px-4 py-3 font-semibold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                        {formatCurrency(branch.total_volume)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                {/* ── Footer com totais ── */}
                <tfoot className="border-t-2 border-border font-semibold">
                  <tr className={isDark ? "bg-slate-800/70" : "bg-slate-100"}>
                    <td className="px-4 py-3" colSpan={2}>
                      Total ({sortedBranches.length} balcoes)
                    </td>
                    <td className="px-4 py-3">
                      {data.branches.reduce((s, b) => s + (b.active_processes || 0), 0)}
                      <span className="text-xs text-muted-foreground font-normal ml-1">
                        / {data.branches.reduce((s, b) => s + (b.total_processes || 0), 0)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ApprovalBar rate={summary?.global_approval_rate || 0} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">—</td>
                    <td className="px-4 py-3 text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                      {formatCurrency(data.branches.reduce((s, b) => s + (b.total_volume || 0), 0))}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
    </DashboardLayout>
  );
}