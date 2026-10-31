/**
 * As calculadoras do CRM no Portal do Parceiro (`/parceiro/calculadoras`).
 *
 * O parceiro simula a prestação, a taxa de esforço (DSTI) e o risco antes de
 * submeter um lead — com os MESMOS motores de cálculo que a equipa usa
 * (`components/calculators/CalculatorsPanel.jsx`). Tudo corre no browser:
 * nada do que o parceiro escreve aqui é guardado nem enviado ao servidor; a
 * única chamada é a Euribor pública (sem token, sem cabeçalhos do staff).
 */
import React from "react";
import { Calculator } from "lucide-react";

import CalculatorsPanel from "@/components/calculators/CalculatorsPanel";

export default function PartnerCalculatorsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Calculator className="h-5 w-5 text-primary" aria-hidden="true" />
          Calculadoras
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Simulações de apoio à decisão de crédito. Os valores que introduzir aqui não são guardados.
        </p>
      </div>
      <CalculatorsPanel />
    </div>
  );
}
