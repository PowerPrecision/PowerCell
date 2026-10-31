/**
 * CalculatorsPanel — o conteúdo da secção «Calculadoras», sem moldura.
 *
 * PORQUÊ: as mesmas calculadoras servem o CRM (`/calculadoras`, dentro do
 * `DashboardLayout`) e o Portal do Parceiro (`/parceiro/calculadoras`, dentro
 * do `PartnerShell`). Um só painel garante que o parceiro vê exactamente os
 * mesmos motores de cálculo que a equipa — sem cópias que divergem.
 *
 * Só componentes puros (sem contexto de sessão nem cliente HTTP do staff):
 * a Prestação (`MortgageSimulator`), a Taxa de Esforço (`DSTICalculator`) e
 * o Risco (`RiskCalculator`, cuja Euribor vem do endpoint público).
 */
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../ui/card";
import { Button } from "../ui/button";
import { Home, TrendingUp, Wallet } from "lucide-react";
import MortgageSimulator from "./MortgageSimulator";
import DSTICalculator from "../DSTICalculator";
import RiskCalculator from "../RiskCalculator";

function CalculadoraRapida({ icone: Icone, titulo, descricao, children }) {
  return (
    <Card className="border-border">
      <CardContent className="pt-6 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <Icone className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
            {titulo}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">{descricao}</p>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

const botaoAbrir = (rotulo) => (
  <Button variant="outline" size="sm" className="shrink-0" aria-label={`Abrir ${rotulo}`}>
    Abrir
  </Button>
);

export default function CalculatorsPanel() {
  return (
    <div className="space-y-6">
      {/* ── Calculadora de Prestações (Crédito Habitação) — principal ── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Home className="h-4 w-4 text-primary" aria-hidden="true" />
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

      {/* ── Outras calculadoras — acesso rápido (dialogs) ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <CalculadoraRapida
          icone={Wallet}
          titulo="DSTI (Taxa de Esforço)"
          descricao="Rácio entre prestações e rendimento do cliente."
        >
          <DSTICalculator trigger={botaoAbrir("DSTI (Taxa de Esforço)")} />
        </CalculadoraRapida>
        <CalculadoraRapida
          icone={TrendingUp}
          titulo="Risco de Crédito"
          descricao="Avaliação estruturada de LTV, DSTI e histórico."
        >
          <RiskCalculator trigger={botaoAbrir("Risco de Crédito")} />
        </CalculadoraRapida>
      </div>
    </div>
  );
}
