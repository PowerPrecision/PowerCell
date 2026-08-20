/**
 * CalculatorHub — Dropdown no Header com todas as calculadoras do CRM.
 *
 * Pacote DR: o ícone de calculadora deixa de abrir só Prestações. Abre um
 * DropdownMenu Shadcn com Prestações, Taxa de Esforço (DSTI) e Risco.
 * Se o utilizador estiver na ficha de um processo (`/processo/:id` ou
 * `/process/:id`), os campos são pré-preenchidos a partir do processo
 * em cache (TanStack Query).
 */
import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { Calculator, Home, TrendingUp, Wallet } from "lucide-react";
import MortgageSimulator from "./MortgageSimulator";
import DSTICalculator from "../DSTICalculator";
import RiskCalculator from "../RiskCalculator";
import { useProcessQuery } from "../../hooks/queries/useProcessQuery";
import {
  extractCalculatorPrefill,
  getProcessIdFromPath,
} from "../../utils/calculatorPrefill";

export default function CalculatorHub() {
  const location = useLocation();
  const processId = getProcessIdFromPath(location.pathname);
  const { process } = useProcessQuery(processId, { enabled: !!processId });
  const prefill = useMemo(() => extractCalculatorPrefill(process), [process]);
  const [activeCalc, setActiveCalc] = useState(null);

  const close = () => setActiveCalc(null);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Calculadoras"
            title="Calculadoras"
            data-testid="calculator-hub-trigger"
            className="h-9 w-9 sm:h-10 sm:w-10"
          >
            <Calculator className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>Calculadoras</DropdownMenuLabel>
          {prefill.hasContext && (
            <p className="px-2 pb-1 text-[11px] text-muted-foreground">
              Campos pré-preenchidos com o processo ativo
            </p>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="cursor-pointer gap-2"
            onSelect={() => setActiveCalc("prestacoes")}
            data-testid="calculator-hub-prestacoes"
          >
            <Home className="h-4 w-4 text-primary" />
            Prestações (Crédito Habitação)
          </DropdownMenuItem>
          <DropdownMenuItem
            className="cursor-pointer gap-2"
            onSelect={() => setActiveCalc("dsti")}
            data-testid="calculator-hub-dsti"
          >
            <Wallet className="h-4 w-4 text-primary" />
            Taxa de Esforço (DSTI)
          </DropdownMenuItem>
          <DropdownMenuItem
            className="cursor-pointer gap-2"
            onSelect={() => setActiveCalc("risco")}
            data-testid="calculator-hub-risco"
          >
            <TrendingUp className="h-4 w-4 text-primary" />
            Risco de Crédito
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Sheet open={activeCalc === "prestacoes"} onOpenChange={(open) => !open && close()}>
        <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Calculator className="h-5 w-5" />
              Calculadora de Prestações
            </SheetTitle>
          </SheetHeader>
          <div className="mt-4">
            <MortgageSimulator
              key={`${processId || "global"}-prestacoes`}
              initialValues={prefill.mortgage}
            />
          </div>
        </SheetContent>
      </Sheet>

      <DSTICalculator
        open={activeCalc === "dsti"}
        onOpenChange={(open) => { if (!open) close(); }}
        clientData={prefill.dsti}
      />
      <RiskCalculator
        open={activeCalc === "risco"}
        onOpenChange={(open) => { if (!open) close(); }}
        clientData={prefill.risk}
      />
    </>
  );
}
