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
 * O conteúdo vive em `components/calculators/CalculatorsPanel.jsx`, que o
 * Portal do Parceiro (`/parceiro/calculadoras`) também usa.
 *
 * @route /calculadoras
 */
import DashboardLayout from "../layouts/DashboardLayout";
import { PageHeader } from "../components/shared/PageHeader";
import { Calculator } from "lucide-react";
import CalculatorsPanel from "../components/calculators/CalculatorsPanel";

export default function CalculatorsPage() {
  return (
    <DashboardLayout title="Calculadoras">
      <div className="space-y-6 max-w-6xl mx-auto">
        <PageHeader
          icon={Calculator}
          title="Calculadoras"
          description="Simulações financeiras de apoio à decisão de crédito"
        />
        <CalculatorsPanel />
      </div>
    </DashboardLayout>
  );
}
