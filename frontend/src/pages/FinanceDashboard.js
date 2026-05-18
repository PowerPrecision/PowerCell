/**
 * FinanceDashboard — Módulo Financeiro Fase 2 (Premium UI)
 *
 * Ecrã principal do módulo financeiro com 3 secções:
 * 1. Painel de Configuração da Empresa (Honorários) — Modal GET/POST/PUT FinanceConfig
 * 2. Resumo Financeiro — 4 KPI Cards agregados de ProcessFinance
 * 3. Tabela de Histórico — Snapshots de ProcessFinance com edição de Estado
 *
 * Preserva as tabs originais (Imobiliária, Crédito, Mensal, Comissões)
 * e adiciona a nova secção "Honorários & Processos".
 *
 * @context {AuthContext} — user.company como company_id (multi-tenant)
 */

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
  Settings,
  CreditCard,
  Percent,
  Landmark,
  Save,
  Check,
  AlertTriangle,
  FileText,
  Receipt,
  Wallet,
  CircleDollarSign,
  RefreshCw,
  Filter,
  Eye,
  Pencil,
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
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
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
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
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
  updateFinanceConfig,
  // Fase 2 APIs
  getFinanceConfigs,
  createFinanceConfig,
  updateFinanceConfigById,
  getProcessFinances,
  updateProcessFinance,
  getProcessFinanceSummary,
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
    <Card className="overflow-hidden relative">
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
// CONFIGURAR HONORÁRIOS — Modal (Fase 2)
// ====================================================================

const HonorariosDialog = ({ companyId, onSaved }) => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const [feeType, setFeeType] = useState("percentage");
  const [defaultValue, setDefaultValue] = useState("");
  const [taxRate, setTaxRate] = useState("23");
  const [existingConfigId, setExistingConfigId] = useState(null);

  // Carregar configuração ao abrir o modal
  const fetchConfig = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const res = await getFinanceConfigs({ company_id: companyId });
      const configs = res.data?.configs || [];
      if (configs.length > 0) {
        const cfg = configs[0];
        setFeeType(cfg.fee_type || "percentage");
        setDefaultValue(String(cfg.default_value ?? ""));
        setTaxRate(String(cfg.tax_rate ?? "23"));
        setExistingConfigId(cfg.id);
      } else {
        setFeeType("percentage");
        setDefaultValue("");
        setTaxRate("23");
        setExistingConfigId(null);
      }
    } catch (err) {
      console.error("Erro ao carregar config:", err);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    if (open) fetchConfig();
  }, [open, fetchConfig]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const payload = {
        company_id: companyId,
        fee_type: feeType,
        default_value: parseFloat(defaultValue),
        tax_rate: parseFloat(taxRate),
      };

      if (existingConfigId) {
        // PUT — actualizar existente
        await updateFinanceConfigById(existingConfigId, {
          fee_type: feeType,
          default_value: parseFloat(defaultValue),
          tax_rate: parseFloat(taxRate),
        });
      } else {
        // POST — criar nova
        const res = await createFinanceConfig(payload);
        const newId = res.data?.id;
        if (newId) setExistingConfigId(newId);
      }

      setSuccess(true);
      if (onSaved) onSaved();
      setTimeout(() => {
        setOpen(false);
        setSuccess(false);
      }, 1500);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Erro ao guardar configuração de honorários."
      );
    } finally {
      setSaving(false);
    }
  };

  // Pré-visualização do cálculo
  const previewValue = parseFloat(defaultValue) || 0;
  const previewBase = 100000; // valor base exemplo
  const commission =
    feeType === "percentage"
      ? previewBase * (previewValue / 100)
      : previewValue;
  const taxAmt = commission * ((parseFloat(taxRate) || 23) / 100);
  const total = commission + taxAmt;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Settings className="h-4 w-4" />
          Configurar Honorários
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Percent className="h-5 w-5 text-purple-600" />
            Configuração de Honorários
          </DialogTitle>
          <DialogDescription>
            Defina o tipo de comissão e o valor por omissão para os processos da empresa.
            As alterações aplicam-se aos novos processos (os já fechados mantêm o snapshot).
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
            <span className="ml-2 text-muted-foreground">A carregar configuração...</span>
          </div>
        ) : (
          <div className="space-y-5 py-2">
            {/* Tipo de Honorário */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">Tipo de Honorário</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setFeeType("percentage")}
                  className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all ${
                    feeType === "percentage"
                      ? "border-purple-500 bg-purple-50 text-purple-700"
                      : "border-gray-200 hover:border-gray-300 text-muted-foreground"
                  }`}
                >
                  <Percent className="h-5 w-5" />
                  <div className="text-left">
                    <p className="text-sm font-semibold">Percentagem</p>
                    <p className="text-xs opacity-70">% sobre o valor base</p>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setFeeType("fixed")}
                  className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all ${
                    feeType === "fixed"
                      ? "border-purple-500 bg-purple-50 text-purple-700"
                      : "border-gray-200 hover:border-gray-300 text-muted-foreground"
                  }`}
                >
                  <DollarSign className="h-5 w-5" />
                  <div className="text-left">
                    <p className="text-sm font-semibold">Valor Fixo</p>
                    <p className="text-xs opacity-70">Montante em euros</p>
                  </div>
                </button>
              </div>
            </div>

            {/* Valor */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  {feeType === "percentage" ? "Percentagem (%)" : "Valor Fixo (€)"}
                </Label>
                <div className="relative">
                  <Input
                    type="number"
                    min={0}
                    max={feeType === "percentage" ? 100 : undefined}
                    step={feeType === "percentage" ? 0.5 : 100}
                    value={defaultValue}
                    onChange={(e) => setDefaultValue(e.target.value)}
                    placeholder={feeType === "percentage" ? "ex: 5" : "ex: 5000"}
                    className="pr-10"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    {feeType === "percentage" ? "%" : "€"}
                  </span>
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium">Taxa de IVA (%)</Label>
                <div className="relative">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    value={taxRate}
                    onChange={(e) => setTaxRate(e.target.value)}
                    className="pr-8"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                </div>
              </div>
            </div>

            {/* Pré-visualização */}
            <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Pré-visualização (base: {formatCurrency(previewBase)})
              </p>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-muted-foreground text-xs">Comissão</p>
                  <p className="font-semibold">{formatCurrency(commission)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">IVA ({taxRate}%)</p>
                  <p className="font-semibold">{formatCurrency(taxAmt)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">Total a Faturar</p>
                  <p className="font-semibold text-emerald-700">{formatCurrency(total)}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-red-200 bg-red-50 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {success && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-green-200 bg-green-50 text-sm text-green-700">
            <Check className="h-4 w-4 flex-shrink-0" />
            Configuração guardada com sucesso!
          </div>
        )}

        <DialogFooter className="gap-2">
          <DialogClose asChild>
            <Button variant="outline" disabled={saving}>Cancelar</Button>
          </DialogClose>
          <Button onClick={handleSave} disabled={saving || !defaultValue} className="gap-2">
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

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
      setError(err.response?.data?.detail || "Erro ao carregar registos financeiros.");
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
// LEGACY CONFIG DIALOG (Preservado para as tabs originais)
// ====================================================================

const ConfigDialog = ({ config, onSave }) => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);

  const [localConfig, setLocalConfig] = useState({
    imobiliaria: { ...config?.imobiliaria },
    credito: { ...config?.credito },
  });

  useEffect(() => {
    if (config) {
      setLocalConfig({
        imobiliaria: { ...config.imobiliaria },
        credito: { ...config.credito },
      });
    }
  }, [config]);

  const handleChange = (area, field, value) => {
    const numVal = parseFloat(value);
    if (!isNaN(numVal) && numVal >= 0 && numVal <= 100) {
      setLocalConfig((prev) => ({
        ...prev,
        [area]: { ...prev[area], [field]: numVal },
      }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      await onSave(localConfig);
      setSuccess(true);
      setTimeout(() => {
        setOpen(false);
        setSuccess(false);
      }, 1500);
    } catch (err) {
      setError(err.response?.data?.detail || "Erro ao guardar configurações.");
    } finally {
      setSaving(false);
    }
  };

  const fields = [
    { key: "comissao_consultor_pct", label: "% Comissão Consultor", description: "Percentagem da comissão paga ao consultor" },
    { key: "retida_agencia_pct", label: "% Retida pela Agência", description: "Percentagem da comissão retida como lucro bruto" },
    { key: "taxa_impostos_sobre_lucro", label: "% Impostos sobre Lucro", description: "Taxa de imposto sobre o lucro bruto" },
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Settings className="h-4 w-4" />
          Config. Dashboard
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Percent className="h-5 w-5 text-purple-600" />
            Configurações do Dashboard
          </DialogTitle>
          <DialogDescription>
            Defina as percentagens de comissão e impostos para cada área de negócio.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-purple-600" />
              <h3 className="font-semibold text-sm">Imobiliária</h3>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {fields.map((f) => (
                <div key={`imob-${f.key}`} className="space-y-1">
                  <Label className="text-xs text-muted-foreground">{f.label}</Label>
                  <div className="relative">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={localConfig.imobiliaria?.[f.key] ?? ""}
                      onChange={(e) => handleChange("imobiliaria", f.key, e.target.value)}
                      className="pr-8"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{f.description}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-blue-600" />
              <h3 className="font-semibold text-sm">Crédito</h3>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {fields.map((f) => (
                <div key={`cred-${f.key}`} className="space-y-1">
                  <Label className="text-xs text-muted-foreground">{f.label}</Label>
                  <div className="relative">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={localConfig.credito?.[f.key] ?? ""}
                      onChange={(e) => handleChange("credito", f.key, e.target.value)}
                      className="pr-8"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{f.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-red-200 bg-red-50 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {success && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-green-200 bg-green-50 text-sm text-green-700">
            <Check className="h-4 w-4 flex-shrink-0" />
            Configurações guardadas com sucesso!
          </div>
        )}

        <DialogFooter className="gap-2">
          <DialogClose asChild>
            <Button variant="outline" disabled={saving}>Cancelar</Button>
          </DialogClose>
          <Button onClick={handleSave} disabled={saving} className="gap-2">
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

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
  const [config, setConfig] = useState(null);

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
      const [summaryRes, monthlyRes, commissionsRes, performanceRes, configRes] =
        await Promise.all([
          getFinanceSummary(params),
          getFinanceMonthly(params),
          getFinanceCommissions(params),
          getFinancePerformance(params),
          getFinanceConfig(),
        ]);
      setSummary(summaryRes.data);
      setMonthly(monthlyRes.data);
      setCommissions(commissionsRes.data);
      setPerformance(performanceRes.data);
      if (configRes.data?.config) {
        setConfig(configRes.data.config);
      }
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

  const handleSaveConfig = async (newConfig) => {
    await updateFinanceConfig(newConfig);
    setConfig(newConfig);
    await fetchAllData();
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
        <div className="p-4 md:p-6 space-y-4">
          <div className="flex items-center gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
            <span className="text-muted-foreground">A carregar dados financeiros...</span>
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
              Visão financeira por área de negócio — exclusivo para Administração
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <HonorariosDialog companyId={companyId} onSaved={fetchAllData} />

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

        {/* KPIs Globais (Legacy) */}
        {summary && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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

        {/* Tabs */}
        <Tabs defaultValue="honorarios" className="space-y-4">
          <TabsList className="grid w-full grid-cols-2 sm:grid-cols-5 lg:w-auto lg:inline-grid">
            <TabsTrigger value="honorarios" className="gap-1.5">
              <CircleDollarSign className="h-3.5 w-3.5" />
              Honorários & Processos
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
          </TabsList>

          {/* TAB: Honorários & Processos (Fase 2 — NOVO) */}
          <TabsContent value="honorarios">
            <ProcessFinancesTab companyId={companyId} />
          </TabsContent>

          {/* TAB: Imobiliária */}
          <TabsContent value="imobiliaria">
            <div className="flex justify-end mb-3">
              <ConfigDialog config={config} onSave={handleSaveConfig} />
            </div>
            <AreaDetail
              area="imobiliaria"
              data={summary?.imobiliaria}
              monthlyData={monthly?.monthly}
              performanceData={performance}
              selectedYear={selectedYear}
            />
          </TabsContent>

          {/* TAB: Crédito */}
          <TabsContent value="credito">
            <div className="flex justify-end mb-3">
              <ConfigDialog config={config} onSave={handleSaveConfig} />
            </div>
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
                    subtitle="Pagamentos a colaboradores"
                    icon={Users}
                    color="text-orange-600"
                    iconBg="bg-orange-50"
                  />
                  <FinanceStatCard
                    title="Colaboradores Activos"
                    value={commissions.collaborators.length}
                    subtitle="Consultores e intermediários"
                    icon={Users}
                    color="text-blue-600"
                    iconBg="bg-blue-50"
                  />
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Ranking de Colaboradores — {selectedYear}</CardTitle>
                    <CardDescription>Comissões por área de negócio</CardDescription>
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
                              <th className="text-right py-2 px-3 font-medium text-muted-foreground">Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            {commissions.collaborators.map((c, idx) => (
                              <tr key={c.name} className="border-b hover:bg-muted/50">
                                <td className="py-2 px-3 text-muted-foreground font-mono">{idx + 1}</td>
                                <td className="py-2 px-3 font-medium">{c.name}</td>
                                <td className="py-2 px-3">
                                  <Badge variant={hasRole(c, "consultor") ? "default" : "secondary"} className="text-xs">
                                    {hasRole(c, "consultor") ? "Consultor" : "Intermediário"}
                                  </Badge>
                                </td>
                                <td className="py-2 px-3 text-right">{c.num_processos}</td>
                                <td className="py-2 px-3 text-right text-purple-600">
                                  {formatCurrency(c.areas?.imobiliaria || 0)}
                                </td>
                                <td className="py-2 px-3 text-right text-blue-600">
                                  {formatCurrency(c.areas?.credito || 0)}
                                </td>
                                <td className="py-2 px-3 text-right font-semibold text-green-600">
                                  {formatCurrency(c.total_comissao)}
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
