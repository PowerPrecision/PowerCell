/**
 * FinanceDashboard — Módulo Financeiro (Premium UI — Layout Expandido)
 *
 * Ecrã principal do módulo financeiro com visualização de dados:
 * 1. Resumo Financeiro — KPI Cards agregados
 * 2. Tabs de análise: Processos Financeiros, Imobiliária, Crédito, Mensal, Comissões, Distribuição
 *
 * NOTA: Os painéis de configuração foram movidos para /finance/settings
 * (FinanceSettingsPage). Esta página é agora apenas de visualização.
 *
 * Layout: ecrã inteiro (w-full max-w-7xl mx-auto)
 *
 * @context {AuthContext} — user.company como company_id (multi-tenant)
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  BarChart3,
  TrendingUp,
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
  CreditCard,
  Landmark,
  AlertTriangle,
  FileText,
  Receipt,
  Wallet,
  CircleDollarSign,
  RefreshCw,
  Filter,
  Pencil,
  Cog,
  Download,
  Printer,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import DashboardLayout from "../layouts/DashboardLayout";
import { useAuth } from "../contexts/AuthContext";
import { hasRole } from "../utils/roleUtils";
import {
  // Legacy dashboard APIs
  getFinanceSummary,
  getFinanceMonthly,
  getFinanceCommissions,
  getFinancePerformance,
  getFinanceConfig,
  // Fase 2 APIs
  getFinanceConfigs,
  getProcessFinances,
  updateProcessFinance,
  getProcessFinanceSummary,
  getPoolDistribution,
  exportPoolDistributionCSV,
  exportFinanceCommissionsCSV,
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
} from "recharts";
import SafeChartContainer from "../components/ui/SafeChartContainer";

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

const formatPct = (value) => {
  if (value == null || isNaN(value)) return "0%";
  return `${Number(value).toFixed(1)}%`;
};

// Mapeamento de status para labels e cores em pt-PT
const STATUS_MAP = {
  pending:  { label: "Pendente",  color: "bg-amber-100 text-amber-800 border-amber-200", dot: "bg-amber-500" },
  invoiced: { label: "Faturado",  color: "bg-sky-100 text-sky-800 border-sky-200",       dot: "bg-sky-500" },
  paid:     { label: "Pago",      color: "bg-emerald-100 text-emerald-800 border-emerald-200", dot: "bg-emerald-500" },
  cancelled:{ label: "Cancelado", color: "bg-gray-100 text-gray-600 border-gray-200",     dot: "bg-gray-400" },
};

// Próximo status no ciclo
const NEXT_STATUS = {
  pending: "invoiced",
  invoiced: "paid",
  paid: "paid",
  cancelled: "cancelled",
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
// CUSTOM TOOLTIP
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
// STAT CARD (Legacy — preservado para tabs Imobiliária/Crédito)
// ====================================================================

const FinanceStatCard = ({ title, value, subtitle, icon: Icon, color, variation, iconBg }) => (
  <Card>
    <CardContent className="p-5">
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className={`text-2xl font-bold mt-1 ${color || ""}`}>{value}</p>
          <div className="mt-1">
            {subtitle && (
              <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
            )}
            {variation !== undefined && <VariationIndicator value={variation} />}
          </div>
        </div>
        <div className={`p-3 rounded-xl ${iconBg || "bg-purple-50"}`}>
          <Icon className={`h-6 w-6 ${color || "text-purple-600"}`} />
        </div>
      </div>
    </CardContent>
  </Card>
);

// ====================================================================
// KPI CARD — Premium (Fase 2)
// ====================================================================

const KpiCard = ({ title, value, subtitle, icon: Icon, accent = "purple" }) => {
  const accents = {
    purple: { bar: "bg-purple-500", iconBg: "bg-purple-50", iconText: "text-purple-600" },
    amber:  { bar: "bg-amber-500",  iconBg: "bg-amber-50",  iconText: "text-amber-600" },
    sky:    { bar: "bg-sky-500",    iconBg: "bg-sky-50",    iconText: "text-sky-600" },
    emerald:{ bar: "bg-emerald-500",iconBg: "bg-emerald-50", iconText: "text-emerald-600" },
  };
  const a = accents[accent] || accents.purple;

  return (
    <Card className="overflow-visible relative">
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${a.bar}`} />
      <CardContent className="p-5 pl-6">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1 tracking-tight">{value}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-1.5 truncate">{subtitle}</p>
            )}
          </div>
          <div className={`p-3 rounded-xl ${a.iconBg}`}>
            <Icon className={`h-6 w-6 ${a.iconText}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// ====================================================================
// NOTA: HonorariosDialog e ConfigDialog foram movidos para
// FinanceSettingsPage (/finance/settings). Esta página é agora
// apenas de visualização de dados financeiros.
// ====================================================================

// ====================================================================
// STATUS BADGE — Componente de Estado
// ====================================================================

const StatusBadge = ({ status }) => {
  const s = STATUS_MAP[status] || STATUS_MAP.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${s.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
};

// ====================================================================
// RECEIPT MODAL — Recibo de Vencimento Individual
// ====================================================================

const ReceiptModal = ({ consultant, poolData, monthNames, onClose }) => {
  const receiptRef = useRef(null);
  const { user } = useAuth();

  if (!consultant || !poolData) return null;

  const companyName = user?.company === "power"
    ? "Power Real Estate"
    : user?.company === "precision"
    ? "Precision Crédito"
    : "PowerCell";

  const logoSrc = user?.company === "power"
    ? "/PowerLogo-removebg-preview.png"
    : user?.company === "precision"
    ? "/logoPrecision-removebg-preview.png"
    : "/PowerCell-default.png";

  const handlePrint = () => {
    window.print();
  };

  const monthLabel = monthNames[poolData.month] || "";
  const roleLabel = consultant.role === "consultor" ? "Consultor" : "Intermediário";

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)] print-modal-content">
        <DialogHeader className="no-print">
          <DialogTitle className="flex items-center gap-2">
            <Receipt className="h-5 w-5" />
            Recibo de Vencimento
          </DialogTitle>
          <DialogDescription>
            Pré-visualização do recibo para {consultant.name}
          </DialogDescription>
        </DialogHeader>

        {/* Receipt content — this is what gets printed */}
        <div ref={receiptRef} className="print-receipt">
          {/* Header */}
          <div className="text-center border-b-2 border-emerald-600 pb-4 mb-6">
            <img src={logoSrc} alt="Logo" className="h-12 w-auto mx-auto mb-3" />
            <h2 className="text-xl font-bold text-emerald-800">{companyName}</h2>
            <p className="text-sm text-muted-foreground mt-1">Recibo de Vencimento</p>
          </div>

          {/* Details */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Nome</p>
                <p className="font-semibold text-base">{consultant.name}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Cargo</p>
                <p className="font-semibold text-base">{roleLabel}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Período</p>
                <p className="font-semibold text-base">{monthLabel} {poolData.year}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Consultores no Pool</p>
                <p className="font-semibold text-base">{poolData.total_consultants}</p>
              </div>
            </div>

            {/* Values breakdown */}
            <div className="border rounded-lg overflow-hidden mt-6">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-emerald-50">
                    <th className="text-left py-3 px-4 font-medium text-emerald-800">Descrição</th>
                    <th className="text-right py-3 px-4 font-medium text-emerald-800">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t">
                    <td className="py-3 px-4">Salário Fixo</td>
                    <td className="py-3 px-4 text-right font-mono font-medium">
                      {formatCurrency(consultant.fixed_salary)}
                    </td>
                  </tr>
                  <tr className="border-t">
                    <td className="py-3 px-4">Comissões / Pool</td>
                    <td className="py-3 px-4 text-right font-mono font-medium">
                      {formatCurrency(consultant.variable_pay)}
                    </td>
                  </tr>
                  <tr className="border-t-2 border-emerald-600 bg-emerald-50">
                    <td className="py-3 px-4 font-bold text-emerald-800">Total a Receber</td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-emerald-800 text-lg">
                      {formatCurrency(consultant.total_monthly)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Footer */}
            <div className="mt-8 pt-4 border-t text-xs text-muted-foreground flex justify-between">
              <span>Documento gerado automaticamente pelo PowerCell</span>
              <span>{new Date().toLocaleDateString("pt-PT")}</span>
            </div>
          </div>
        </div>

        {/* Print button — hidden when printing */}
        <div className="flex justify-end gap-2 mt-4 no-print">
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
          <Button onClick={handlePrint} className="gap-2 bg-emerald-600 hover:bg-emerald-700">
            <Printer className="h-4 w-4" />
            Imprimir Recibo
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ====================================================================
// POOL DISTRIBUTION PANEL — Distribuição do Mês (Modelo Global Pool)
// ====================================================================

const PoolDistributionPanel = ({ companyId }) => {
  const { user } = useAuth();
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [poolData, setPoolData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [receiptConsultant, setReceiptConsultant] = useState(null);

  const isAdminOrCeo = hasRole(user, "admin") || hasRole(user, "ceo");

  const fetchPoolData = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getPoolDistribution({
        month: selectedMonth,
        year: selectedYear,
        company_id: companyId,
      });
      setPoolData(res.data);
    } catch (err) {
      console.error("Erro ao carregar distribuição do pool:", err);
      const rawDetail = err.response?.data?.detail;
      const msg = typeof rawDetail === 'string' ? rawDetail : (Array.isArray(rawDetail) ? rawDetail.map(e => e.msg || String(e)).join(' • ') : "Erro ao carregar distribuição do pool.");
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [companyId, selectedMonth, selectedYear]);

  useEffect(() => {
    fetchPoolData();
  }, [fetchPoolData]);

  const monthNames = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
  ];

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      const res = await exportPoolDistributionCSV({
        month: selectedMonth,
        year: selectedYear,
        company_id: companyId,
      });
      // Create blob from response and trigger download
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `fecho_${monthNames[selectedMonth].toLowerCase()}_${selectedYear}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Erro ao exportar CSV:", err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <Card className="border-emerald-200 bg-gradient-to-br from-emerald-50/50 to-white">
      <CardHeader>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <CircleDollarSign className="h-5 w-5 text-emerald-600" />
              Distribuição do Mês — Pool Global
            </CardTitle>
            <CardDescription className="mt-1">
              Comissões faturadas divididas igualmente pelos consultores ativos
            </CardDescription>
          </div>
          {/* PACOTE BA: overflow-visible + z-index para Selects não ficarem cortados */}
          <div className="flex items-center gap-2 flex-wrap relative z-30 overflow-visible">
            {/* Export CSV — Admin/CEO only */}
            {isAdminOrCeo && (
              <Button
                variant="outline"
                size="sm"
                className="gap-2 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                onClick={handleExportCSV}
                disabled={exporting || loading}
              >
                {exporting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Exportar para CSV
              </Button>
            )}
            <Select value={String(selectedMonth)} onValueChange={(v) => setSelectedMonth(parseInt(v))}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {monthNames.slice(1).map((name, idx) => (
                  <SelectItem key={idx + 1} value={String(idx + 1)}>{name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={String(selectedYear)} onValueChange={(v) => setSelectedYear(parseInt(v))}>
              <SelectTrigger className="w-[100px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 6 }, (_, i) => now.getFullYear() - i).map((yr) => (
                  <SelectItem key={yr} value={String(yr)}>{yr}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="icon" onClick={fetchPoolData} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading && !poolData ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-emerald-600" />
            <span className="ml-2 text-muted-foreground">A calcular distribuição...</span>
          </div>
        ) : error ? (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-red-200 bg-red-50 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        ) : poolData ? (
          <div className="space-y-6">
            {/* KPIs do Pool */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="rounded-xl border bg-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-100">
                    <Receipt className="h-5 w-5 text-emerald-600" />
                  </div>
                  <span className="text-sm text-muted-foreground">Total Faturado no Mês</span>
                </div>
                <p className="text-2xl font-bold text-emerald-700">
                  {formatCurrency(poolData.total_pool)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {poolData.count_processes} processo{poolData.count_processes !== 1 ? "s" : ""} faturado{poolData.count_processes !== 1 ? "s" : ""}
                </p>
                {(poolData.total_real_estate_commission > 0 || poolData.total_credit_commission > 0) && (
                  <div className="flex gap-3 mt-2 text-xs">
                    <span className="text-purple-600">Imob: {formatCurrency(poolData.total_real_estate_commission)}</span>
                    <span className="text-blue-600">Créd: {formatCurrency(poolData.total_credit_commission)}</span>
                  </div>
                )}
              </div>

              <div className="rounded-xl border bg-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-blue-100">
                    <Users className="h-5 w-5 text-blue-600" />
                  </div>
                  <span className="text-sm text-muted-foreground">Consultores Ativos</span>
                </div>
                <p className="text-2xl font-bold text-blue-700">
                  {poolData.total_consultants}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Consultores e intermediários da empresa
                </p>
              </div>

              <div className="rounded-xl border-2 border-emerald-300 bg-emerald-50/50 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-200">
                    <Wallet className="h-5 w-5 text-emerald-700" />
                  </div>
                  <span className="text-sm font-medium text-emerald-800">Valor por Consultor</span>
                </div>
                <p className="text-3xl font-bold text-emerald-700">
                  {formatCurrency(poolData.pool_per_consultant)}
                </p>
                <p className="text-xs text-emerald-600 mt-1">
                  = {formatCurrency(poolData.total_pool)} ÷ {poolData.total_consultants} consultores
                </p>
              </div>
            </div>

            {/* Lista de Consultores — com breakdown Fixo + Variável + Total + Recibo */}
            {poolData.consultants && poolData.consultants.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  Consultores no Pool — {monthNames[poolData.month]} {poolData.year}
                </h4>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/50">
                        <th className="text-left py-2.5 px-3 font-medium text-muted-foreground">Consultor</th>
                        <th className="text-right py-2.5 px-3 font-medium text-muted-foreground">Fixo</th>
                        <th className="text-right py-2.5 px-3 font-medium text-muted-foreground">Comissões/Pool</th>
                        <th className="text-right py-2.5 px-3 font-medium text-emerald-700 font-semibold">Total Mensal</th>
                        <th className="text-center py-2.5 px-3 font-medium text-muted-foreground">Recibo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {poolData.consultants.map((c) => (
                        <tr key={c.id} className="border-t hover:bg-muted/30 transition-colors">
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-700 font-semibold text-xs">
                                {c.name?.charAt(0)?.toUpperCase() || "?"}
                              </div>
                              <div>
                                <p className="font-medium text-sm">{c.name}</p>
                                <p className="text-xs text-muted-foreground capitalize">{c.role}</p>
                              </div>
                            </div>
                          </td>
                          <td className="text-right py-2.5 px-3 font-mono text-sm text-slate-600">
                            {formatCurrency(c.fixed_salary)}
                          </td>
                          <td className="text-right py-2.5 px-3 font-mono text-sm text-slate-600">
                            {formatCurrency(c.variable_pay)}
                          </td>
                          <td className="text-right py-2.5 px-3 font-mono text-sm font-semibold text-emerald-700">
                            {formatCurrency(c.total_monthly)}
                          </td>
                          <td className="text-center py-2.5 px-3">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="gap-1.5 text-emerald-600 hover:text-emerald-800 hover:bg-emerald-50 h-8"
                              onClick={() => setReceiptConsultant(c)}
                              title="Imprimir Recibo"
                            >
                              <Printer className="h-4 w-4" />
                              <span className="hidden sm:inline text-xs">Recibo</span>
                            </Button>
                          </td>
                        </tr>
                      ))}
                      {/* Totals row */}
                      <tr className="border-t-2 border-emerald-200 bg-emerald-50/50">
                        <td className="py-2.5 px-3 font-semibold text-emerald-800">Total</td>
                        <td className="text-right py-2.5 px-3 font-mono text-sm font-semibold text-slate-700">
                          {formatCurrency(poolData.total_base_salaries)}
                        </td>
                        <td className="text-right py-2.5 px-3 font-mono text-sm font-semibold text-slate-700">
                          {formatCurrency(poolData.total_variable_pay)}
                        </td>
                        <td className="text-right py-2.5 px-3 font-mono text-sm font-bold text-emerald-700">
                          {formatCurrency(poolData.total_grand_monthly)}
                        </td>
                        <td />
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {poolData.total_pool === 0 && (
              <div className="text-center py-6 text-muted-foreground">
                <Receipt className="h-10 w-10 mx-auto mb-2 opacity-30" />
                <p className="text-sm">Sem comissões faturadas em {monthNames[poolData.month]} {poolData.year}.</p>
              </div>
            )}
          </div>
        ) : null}
      </CardContent>

      {/* Receipt Modal */}
      {receiptConsultant && poolData && (
        <ReceiptModal
          consultant={receiptConsultant}
          poolData={poolData}
          monthNames={monthNames}
          onClose={() => setReceiptConsultant(null)}
        />
      )}
    </Card>
  );
};

// ====================================================================
// AREA DETAIL TAB (Imobiliária ou Crédito — Legacy preservado)
// ====================================================================

const AreaDetail = ({ area, data, monthlyData, performanceData, selectedYear }) => {
  const navigate = useNavigate();
  const isImob = area === "imobiliaria";
  const color = isImob ? "text-purple-600" : "text-blue-600";
  const iconBg = isImob ? "bg-purple-50" : "bg-blue-50";
  const label = isImob ? "Imobiliária" : "Crédito";

  if (!data) return null;

  const areaChartData = (monthlyData || []).map((m) => ({
    name: m.month_label,
    Receita: isImob ? m.imob_receita : m.cred_receita,
    Comissões: isImob ? m.imob_comissoes : m.cred_comissoes,
    "Lucro Líquido": isImob ? m.imob_lucro_liquido : m.cred_lucro_liquido,
  }));

  const varPrefix = isImob ? "imob_" : "cred_";
  const varReceita = performanceData?.variations?.[`${varPrefix}receita`];
  const varLucro = performanceData?.variations?.[`${varPrefix}lucro`];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <FinanceStatCard
          title={`Receita ${label}`}
          value={formatCurrency(data.total_receita)}
          subtitle={`${data.processos_com_comissao} processos com comissão`}
          icon={TrendingUp}
          color={color}
          variation={varReceita}
          iconBg={iconBg}
        />
        <FinanceStatCard
          title="Comissões Pagas"
          value={formatCurrency(data.comissoes_pagas_consultores)}
          subtitle={`Consultor: ${formatPct(data.pct_consultor)} | Agência: ${formatPct(data.pct_agencia)}`}
          icon={Users}
          color="text-orange-600"
          iconBg="bg-orange-50"
        />
        <FinanceStatCard
          title="Lucro Bruto Agência"
          value={formatCurrency(data.lucro_bruto_agencia)}
          subtitle={`Impostos: ${formatCurrency(data.total_impostos)} (${formatPct(data.pct_impostos)})`}
          icon={Landmark}
          color="text-red-600"
          iconBg="bg-red-50"
        />
        <FinanceStatCard
          title="Lucro Líquido"
          value={formatCurrency(data.lucro_liquido_agencia)}
          subtitle={`Margem: ${formatPct(data.taxa_margem)}`}
          icon={DollarSign}
          color="text-green-600"
          iconBg="bg-green-50"
          variation={varLucro}
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-xs text-muted-foreground">Processos</p>
            <p className="text-xl font-bold mt-1">{data.total_processos}</p>
            <p className="text-[10px] text-muted-foreground">concluídos</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-xs text-muted-foreground">Comissão Média</p>
            <p className="text-xl font-bold mt-1">{formatCurrency(data.valor_medio_comissao)}</p>
            <p className="text-[10px] text-muted-foreground">por processo</p>
          </CardContent>
        </Card>
        {isImob && (
          <Card className="col-span-2">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-muted-foreground">Valor Total Imóveis</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(data.total_valor_imoveis)}</p>
              <p className="text-[10px] text-muted-foreground">volume de negócios</p>
            </CardContent>
          </Card>
        )}
        {!isImob && (
          <Card className="col-span-2">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-muted-foreground">Montante Total Crédito</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(data.total_credit_montante)}</p>
              <p className="text-[10px] text-muted-foreground">financiado</p>
            </CardContent>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Evolução Mensal — {label} ({selectedYear})
          </CardTitle>
          <CardDescription>Receita, comissões e lucro líquido</CardDescription>
        </CardHeader>
        <CardContent>
          <SafeChartContainer className="h-[200px] sm:h-[300px] min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={areaChartData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="name" fontSize={12} />
                <YAxis
                  fontSize={12}
                  tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)}
                />
                <Tooltip content={<FinanceTooltip />} />
                <Legend />
                <Bar dataKey="Receita" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Comissões" fill="#f97316" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Lucro Líquido" fill="#22c55e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </SafeChartContainer>
        </CardContent>
      </Card>

      {data.processes && data.processes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Processos — {label}
            </CardTitle>
            <CardDescription>Processos concluídos ordenados por comissão</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium text-muted-foreground">Processo</th>
                    <th className="text-left py-2 px-3 font-medium text-muted-foreground">Cliente</th>
                    <th className="text-left py-2 px-3 font-medium text-muted-foreground">Tipo</th>
                    <th className="text-right py-2 px-3 font-medium text-muted-foreground">Comissão</th>
                    <th className="text-right py-2 px-3 font-medium text-muted-foreground">Comiss. Consultor</th>
                    <th className="text-right py-2 px-3 font-medium text-green-600">Lucro Agência</th>
                    {isImob && (
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Valor Imóvel</th>
                    )}
                    {!isImob && (
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Montante Crédito</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {data.processes
                    .filter((p) => p.comissao > 0)
                    .slice(0, 20)
                    .map((p, idx) => (
                      <tr
                        key={p.id || idx}
                        className="border-b hover:bg-muted/50 cursor-pointer"
                        onClick={() => p.id && navigate(`/processo/${p.id}`)}
                      >
                        <td className="py-2 px-3 font-mono text-xs">#{p.process_number || "—"}</td>
                        <td className="py-2 px-3">{p.client_name}</td>
                        <td className="py-2 px-3">
                          <Badge variant="outline" className="text-xs">{p.process_type || "—"}</Badge>
                        </td>
                        <td className="py-2 px-3 text-right font-semibold">{formatCurrency(p.comissao)}</td>
                        <td className="py-2 px-3 text-right text-orange-600">{formatCurrency(p.comissao_consultor)}</td>
                        <td className="py-2 px-3 text-right font-semibold text-green-600">{formatCurrency(p.lucro_agencia)}</td>
                        {isImob && (
                          <td className="py-2 px-3 text-right">{p.valor_imovel > 0 ? formatCurrency(p.valor_imovel) : "—"}</td>
                        )}
                        {!isImob && (
                          <td className="py-2 px-3 text-right">{p.montante_credito > 0 ? formatCurrency(p.montante_credito) : "—"}</td>
                        )}
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// ====================================================================
// PROCESS FINANCES TAB — Fase 2 (KPI Cards + Tabela Histórico)
// ====================================================================

const ProcessFinancesTab = ({ companyId }) => {
  const navigate = useNavigate();
  const [finances, setFinances] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [updatingId, setUpdatingId] = useState(null);

  const fetchData = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError(null);
    try {
      const [finRes, sumRes] = await Promise.all([
        getProcessFinances({ company_id: companyId }),
        getProcessFinanceSummary({ company_id: companyId }),
      ]);
      setFinances(finRes.data?.finances || []);
      setSummary(sumRes.data || null);
    } catch (err) {
      console.error("Erro ao carregar ProcessFinances:", err);
      const rawDetail2 = err.response?.data?.detail;
      const msg2 = typeof rawDetail2 === 'string' ? rawDetail2 : (Array.isArray(rawDetail2) ? rawDetail2.map(e => e.msg || String(e)).join(' • ') : "Erro ao carregar registos financeiros.");
      setError(msg2);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Alterar status de um registo (PUT)
  const handleStatusChange = async (financeId, newStatus) => {
    setUpdatingId(financeId);
    try {
      await updateProcessFinance(financeId, { status: newStatus });
      // Atualizar localmente
      setFinances((prev) =>
        prev.map((f) => (f.id === financeId ? { ...f, status: newStatus } : f))
      );
      // Refetch summary
      const sumRes = await getProcessFinanceSummary({ company_id: companyId });
      setSummary(sumRes.data || null);
    } catch (err) {
      console.error("Erro ao atualizar status:", err);
    } finally {
      setUpdatingId(null);
    }
  };

  // Filtrar por status
  const filtered = statusFilter === "all"
    ? finances
    : finances.filter((f) => f.status === statusFilter);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
        <span className="ml-2 text-muted-foreground">A carregar registos financeiros...</span>
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-red-200 bg-red-50">
        <CardContent className="p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-red-500 mx-auto mb-2" />
          <p className="text-red-700 text-sm">{error}</p>
          <Button variant="outline" size="sm" className="mt-3 gap-2" onClick={fetchData}>
            <RefreshCw className="h-4 w-4" />
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Total Faturado"
          value={formatCurrency(summary?.total_paid || 0)}
          subtitle={`${summary?.count_paid || 0} processos pagos`}
          icon={CircleDollarSign}
          accent="emerald"
        />
        <KpiCard
          title="A Receber (Pendente)"
          value={formatCurrency(summary?.total_pending || 0)}
          subtitle={`${summary?.count_pending || 0} processos pendentes`}
          icon={Wallet}
          accent="amber"
        />
        <KpiCard
          title="Impostos (IVA)"
          value={formatCurrency(
            (summary?.total_expected || 0) - (summary?.total_paid || 0) - (summary?.total_pending || 0)
          )}
          subtitle={`Base: ${formatCurrency(summary?.total_expected || 0)}`}
          icon={Receipt}
          accent="sky"
        />
        <KpiCard
          title="Total Processos Ganhos"
          value={formatNumber(
            (summary?.count_paid || 0) +
            (summary?.count_pending || 0) +
            (summary?.count_invoiced || 0)
          )}
          subtitle={`${summary?.count_invoiced || 0} faturados`}
          icon={FileText}
          accent="purple"
        />
      </div>

      {/* Filtro + Header da Tabela */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <CardTitle className="text-base">Histórico de Processos Financeiros</CardTitle>
              <CardDescription>
                {filtered.length} registo{filtered.length !== 1 ? "s" : ""} encontrado{filtered.length !== 1 ? "s" : ""}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue placeholder="Filtrar estado" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos os estados</SelectItem>
                  <SelectItem value="pending">Pendente</SelectItem>
                  <SelectItem value="invoiced">Faturado</SelectItem>
                  <SelectItem value="paid">Pago</SelectItem>
                  <SelectItem value="cancelled">Cancelado</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filtered.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
              <p className="text-muted-foreground text-sm">Sem registos financeiros para mostrar.</p>
              <p className="text-muted-foreground text-xs mt-1">
                Os registos são criados automaticamente quando um processo é fechado.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-background z-10">
                  <tr className="border-b">
                    <th className="text-left py-3 px-3 font-medium text-muted-foreground">Processo</th>
                    <th className="text-left py-3 px-3 font-medium text-muted-foreground">Cliente</th>
                    <th className="text-right py-3 px-3 font-medium text-muted-foreground">Valor Base</th>
                    <th className="text-center py-3 px-3 font-medium text-muted-foreground">Honorário</th>
                    <th className="text-right py-3 px-3 font-medium text-muted-foreground">Comissão</th>
                    <th className="text-right py-3 px-3 font-medium text-muted-foreground">IVA</th>
                    <th className="text-right py-3 px-3 font-medium text-muted-foreground">Total a Faturar</th>
                    <th className="text-center py-3 px-3 font-medium text-muted-foreground">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((f) => (
                    <tr
                      key={f.id}
                      className="border-b hover:bg-muted/30 transition-colors"
                    >
                      <td className="py-3 px-3">
                        <button
                          onClick={() => navigate(`/processo/${f.process_id}`)}
                          className="text-purple-600 hover:text-purple-800 hover:underline font-mono text-xs"
                        >
                          #{f.process_id?.slice(0, 8) || "—"}
                        </button>
                      </td>
                      <td className="py-3 px-3">
                        <button
                          onClick={() => navigate(`/cliente/${f.client_id}`)}
                          className="text-sm hover:underline"
                        >
                          {f.client_name || f.client_id?.slice(0, 8) || "—"}
                        </button>
                      </td>
                      <td className="py-3 px-3 text-right">
                        {formatCurrency(f.base_business_value)}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <Badge variant="outline" className="text-xs font-medium">
                          {f.applied_fee_type === "percentage"
                            ? `${f.applied_fee_value}%`
                            : formatCurrency(f.applied_fee_value)}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-right font-semibold">
                        {formatCurrency(f.expected_commission)}
                      </td>
                      <td className="py-3 px-3 text-right text-muted-foreground">
                        {formatCurrency(f.tax_amount)}
                      </td>
                      <td className="py-3 px-3 text-right font-semibold text-emerald-700">
                        {formatCurrency(f.total_with_tax)}
                      </td>
                      <td className="py-3 px-3 text-center">
                        {updatingId === f.id ? (
                          <Loader2 className="h-4 w-4 animate-spin mx-auto text-purple-600" />
                        ) : (
                          <button
                            onClick={() => handleStatusChange(f.id, NEXT_STATUS[f.status])}
                            title={`Clique para alterar para ${STATUS_MAP[NEXT_STATUS[f.status]]?.label}`}
                            className="inline-flex items-center gap-1 cursor-pointer hover:scale-105 transition-transform"
                          >
                            <StatusBadge status={f.status} />
                            <Pencil className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="sticky bottom-0 bg-background border-t-2">
                  <tr className="font-semibold text-sm">
                    <td className="py-3 px-3" colSpan={2}>Total</td>
                    <td className="py-3 px-3 text-right">
                      {formatCurrency(filtered.reduce((s, f) => s + (f.base_business_value || 0), 0))}
                    </td>
                    <td />
                    <td className="py-3 px-3 text-right">
                      {formatCurrency(filtered.reduce((s, f) => s + (f.expected_commission || 0), 0))}
                    </td>
                    <td className="py-3 px-3 text-right text-muted-foreground">
                      {formatCurrency(filtered.reduce((s, f) => s + (f.tax_amount || 0), 0))}
                    </td>
                    <td className="py-3 px-3 text-right text-emerald-700">
                      {formatCurrency(filtered.reduce((s, f) => s + (f.total_with_tax || 0), 0))}
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ====================================================================
// ConfigDialog REMOVIDO — movido para FinanceSettingsPage
// ====================================================================

// ====================================================================
// MAIN COMPONENT
// ====================================================================

const FinanceDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dados (legacy)
  const [summary, setSummary] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [commissions, setCommissions] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [, setConfig] = useState(null);
  const [distributionModel, setDistributionModel] = useState("individual_split");
  const [commissionsReceiptConsultant, setCommissionsReceiptConsultant] = useState(null);

  // Filtros
  const currentYear = new Date().getFullYear();
  const yearParam = parseInt(searchParams.get("year")) || currentYear;
  const [selectedYear, setSelectedYear] = useState(yearParam);

  // company_id do utilizador autenticado
  const companyId = user?.company || "default";

  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { year: selectedYear };
      const [summaryRes, monthlyRes, commissionsRes, performanceRes, configRes, financeConfigsRes] =
        await Promise.all([
          getFinanceSummary(params),
          getFinanceMonthly(params),
          getFinanceCommissions({ ...params, company_id: companyId }),
          getFinancePerformance(params),
          getFinanceConfig(),
          getFinanceConfigs({ company_id: companyId }),
        ]);
      setSummary(summaryRes.data);
      setMonthly(monthlyRes.data);
      setCommissions(commissionsRes.data);
      setPerformance(performanceRes.data);
      if (configRes.data?.config) {
        setConfig(configRes.data.config);
      }
      const cfgs = financeConfigsRes.data?.configs || [];
      if (cfgs.length > 0 && cfgs[0].distribution_model) {
        setDistributionModel(cfgs[0].distribution_model);
      }
    } catch (err) {
      console.error("Erro ao carregar dados financeiros:", err);
      const rawDetail3 = err.response?.data?.detail;
      const msg3 = typeof rawDetail3 === 'string' ? rawDetail3 : (Array.isArray(rawDetail3) ? rawDetail3.map(e => e.msg || String(e)).join(' • ') : "Erro ao carregar dados financeiros.");
      setError(msg3);
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


  // Chart data para comparação imob vs cred
  const comparisonChartData = (monthly?.monthly || []).map((m) => ({
    name: m.month_label,
    Imobiliária: m.imob_receita,
    Crédito: m.cred_receita,
  }));

  if (loading) {
    return (
      <DashboardLayout>
        <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
            <span className="text-muted-foreground">A carregar dados financeiros...</span>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // Verificar se o utilizador é admin/CEO para mostrar o link de gestão
  const isAdminOrCeo = hasRole(user, "admin") || hasRole(user, "ceo");

  return (
    <DashboardLayout>
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <BarChart3 className="h-6 w-6 text-purple-600" />
              Dashboard Financeiro
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Visão financeira por área de negócio — relatórios e KPIs
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Link para Gestão Financeira (admin/CEO only) */}
            {isAdminOrCeo && (
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => navigate("/finance/settings")}
              >
                <Cog className="h-4 w-4" />
                Gestão Financeira
              </Button>
            )}

            <div className="flex items-center gap-2">
              <Button variant="outline" size="icon" onClick={() => handleYearChange(-1)} disabled={selectedYear <= 2020}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="flex items-center gap-2 px-4 py-2 border rounded-lg bg-background">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="font-semibold">{selectedYear}</span>
              </div>
              <Button variant="outline" size="icon" onClick={() => handleYearChange(1)} disabled={selectedYear >= currentYear + 1}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-4">
              <p className="text-red-600 text-sm">{error}</p>
            </CardContent>
          </Card>
        )}

        {/* KPIs Globais — layout expandido */}
        {summary && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
            <FinanceStatCard
              title="Receita Total"
              value={formatCurrency(summary.global?.total_receita)}
              subtitle="Imobiliária + Crédito"
              icon={TrendingUp}
              color="text-green-600"
              iconBg="bg-green-50"
              variation={performance?.variations?.receita}
            />
            <FinanceStatCard
              title="Comissões Pagas"
              value={formatCurrency(summary.global?.total_comissoes_pagas)}
              subtitle="Total a colaboradores"
              icon={Users}
              color="text-orange-600"
              iconBg="bg-orange-50"
            />
            <FinanceStatCard
              title="Lucro Líquido Total"
              value={formatCurrency(summary.global?.total_lucro_liquido)}
              subtitle={`Margem: ${formatPct(summary.global?.taxa_margem)}`}
              icon={DollarSign}
              color="text-blue-600"
              iconBg="bg-blue-50"
              variation={performance?.variations?.lucro}
            />
            <FinanceStatCard
              title="Total Impostos"
              value={formatCurrency(summary.global?.total_impostos)}
              subtitle={`${summary.global?.total_processos} processos concluídos`}
              icon={Landmark}
              color="text-red-600"
              iconBg="bg-red-50"
            />
          </div>
        )}

        {/* Tabs — layout expandido sem tabs de configuração */}
        <Tabs defaultValue="processos" className="space-y-4">
          <TabsList className="flex flex-wrap gap-1 h-auto p-1">
            <TabsTrigger value="processos" className="gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              Processos Financeiros
            </TabsTrigger>
            <TabsTrigger value="imobiliaria" className="gap-1.5">
              <Building2 className="h-3.5 w-3.5" />
              Imobiliária
            </TabsTrigger>
            <TabsTrigger value="credito" className="gap-1.5">
              <CreditCard className="h-3.5 w-3.5" />
              Crédito
            </TabsTrigger>
            <TabsTrigger value="monthly" className="gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              Mensal
            </TabsTrigger>
            <TabsTrigger value="commissions" className="gap-1.5">
              <Users className="h-3.5 w-3.5" />
              Comissões
            </TabsTrigger>
            {distributionModel === "global_pool" && (
              <TabsTrigger value="distribution" className="gap-1.5">
                <CircleDollarSign className="h-3.5 w-3.5" />
                Distribuição
              </TabsTrigger>
            )}
          </TabsList>

          {/* TAB: Processos Financeiros (anteriormente Honorários & Processos) */}
          <TabsContent value="processos">
            <ProcessFinancesTab companyId={companyId} />
          </TabsContent>

          {/* TAB: Imobiliária — ConfigDialog removido (ver /finance/settings) */}
          <TabsContent value="imobiliaria">
            <AreaDetail
              area="imobiliaria"
              data={summary?.imobiliaria}
              monthlyData={monthly?.monthly}
              performanceData={performance}
              selectedYear={selectedYear}
            />
          </TabsContent>

          {/* TAB: Crédito — ConfigDialog removido (ver /finance/settings) */}
          <TabsContent value="credito">
            <AreaDetail
              area="credito"
              data={summary?.credito}
              monthlyData={monthly?.monthly}
              performanceData={performance}
              selectedYear={selectedYear}
            />
          </TabsContent>

          {/* TAB: Mensal */}
          <TabsContent value="monthly" className="space-y-4">
            {monthly && (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Imobiliária vs Crédito — {selectedYear}</CardTitle>
                    <CardDescription>Receita mensal por área de negócio</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <SafeChartContainer className="h-[200px] sm:h-[300px] min-w-0">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={comparisonChartData}>
                          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                          <XAxis dataKey="name" fontSize={12} />
                          <YAxis fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)} />
                          <Tooltip content={<FinanceTooltip />} />
                          <Legend />
                          <Bar dataKey="Imobiliária" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="Crédito" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </SafeChartContainer>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Detalhe Mensal — {selectedYear}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3 font-medium text-muted-foreground">Mês</th>
                            <th className="text-right py-2 px-3 font-medium text-muted-foreground">Proc.</th>
                            <th className="text-right py-2 px-3 font-medium text-purple-600">Imob. Receita</th>
                            <th className="text-right py-2 px-3 font-medium text-purple-700">Imob. Lucro</th>
                            <th className="text-right py-2 px-3 font-medium text-blue-600">Créd. Receita</th>
                            <th className="text-right py-2 px-3 font-medium text-blue-700">Créd. Lucro</th>
                            <th className="text-right py-2 px-3 font-medium text-green-600">Total Lucro</th>
                          </tr>
                        </thead>
                        <tbody>
                          {monthly.monthly.map((m) => (
                            <tr key={m.month} className="border-b hover:bg-muted/50">
                              <td className="py-2 px-3 font-medium">{m.month_label}</td>
                              <td className="py-2 px-3 text-right">{m.num_processos}</td>
                              <td className="py-2 px-3 text-right">{m.imob_receita > 0 ? formatCurrency(m.imob_receita) : "—"}</td>
                              <td className="py-2 px-3 text-right">{m.imob_lucro_liquido > 0 ? formatCurrency(m.imob_lucro_liquido) : "—"}</td>
                              <td className="py-2 px-3 text-right">{m.cred_receita > 0 ? formatCurrency(m.cred_receita) : "—"}</td>
                              <td className="py-2 px-3 text-right">{m.cred_lucro_liquido > 0 ? formatCurrency(m.cred_lucro_liquido) : "—"}</td>
                              <td className="py-2 px-3 text-right font-semibold text-green-600">
                                {formatCurrency((m.imob_lucro_liquido || 0) + (m.cred_lucro_liquido || 0))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr className="font-bold border-t-2">
                            <td className="py-3 px-3">Total</td>
                            <td className="py-3 px-3 text-right">{monthly.totals?.total_processos}</td>
                            <td className="py-3 px-3 text-right text-purple-600">{formatCurrency(monthly.totals?.total_imob_receita)}</td>
                            <td className="py-3 px-3 text-right text-purple-700">{formatCurrency(monthly.totals?.total_imob_lucro)}</td>
                            <td className="py-3 px-3 text-right text-blue-600">{formatCurrency(monthly.totals?.total_cred_receita)}</td>
                            <td className="py-3 px-3 text-right text-blue-700">{formatCurrency(monthly.totals?.total_cred_lucro)}</td>
                            <td className="py-3 px-3 text-right text-green-600">
                              {formatCurrency((monthly.totals?.total_imob_lucro || 0) + (monthly.totals?.total_cred_lucro || 0))}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
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
                    subtitle="Pagamentos variáveis a colaboradores"
                    icon={Users}
                    color="text-orange-600"
                    iconBg="bg-orange-50"
                  />
                  <FinanceStatCard
                    title="Colaboradores Activos"
                    value={commissions.collaborators.length}
                    subtitle={commissions.distribution_model === "global_pool"
                      ? "Modelo: Pool Global"
                      : "Modelo: Tradicional (Split)"}
                    icon={Users}
                    color="text-blue-600"
                    iconBg="bg-blue-50"
                  />
                </div>

                {/* KPIs do modelo híbrido */}
                {(commissions.total_base_salaries > 0 || commissions.total_grand_monthly > 0) && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <FinanceStatCard
                      title="Total Vencimentos Fixos"
                      value={formatCurrency(commissions.total_base_salaries || 0)}
                      subtitle="Soma dos salários fixos mensais"
                      icon={Wallet}
                      color="text-slate-600"
                      iconBg="bg-slate-50"
                    />
                    <FinanceStatCard
                      title="Total Variável"
                      value={formatCurrency(commissions.total_variable_pay || 0)}
                      subtitle={commissions.distribution_model === "global_pool" ? "Pool Global" : "Comissões Individuais"}
                      icon={Receipt}
                      color="text-orange-600"
                      iconBg="bg-orange-50"
                    />
                    <FinanceStatCard
                      title="Total Geral Mensal"
                      value={formatCurrency(commissions.total_grand_monthly || 0)}
                      subtitle="Fixo + Variável"
                      icon={CircleDollarSign}
                      color="text-emerald-600"
                      iconBg="bg-emerald-50"
                    />
                  </div>
                )}

                <Card>
                  <CardHeader>
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                      <div>
                        <CardTitle className="text-base">Ranking de Colaboradores — {selectedYear}</CardTitle>
                        <CardDescription>
                          Comissões por área de negócio (modelo híbrido: Fixo + Variável)
                        </CardDescription>
                      </div>
                      {/* Exportar para CSV — Admin/CEO only */}
                      {isAdminOrCeo && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-2 border-emerald-300 text-emerald-700 hover:bg-emerald-50 shrink-0"
                          onClick={async () => {
                            try {
                              const res = await exportFinanceCommissionsCSV({
                                year: selectedYear,
                                company_id: companyId,
                              });
                              const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
                              const url = window.URL.createObjectURL(blob);
                              const link = document.createElement("a");
                              link.href = url;
                              link.setAttribute("download", `comissoes_${selectedYear}_${companyId}.csv`);
                              document.body.appendChild(link);
                              link.click();
                              document.body.removeChild(link);
                              window.URL.revokeObjectURL(url);
                            } catch (err) {
                              console.error("Erro ao exportar CSV:", err);
                            }
                          }}
                        >
                          <Download className="h-4 w-4" />
                          Exportar para CSV
                        </Button>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    {commissions.collaborators.length === 0 ? (
                      <p className="text-center text-muted-foreground py-8">Sem dados de comissões para este período.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b">
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground w-8">#</th>
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground">Colaborador</th>
                              <th className="text-left py-2 px-3 font-medium text-muted-foreground">Função</th>
                              <th className="text-right py-2 px-3 font-medium text-muted-foreground">Processos</th>
                              <th className="text-right py-2 px-3 font-medium text-purple-600">Imobiliária</th>
                              <th className="text-right py-2 px-3 font-medium text-blue-600">Crédito</th>
                              <th className="text-right py-2 px-3 font-medium text-muted-foreground">Salário Fixo</th>
                              <th className="text-right py-2 px-3 font-medium text-muted-foreground">Comissões/Pool</th>
                              <th className="text-right py-2 px-3 font-medium text-emerald-700 font-semibold">Total Mensal</th>
                              <th className="text-center py-2 px-3 font-medium text-muted-foreground">Recibo</th>
                            </tr>
                          </thead>
                          <tbody>
                            {commissions.collaborators.map((c, idx) => (
                              <tr key={c.name} className="border-b hover:bg-muted/50">
                                <td className="py-2 px-3 text-muted-foreground font-mono">{idx + 1}</td>
                                <td className="py-2 px-3 font-medium">{c.name}</td>
                                <td className="py-2 px-3">
                                  <Badge variant={c.role === "consultor" ? "default" : "secondary"} className="text-xs">
                                    {c.role === "consultor" ? "Consultor" : "Intermediário"}
                                  </Badge>
                                </td>
                                <td className="py-2 px-3 text-right">{c.num_processos}</td>
                                <td className="py-2 px-3 text-right text-purple-600">
                                  {formatCurrency(c.areas?.imobiliaria || 0)}
                                </td>
                                <td className="py-2 px-3 text-right text-blue-600">
                                  {formatCurrency(c.areas?.credito || 0)}
                                </td>
                                <td className="py-2 px-3 text-right font-mono text-slate-600">
                                  {formatCurrency(c.base_salary || 0)}
                                </td>
                                <td className="py-2 px-3 text-right font-mono text-orange-600">
                                  {formatCurrency(c.commission_share ?? c.total_comissao)}
                                </td>
                                <td className="py-2 px-3 text-right font-semibold font-mono text-emerald-700">
                                  {formatCurrency(c.total_payout ?? c.total_monthly ?? c.total_comissao)}
                                </td>
                                <td className="text-center py-2 px-3">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="gap-1.5 text-emerald-600 hover:text-emerald-800 hover:bg-emerald-50 h-8"
                                    onClick={() => setCommissionsReceiptConsultant(c)}
                                    title="Imprimir Recibo"
                                  >
                                    <Printer className="h-4 w-4" />
                                    <span className="hidden sm:inline text-xs">Recibo</span>
                                  </Button>
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

          {/* TAB: Distribuição (Pool Global — conditional) */}
          {distributionModel === "global_pool" && (
            <TabsContent value="distribution">
              <PoolDistributionPanel companyId={companyId} />
            </TabsContent>
          )}
        </Tabs>

        {/* Receipt Modal — Comissões Tab */}
        {commissionsReceiptConsultant && commissions && (
          <Dialog open={true} onOpenChange={() => setCommissionsReceiptConsultant(null)}>
            <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)] print-modal-content">
              <DialogHeader className="no-print">
                <DialogTitle className="flex items-center gap-2">
                  <Receipt className="h-5 w-5" />
                  Recibo de Vencimento
                </DialogTitle>
                <DialogDescription>
                  Pré-visualização do recibo para {commissionsReceiptConsultant.name}
                </DialogDescription>
              </DialogHeader>

              {/* Receipt content — this is what gets printed */}
              <div className="print-receipt">
                <div className="text-center border-b-2 border-emerald-600 pb-4 mb-6">
                  <img
                    src={user?.company === "power" ? "/PowerLogo-removebg-preview.png" : user?.company === "precision" ? "/logoPrecision-removebg-preview.png" : "/PowerCell-default.png"}
                    alt="Logo"
                    className="h-12 w-auto mx-auto mb-3"
                  />
                  <h2 className="text-xl font-bold text-emerald-800">
                    {user?.company === "power" ? "Power Real Estate" : user?.company === "precision" ? "Precision Crédito" : "PowerCell"}
                  </h2>
                  <p className="text-sm text-muted-foreground mt-1">Recibo de Vencimento</p>
                </div>

                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Nome</p>
                      <p className="font-semibold text-base">{commissionsReceiptConsultant.name}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Cargo</p>
                      <p className="font-semibold text-base">
                        {commissionsReceiptConsultant.role === "consultor" ? "Consultor" : "Intermediário"}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Período</p>
                      <p className="font-semibold text-base">Ano {selectedYear}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Modelo</p>
                      <p className="font-semibold text-base">
                        {commissions.distribution_model === "global_pool" ? "Pool Global" : "Tradicional"}
                      </p>
                    </div>
                  </div>

                  <div className="border rounded-lg overflow-hidden mt-6">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-emerald-50">
                          <th className="text-left py-3 px-4 font-medium text-emerald-800">Descrição</th>
                          <th className="text-right py-3 px-4 font-medium text-emerald-800">Valor</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t">
                          <td className="py-3 px-4">Salário Fixo</td>
                          <td className="py-3 px-4 text-right font-mono font-medium">
                            {formatCurrency(commissionsReceiptConsultant.base_salary || 0)}
                          </td>
                        </tr>
                        <tr className="border-t">
                          <td className="py-3 px-4">Comissões / Pool</td>
                          <td className="py-3 px-4 text-right font-mono font-medium">
                            {formatCurrency(commissionsReceiptConsultant.commission_share ?? commissionsReceiptConsultant.total_comissao)}
                          </td>
                        </tr>
                        <tr className="border-t-2 border-emerald-600 bg-emerald-50">
                          <td className="py-3 px-4 font-bold text-emerald-800">Total a Receber</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-emerald-800 text-lg">
                            {formatCurrency(commissionsReceiptConsultant.total_payout ?? commissionsReceiptConsultant.total_monthly ?? commissionsReceiptConsultant.total_comissao)}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <div className="mt-8 pt-4 border-t text-xs text-muted-foreground flex justify-between">
                    <span>Documento gerado automaticamente pelo PowerCell</span>
                    <span>{new Date().toLocaleDateString("pt-PT")}</span>
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 mt-4 no-print">
                <Button variant="outline" onClick={() => setCommissionsReceiptConsultant(null)}>
                  Fechar
                </Button>
                <Button onClick={() => window.print()} className="gap-2 bg-emerald-600 hover:bg-emerald-700">
                  <Printer className="h-4 w-4" />
                  Imprimir Recibo
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>
    </DashboardLayout>
  );
};

export default FinanceDashboard;
