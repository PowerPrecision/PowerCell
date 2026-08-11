/**
 * MortgageSimulator — Calculadora de Prestações de Crédito Habitação (CRM).
 *
 * PORQUÊ: o motor de cálculo já existia em `components/portal/SimulatorCH.jsx`
 * (Portal do Cliente), mas não havia forma de o usar dentro do CRM sem abrir o
 * Portal. Este componente reutiliza o mesmo motor (`utils/mortgageCalculations.js`)
 * numa UI orientada à equipa: Inputs à esquerda, Resultado em destaque à
 * direita, e "Progressive Disclosure" no toggle de Seguros — os campos de
 * Seguro de Vida / Multirriscos só aparecem quando o utilizador ativa o
 * Switch "Incluir Seguros".
 *
 * Regras de Ouro: tokens semânticos do Shadcn (bg-primary, text-muted-foreground,
 * etc.) em vez de cores Tailwind cruas (ver regra ESLint `no-restricted-syntax`
 * em `eslint.config.js`), e `formatCurrency` centralizado para todos os valores
 * monetários.
 */
import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";
import { Slider } from "../ui/slider";
import { Calculator, Euro, Calendar, Percent, Shield, Heart, Home, TrendingUp } from "lucide-react";
import { formatCurrency } from "../../utils/formatCurrency";
import { simularCreditoHabitacao } from "../../utils/mortgageCalculations";

export default function MortgageSimulator() {
  const [capital, setCapital] = useState(200000);
  const [prazoAnos, setPrazoAnos] = useState(30);
  const [taxaJuro, setTaxaJuro] = useState(3.5);
  const [incluirSeguros, setIncluirSeguros] = useState(false);
  const [seguroVida, setSeguroVida] = useState(15);
  const [seguroMultirriscos, setSeguroMultirriscos] = useState(10);

  const resultado = useMemo(
    () =>
      simularCreditoHabitacao({
        capital,
        prazoAnos,
        taxaJuro,
        incluirSeguros,
        seguroVida,
        seguroMultirriscos,
      }),
    [capital, prazoAnos, taxaJuro, incluirSeguros, seguroVida, seguroMultirriscos]
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ── Coluna Esquerda: Inputs ── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Calculator className="h-4 w-4 text-primary" />
            Dados do Empréstimo
          </CardTitle>
          <CardDescription>Capital, prazo e taxa de juro (TAN, já com spread se aplicável)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Capital */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1.5 text-sm">
                <Euro className="h-3.5 w-3.5 text-muted-foreground" />
                Capital / Montante
              </Label>
              <span className="text-sm font-semibold text-primary" data-testid="capital-value">
                {formatCurrency(capital)}
              </span>
            </div>
            <Slider
              min={10000}
              max={1000000}
              step={5000}
              value={[capital]}
              onValueChange={([v]) => setCapital(v)}
            />
            <Input
              type="number"
              min={0}
              step={1000}
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value) || 0)}
              className="mt-1"
              data-testid="capital-input"
            />
          </div>

          {/* Prazo */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1.5 text-sm">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                Prazo
              </Label>
              <span className="text-sm font-semibold text-primary">{prazoAnos} anos</span>
            </div>
            <Slider
              min={1}
              max={40}
              step={1}
              value={[prazoAnos]}
              onValueChange={([v]) => setPrazoAnos(v)}
            />
          </div>

          {/* Taxa de Juro / Spread */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1.5 text-sm">
                <Percent className="h-3.5 w-3.5 text-muted-foreground" />
                Taxa de Juro / Spread (TAN)
              </Label>
              <span className="text-sm font-semibold text-primary">{taxaJuro.toFixed(2)}%</span>
            </div>
            <Slider
              min={0.1}
              max={10}
              step={0.05}
              value={[taxaJuro]}
              onValueChange={([v]) => setTaxaJuro(v)}
            />
          </div>

          {/* Toggle Incluir Seguros — Progressive Disclosure */}
          <div className="pt-2 border-t border-border space-y-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="incluir-seguros" className="flex items-center gap-1.5 text-sm">
                <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                Incluir Seguros
              </Label>
              <Switch
                id="incluir-seguros"
                checked={incluirSeguros}
                onCheckedChange={setIncluirSeguros}
                data-testid="incluir-seguros-switch"
              />
            </div>

            {incluirSeguros && (
              <div className="grid grid-cols-2 gap-3 animate-in fade-in slide-in-from-top-1">
                <div className="space-y-1">
                  <Label className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Heart className="h-3 w-3" />
                    Seguro de Vida (€/mês)
                  </Label>
                  <Input
                    type="number"
                    min={0}
                    step={0.5}
                    value={seguroVida}
                    onChange={(e) => setSeguroVida(Number(e.target.value) || 0)}
                    data-testid="seguro-vida-input"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Home className="h-3 w-3" />
                    Multirriscos (€/mês)
                  </Label>
                  <Input
                    type="number"
                    min={0}
                    step={0.5}
                    value={seguroMultirriscos}
                    onChange={(e) => setSeguroMultirriscos(Number(e.target.value) || 0)}
                    data-testid="seguro-multirriscos-input"
                  />
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Coluna Direita: Resultado ── */}
      <div className="space-y-4">
        <Card className="border-primary/30 bg-primary/5" data-testid="mortgage-result-card">
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground font-medium mb-1">Prestação Mensal Estimada</p>
            <p className="text-4xl sm:text-5xl font-extrabold text-primary tracking-tight" data-testid="prestacao-mensal">
              {resultado ? formatCurrency(resultado.prestacaoTotal) : formatCurrency(0)}
              <span className="text-base font-medium text-muted-foreground ml-1">/ mês</span>
            </p>
            {resultado && (
              <div className="mt-2 inline-flex items-center gap-1.5 bg-card px-3 py-1 rounded-full border border-border">
                <TrendingUp className="h-3.5 w-3.5 text-primary" />
                <span className="text-xs text-muted-foreground">TAEG estimada:</span>
                <span className="text-sm font-semibold text-foreground">{resultado.taeg.toFixed(2)}%</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Detalhe da Simulação</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 pt-0">
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Capital</p>
              <p className="text-sm font-semibold text-foreground">{formatCurrency(capital)}</p>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Prestação Base</p>
              <p className="text-sm font-semibold text-foreground">
                {resultado ? formatCurrency(resultado.prestacaoBase) : formatCurrency(0)}
              </p>
            </div>
            {incluirSeguros && (
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Seguros / mês</p>
                <p className="text-sm font-semibold text-foreground">
                  {resultado ? formatCurrency(resultado.segurosMensal) : formatCurrency(0)}
                </p>
              </div>
            )}
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Total de Juros</p>
              <p className="text-sm font-semibold text-destructive">
                {resultado ? formatCurrency(resultado.totalJuros) : formatCurrency(0)}
              </p>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center col-span-2">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Total a Pagar</p>
              <p className="text-sm font-semibold text-foreground">
                {resultado ? formatCurrency(resultado.totalPago) : formatCurrency(0)}
              </p>
            </div>
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground leading-relaxed px-1">
          Simulação indicativa com o sistema francês de amortização. A TAEG inclui seguros quando
          ativados. Para uma proposta personalizada, contacte a equipa de consultores.
        </p>
      </div>
    </div>
  );
}
