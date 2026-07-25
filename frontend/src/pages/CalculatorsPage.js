/**
 * CalculatorsPage — Secção "Calculadoras" do CRM.
 *
 * PORQUÊ: agrupa as simulações financeiras que a equipa usa para apoiar
 * decisões de crédito num único sítio, em vez de ficarem escondidas em
 * dialogs soltos dentro da ficha do processo. A Calculadora de Prestações
 * (Crédito Habitação) é a principal — o mesmo motor de cálculo do
 * simulador do Portal do Cliente (`utils/mortgageCalculations.js`,
 * extraído de `components/portal/SimulatorCH.jsx`), numa UI própria do
 * CRM. DSTI e Risco continuam disponíveis como calculadoras rápidas
 * (dialogs), reaproveitando os componentes já existentes.
 *
 * @route /calculadoras
 */
import DashboardLayout from "../layouts/DashboardLayout";
import { PageHeader } from "../components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Calculator, Home, TrendingUp, Wallet } from "lucide-react";
import MortgageSimulator from "../components/calculators/MortgageSimulator";
import DSTICalculator from "../components/DSTICalculator";
import RiskCalculator from "../components/RiskCalculator";

export default function CalculatorsPage() {
  return (
    <DashboardLayout title="Calculadoras">
      <div className="space-y-6 max-w-6xl mx-auto">
        <PageHeader
          icon={Calculator}
          title="Calculadoras"
          description="Simulações financeiras de apoio à decisão de crédito"
        />

        {/* ── Calculadora de Prestações (Crédito Habitação) — principal ── */}
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Home className="h-4 w-4 text-primary" />
              Prestação de Crédito Habitação
            </CardTitle>
            <CardDescription>
              Simule a prestação mensal com ou sem seguros, para qualquer cliente ou processo.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MortgageSimulator />
          </CardContent>
        </Card>

        {/* ── Outras calculadoras — acesso rápido (dialogs existentes) ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card className="border-border">
            <CardContent className="pt-6 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground flex items-center gap-1.5">
                  <Wallet className="h-4 w-4 text-primary shrink-0" />
                  DSTI (Taxa de Esforço)
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Rácio entre prestações e rendimento do cliente.
                </p>
              </div>
              <DSTICalculator
                trigger={
                  <Button variant="outline" size="sm" className="shrink-0">
                    Abrir
                  </Button>
                }
              />
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardContent className="pt-6 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground flex items-center gap-1.5">
                  <TrendingUp className="h-4 w-4 text-primary shrink-0" />
                  Risco de Crédito
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Avaliação estruturada de LTV, DSTI e histórico.
                </p>
              </div>
              <RiskCalculator
                trigger={
                  <Button variant="outline" size="sm" className="shrink-0">
                    Abrir
                  </Button>
                }
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}
