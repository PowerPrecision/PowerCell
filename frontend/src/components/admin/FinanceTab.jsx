/**
 * FinanceTab — Tab de Gestão Financeira (embedded no SystemAdminPanel)
 *
 * PORQUÊ: A FinanceSettingsPage era uma página autónoma com rota própria
 * (/finance/settings) e link na sidebar. Para consolidar toda a gestão
 * financeira no Painel de Administração, extraímos a lógica para este
 * componente que funciona em modo embedded (sem DashboardLayout, sem
 * guarda de permissões — o painel pai já gere isso).
 *
 * SECÇÕES:
 * a) Configuração de Honorários — Taxas padrão (% ou fixo) e IVA
 * b) Modelo de Distribuição — Individual Split vs Pool Global
 * c) Percentagens por Área — Legacy dashboard config (Imobiliária + Crédito)
 *
 * @context {AuthContext} — user.company como company_id (multi-tenant)
 */

import { useState, useEffect, useCallback } from "react";
import {
  Percent,
  DollarSign,
  Building2,
  CreditCard,
  Users,
  CircleDollarSign,
  AlertTriangle,
  Save,
  Check,
  Loader2,
  Landmark,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Badge } from "../ui/badge";
import { Separator } from "../ui/separator";
import { useAuth } from "../../contexts/AuthContext";
import {
  getFinanceConfig,
  updateFinanceConfig,
  getFinanceConfigs,
  createFinanceConfig,
  updateFinanceConfigById,
} from "../../services/api";

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

// ====================================================================
// MAIN COMPONENT
// ====================================================================

const FinanceTab = () => {
  const { user } = useAuth();
  const companyId = user?.company || "default";

  // --- Estado: Configuração de Honorários ---
  const [feeType, setFeeType] = useState("percentage");
  const [defaultValue, setDefaultValue] = useState("");
  const [taxRate, setTaxRate] = useState("23");
  const [existingConfigId, setExistingConfigId] = useState(null);
  const [distributionModel, setDistributionModel] = useState("individual_split");

  // --- Estado: Configuração do Dashboard (Legacy) ---
  const [dashboardConfig, setDashboardConfig] = useState({
    imobiliaria: {
      comissao_consultor_pct: 50,
      retida_agencia_pct: 50,
      taxa_impostos_sobre_lucro: 23,
    },
    credito: {
      comissao_consultor_pct: 50,
      retida_agencia_pct: 50,
      taxa_impostos_sobre_lucro: 23,
    },
  });

  // --- Estado: UI ---
  const [loading, setLoading] = useState(true);
  const [savingHonorarios, setSavingHonorarios] = useState(false);
  const [savingDashboard, setSavingDashboard] = useState(false);
  const [successHonorarios, setSuccessHonorarios] = useState(false);
  const [successDashboard, setSuccessDashboard] = useState(false);
  const [error, setError] = useState(null);

  // ====================================================================
  // LOAD CONFIG
  // ====================================================================
  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [configRes, financeConfigsRes] = await Promise.all([
        getFinanceConfig(),
        getFinanceConfigs({ company_id: companyId }),
      ]);

      if (configRes.data?.config) {
        setDashboardConfig({
          imobiliaria: { ...configRes.data.config.imobiliaria },
          credito: { ...configRes.data.config.credito },
        });
      }

      const cfgs = financeConfigsRes.data?.configs || [];
      if (cfgs.length > 0) {
        const cfg = cfgs[0];
        setFeeType(cfg.fee_type || "percentage");
        setDefaultValue(String(cfg.default_value ?? ""));
        setTaxRate(String(cfg.tax_rate ?? "23"));
        setExistingConfigId(cfg.id);
        setDistributionModel(cfg.distribution_model || "individual_split");
      }
    } catch (err) {
      console.error("Erro ao carregar configuração:", err);
      setError(err.response?.data?.detail || "Erro ao carregar configuração financeira.");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // ====================================================================
  // SAVE: Honorários
  // ====================================================================
  const handleSaveHonorarios = async () => {
    setSavingHonorarios(true);
    setError(null);
    setSuccessHonorarios(false);
    try {
      const payload = {
        company_id: companyId,
        fee_type: feeType,
        default_value: parseFloat(defaultValue),
        tax_rate: parseFloat(taxRate),
        distribution_model: distributionModel,
      };

      if (existingConfigId) {
        await updateFinanceConfigById(existingConfigId, {
          fee_type: feeType,
          default_value: parseFloat(defaultValue),
          tax_rate: parseFloat(taxRate),
          distribution_model: distributionModel,
        });
      } else {
        const res = await createFinanceConfig(payload);
        const newId = res.data?.id;
        if (newId) setExistingConfigId(newId);
      }

      setSuccessHonorarios(true);
      setTimeout(() => setSuccessHonorarios(false), 3000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Erro ao guardar configuração de honorários.");
    } finally {
      setSavingHonorarios(false);
    }
  };

  // ====================================================================
  // SAVE: Dashboard Config (Legacy)
  // ====================================================================
  const handleSaveDashboardConfig = async () => {
    setSavingDashboard(true);
    setError(null);
    setSuccessDashboard(false);
    try {
      await updateFinanceConfig(dashboardConfig);
      setSuccessDashboard(true);
      setTimeout(() => setSuccessDashboard(false), 3000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Erro ao guardar configuração do dashboard.");
    } finally {
      setSavingDashboard(false);
    }
  };

  const handleDashboardChange = (area, field, value) => {
    const numVal = parseFloat(value);
    if (!isNaN(numVal) && numVal >= 0 && numVal <= 100) {
      setDashboardConfig((prev) => ({
        ...prev,
        [area]: { ...prev[area], [field]: numVal },
      }));
    }
  };

  // ====================================================================
  // PREVIEW CALCULATION
  // ====================================================================
  const previewValue = parseFloat(defaultValue) || 0;
  const previewBase = 100000;
  const commission =
    feeType === "percentage"
      ? previewBase * (previewValue / 100)
      : previewValue;
  const taxAmt = commission * ((parseFloat(taxRate) || 23) / 100);
  const total = commission + taxAmt;

  // ====================================================================
  // RENDER
  // ====================================================================

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-amber-600" />
        <span className="ml-3 text-muted-foreground text-lg">A carregar configuração financeira...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            Gestão Financeira
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Configure honorários, taxas e modelo de distribuição
          </p>
        </div>
        <Badge variant="outline" className="w-fit gap-1.5 px-3 py-1.5 text-sm border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          <Landmark className="h-3.5 w-3.5" />
          Configuração Global
        </Badge>
      </div>

      {/* Erro global */}
      {error && (
        <div className="flex items-center gap-2 p-4 rounded-lg border border-red-200 bg-red-50 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* ============================================================ */}
      {/* SECÇÃO A: Configuração de Honorários                         */}
      {/* ============================================================ */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Percent className="h-5 w-5 text-amber-600" />
            Configuração de Honorários
          </CardTitle>
          <CardDescription>
            Defina o tipo de comissão, valor por omissão e taxa de IVA para os processos da empresa.
            As alterações aplicam-se aos novos processos (os já fechados mantêm o snapshot).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Tipo de Honorário */}
          <div className="space-y-3">
            <Label className="text-sm font-semibold">Tipo de Honorário</Label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setFeeType("percentage")}
                className={`flex items-center gap-3 p-4 rounded-xl border-2 transition-all ${
                  feeType === "percentage"
                    ? "border-amber-500 bg-amber-50 text-amber-700 shadow-sm dark:bg-amber-900/20 dark:text-amber-300"
                    : "border-gray-200 hover:border-gray-300 text-muted-foreground dark:border-gray-700"
                }`}
              >
                <div className={`p-2 rounded-lg ${feeType === "percentage" ? "bg-amber-100 dark:bg-amber-800/40" : "bg-gray-100 dark:bg-gray-800"}`}>
                  <Percent className="h-5 w-5" />
                </div>
                <div className="text-left">
                  <p className="text-sm font-semibold">Percentagem</p>
                  <p className="text-xs opacity-70">% sobre o valor base</p>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setFeeType("fixed")}
                className={`flex items-center gap-3 p-4 rounded-xl border-2 transition-all ${
                  feeType === "fixed"
                    ? "border-amber-500 bg-amber-50 text-amber-700 shadow-sm dark:bg-amber-900/20 dark:text-amber-300"
                    : "border-gray-200 hover:border-gray-300 text-muted-foreground dark:border-gray-700"
                }`}
              >
                <div className={`p-2 rounded-lg ${feeType === "fixed" ? "bg-amber-100 dark:bg-amber-800/40" : "bg-gray-100 dark:bg-gray-800"}`}>
                  <DollarSign className="h-5 w-5" />
                </div>
                <div className="text-left">
                  <p className="text-sm font-semibold">Valor Fixo</p>
                  <p className="text-xs opacity-70">Montante em euros</p>
                </div>
              </button>
            </div>
          </div>

          <Separator />

          {/* Taxas */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label className="text-sm font-medium">
                {feeType === "percentage" ? "Mediação Imobiliária (%)" : "Valor Fixo Imobiliária (€)"}
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
                  className="pr-12 h-11 text-base"
                />
                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-medium text-muted-foreground">
                  {feeType === "percentage" ? "%" : "€"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {feeType === "percentage"
                  ? "Percentagem aplicada sobre o valor do imóvel/montante de crédito"
                  : "Valor fixo por processo de intermediação"}
              </p>
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
                  className="pr-12 h-11 text-base"
                />
                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-medium text-muted-foreground">%</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Taxa de IVA aplicada sobre a comissão (legal em PT: 23%)
              </p>
            </div>
          </div>

          {/* Pré-visualização */}
          <div className="rounded-xl border bg-muted/30 p-5 space-y-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Pré-visualização (base: {formatCurrency(previewBase)})
            </p>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs">Comissão</p>
                <p className="font-semibold text-base">{formatCurrency(commission)}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">IVA ({taxRate}%)</p>
                <p className="font-semibold text-base">{formatCurrency(taxAmt)}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Total a Faturar</p>
                <p className="font-semibold text-base text-emerald-700 dark:text-emerald-400">{formatCurrency(total)}</p>
              </div>
            </div>
          </div>

          {/* Guardar Honorários */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              onClick={handleSaveHonorarios}
              disabled={savingHonorarios || !defaultValue}
              className="gap-2"
              size="lg"
            >
              {savingHonorarios ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Guardar Honorários
            </Button>
            {successHonorarios && (
              <span className="flex items-center gap-1.5 text-sm text-green-600 font-medium">
                <Check className="h-4 w-4" />
                Configuração guardada com sucesso!
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ============================================================ */}
      {/* SECÇÃO B: Modelo de Distribuição                             */}
      {/* ============================================================ */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <CircleDollarSign className="h-5 w-5 text-emerald-600" />
            Modelo de Distribuição de Comissões
          </CardTitle>
          <CardDescription>
            Escolha como as comissões são distribuídas pelos consultores da empresa.
            Esta definição afeta o cálculo do fecho de mês.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button
              type="button"
              onClick={() => setDistributionModel("individual_split")}
              className={`flex flex-col items-start gap-3 p-5 rounded-xl border-2 transition-all text-left ${
                distributionModel === "individual_split"
                  ? "border-amber-500 bg-amber-50 text-amber-700 shadow-sm dark:bg-amber-900/20 dark:text-amber-300"
                  : "border-gray-200 hover:border-gray-300 text-muted-foreground dark:border-gray-700"
              }`}
            >
              <div className="flex items-center gap-3 w-full">
                <div className={`p-2.5 rounded-lg ${distributionModel === "individual_split" ? "bg-amber-100 dark:bg-amber-800/40" : "bg-gray-100 dark:bg-gray-800"}`}>
                  <Users className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-base font-semibold">Tradicional (Individual Split)</p>
                  <p className="text-xs opacity-70 mt-0.5">Cada consultor recebe a sua comissão individual</p>
                </div>
              </div>
              <div className="w-full mt-2 text-xs space-y-1">
                <p className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${distributionModel === "individual_split" ? "bg-amber-500" : "bg-gray-300"}`} />
                  Comissão directa por processo
                </p>
                <p className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${distributionModel === "individual_split" ? "bg-amber-500" : "bg-gray-300"}`} />
                  Split consultor/agência configurável
                </p>
                <p className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${distributionModel === "individual_split" ? "bg-amber-500" : "bg-gray-300"}`} />
                  Transparência individual
                </p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setDistributionModel("global_pool")}
              className={`flex flex-col items-start gap-3 p-5 rounded-xl border-2 transition-all text-left ${
                distributionModel === "global_pool"
                  ? "border-emerald-500 bg-emerald-50 text-emerald-700 shadow-sm dark:bg-emerald-900/20 dark:text-emerald-300"
                  : "border-gray-200 hover:border-gray-300 text-muted-foreground dark:border-gray-700"
              }`}
            >
              <div className="flex items-center gap-3 w-full">
                <div className={`p-2.5 rounded-lg ${distributionModel === "global_pool" ? "bg-emerald-100 dark:bg-emerald-800/40" : "bg-gray-100 dark:bg-gray-800"}`}>
                  <CircleDollarSign className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-base font-semibold">Pool Global (Cooperativo)</p>
                  <p className="text-xs opacity-70 mt-0.5">Divisão igualitária entre consultores ativos</p>
                </div>
              </div>
              <div className="w-full mt-2 text-xs space-y-1">
                <p className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${distributionModel === "global_pool" ? "bg-emerald-500" : "bg-gray-300"}`} />
                  Soma de todas as comissões do mês
                </p>
                <p className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${distributionModel === "global_pool" ? "bg-emerald-500" : "bg-gray-300"}`} />
                  Divisão igualitária por consultor
                </p>
                <p className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${distributionModel === "global_pool" ? "bg-emerald-500" : "bg-gray-300"}`} />
                  Incentivo ao trabalho de equipa
                </p>
              </div>
            </button>
          </div>

          {distributionModel === "global_pool" && (
            <div className="flex items-start gap-2 p-4 rounded-lg border border-emerald-200 bg-emerald-50/50 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Modelo Pool Global ativo</p>
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                  No modelo Pool, todas as comissões faturadas no mês são somadas e divididas igualmente
                  pelos consultores ativos da empresa. O salário fixo de cada consultor é somado ao valor
                  do pool para obter o total mensal.
                </p>
              </div>
            </div>
          )}

          {/* Guardar Distribuição */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              onClick={handleSaveHonorarios}
              disabled={savingHonorarios || !defaultValue}
              className="gap-2"
              size="lg"
            >
              {savingHonorarios ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Guardar Modelo de Distribuição
            </Button>
            {successHonorarios && (
              <span className="flex items-center gap-1.5 text-sm text-green-600 font-medium">
                <Check className="h-4 w-4" />
                Modelo guardado com sucesso!
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ============================================================ */}
      {/* SECÇÃO C: Percentagens por Área (Legacy Dashboard Config)    */}
      {/* ============================================================ */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Landmark className="h-5 w-5 text-amber-600" />
            Percentagens de Comissão por Área
          </CardTitle>
          <CardDescription>
            Configure as percentagens de split e impostos para cada área de negócio.
            Estas definições são usadas no cálculo do dashboard financeiro.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Imobiliária */}
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                <Building2 className="h-4 w-4 text-amber-600" />
              </div>
              <h3 className="font-semibold text-base">Imobiliária</h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                { key: "comissao_consultor_pct", label: "% Comissão Consultor", desc: "Percentagem paga ao consultor" },
                { key: "retida_agencia_pct", label: "% Retida pela Agência", desc: "Percentagem retida como lucro bruto" },
                { key: "taxa_impostos_sobre_lucro", label: "% Impostos sobre Lucro", desc: "Taxa de imposto sobre lucro bruto" },
              ].map((f) => (
                <div key={`imob-${f.key}`} className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{f.label}</Label>
                  <div className="relative">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={dashboardConfig.imobiliaria?.[f.key] ?? ""}
                      onChange={(e) => handleDashboardChange("imobiliaria", f.key, e.target.value)}
                      className="pr-10 h-11"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>

          <Separator />

          {/* Crédito */}
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-sky-100 dark:bg-sky-900/30">
                <CreditCard className="h-4 w-4 text-sky-600" />
              </div>
              <h3 className="font-semibold text-base">Intermediação de Crédito</h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                { key: "comissao_consultor_pct", label: "% Comissão Consultor", desc: "Percentagem paga ao consultor" },
                { key: "retida_agencia_pct", label: "% Retida pela Agência", desc: "Percentagem retida como lucro bruto" },
                { key: "taxa_impostos_sobre_lucro", label: "% Impostos sobre Lucro", desc: "Taxa de imposto sobre lucro bruto" },
              ].map((f) => (
                <div key={`cred-${f.key}`} className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{f.label}</Label>
                  <div className="relative">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={dashboardConfig.credito?.[f.key] ?? ""}
                      onChange={(e) => handleDashboardChange("credito", f.key, e.target.value)}
                      className="pr-10 h-11"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Guardar Dashboard Config */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              onClick={handleSaveDashboardConfig}
              disabled={savingDashboard}
              className="gap-2"
              size="lg"
              variant="outline"
            >
              {savingDashboard ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Guardar Percentagens
            </Button>
            {successDashboard && (
              <span className="flex items-center gap-1.5 text-sm text-green-600 font-medium">
                <Check className="h-4 w-4" />
                Percentagens guardadas com sucesso!
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default FinanceTab;
