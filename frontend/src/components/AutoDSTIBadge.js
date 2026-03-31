/**
 * AutoDSTIBadge - Indicador automático de DSTI calculado a partir dos dados da IA
 * 
 * Mostra uma badge colorida com o DSTI automático do processo.
 * Cores:
 * - Verde (≤30%): Baixo risco
 * - Amarelo (30-40%): Risco moderado
 * - Laranja (40-50%): Risco elevado
 * - Vermelho (>50%): Risco crítico (ultrapassa limite BdP)
 * - Cinza: Sem dados suficientes
 */
import { useState, useEffect } from "react";
import { Badge } from "./ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";
import { AlertTriangle, CheckCircle, Info, ShieldAlert, Calculator, Loader2 } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const RISK_CONFIG = {
  baixo: {
    color: "bg-green-100 text-green-800 border-green-200",
    badgeClass: "bg-green-500 text-white",
    icon: CheckCircle,
    label: "Baixo Risco",
  },
  moderado: {
    color: "bg-yellow-100 text-yellow-800 border-yellow-200",
    badgeClass: "bg-yellow-500 text-yellow-900",
    icon: Info,
    label: "Risco Moderado",
  },
  elevado: {
    color: "bg-orange-100 text-orange-800 border-orange-200",
    badgeClass: "bg-orange-500 text-white",
    icon: AlertTriangle,
    label: "Risco Elevado",
  },
  critico: {
    color: "bg-red-100 text-red-800 border-red-200",
    badgeClass: "bg-red-500 text-white",
    icon: ShieldAlert,
    label: "Risco Crítico",
  },
  sem_dados: {
    color: "bg-slate-100 text-slate-600 border-slate-200",
    badgeClass: "bg-slate-400 text-white",
    icon: Calculator,
    label: "Sem Dados",
  },
};

const AutoDSTIBadge = ({ processId, token, compact = false, showDetails = true }) => {
  const [dsti, setDsti] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (processId && token) {
      fetchDSTI();
    }
  }, [processId, token]);

  const fetchDSTI = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/processes/dsti/${processId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setDsti(data);
      } else if (res.status === 403) {
        // Funcionalidade desactivada - não mostrar erro
        setDsti(null);
      } else {
        setError("Erro ao calcular DSTI");
      }
    } catch (err) {
      // Silenciar erros de rede
      setDsti(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return compact ? (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        DSTI...
      </Badge>
    ) : (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>A calcular DSTI...</span>
      </div>
    );
  }

  if (!dsti || error) return null;

  const risk = RISK_CONFIG[dsti.risk_level] || RISK_CONFIG.sem_dados;
  const RiskIcon = risk.icon;
  const isHighRisk = dsti.risk_level === "elevado" || dsti.risk_level === "critico";

  // Compacto: apenas badge
  if (compact) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              variant="outline"
              className={`gap-1 ${risk.badgeClass} ${isHighRisk ? "animate-pulse" : ""}`}
            >
              <RiskIcon className="h-3 w-3" />
              {dsti.is_calculable ? `${dsti.dsti_pct}%` : "N/A"}
            </Badge>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-xs">
            <p className="font-semibold">{risk.label}</p>
            {dsti.is_calculable && (
              <>
                <p className="text-xs mt-1">
                  DSTI: {dsti.dsti_pct}% | Esforço Global: {dsti.effort_rate_pct}%
                </p>
                <p className="text-xs text-muted-foreground">
                  Créditos: {dsti.components.prestacao_creditos_mensal}€ / 
                  Rend. Bruto: {dsti.components.rendimento_bruto_total}€
                </p>
              </>
            )}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Detalhado: card com breakdown
  return (
    <div className={`rounded-lg border p-3 ${risk.color}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <RiskIcon className="h-4 w-4" />
          <span className="font-semibold text-sm">DSTI Automático</span>
        </div>
        <Badge className={`${risk.badgeClass} ${isHighRisk ? "animate-pulse" : ""}`}>
          {dsti.is_calculable ? `${dsti.dsti_pct}%` : "N/A"}
        </Badge>
      </div>

      {dsti.is_calculable && showDetails && (
        <div className="space-y-1.5 text-xs">
          <div className="flex justify-between">
            <span className="opacity-80">Rendimento Bruto Total</span>
            <span className="font-medium">{dsti.components.rendimento_bruto_total.toLocaleString("pt-PT")}€</span>
          </div>
          <div className="flex justify-between">
            <span className="opacity-80">Prestações Crédito</span>
            <span className="font-medium">{dsti.components.prestacao_creditos_mensal.toLocaleString("pt-PT")}€</span>
          </div>
          {dsti.components.renda_habitacao > 0 && (
            <div className="flex justify-between">
              <span className="opacity-80">Renda Habitação</span>
              <span className="font-medium">{dsti.components.renda_habitacao.toLocaleString("pt-PT")}€</span>
            </div>
          )}
          <div className="flex justify-between border-t border-current/10 pt-1 mt-1">
            <span className="font-medium">Taxa de Esforço Global</span>
            <span className="font-bold">{dsti.effort_rate_pct}%</span>
          </div>
          <div className="flex justify-between">
            <span className="opacity-80">Disponibilidade Mensal</span>
            <span className={`font-medium ${dsti.available_income >= 0 ? "text-green-700" : "text-red-700"}`}>
              {dsti.available_income.toLocaleString("pt-PT")}€
            </span>
          </div>
          {dsti.components.divida_total_crc > 0 && (
            <div className="flex justify-between">
              <span className="opacity-80">Dívida Total CRC</span>
              <span className="font-medium">{dsti.components.divida_total_crc.toLocaleString("pt-PT")}€</span>
            </div>
          )}
          {dsti.max_installment > 0 && (
            <div className="flex justify-between">
              <span className="opacity-80">Prestação Máx. Possível</span>
              <span className="font-medium">{dsti.max_installment.toLocaleString("pt-PT")}€</span>
            </div>
          )}
        </div>
      )}

      {isHighRisk && (
        <div className="mt-2 pt-2 border-t border-current/10">
          <p className="text-xs flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            {dsti.risk_level === "critico"
              ? "Ultrapassa o limite de 50% do Banco de Portugal"
              : "DSTI próximo do limite máximo - atenção"}
          </p>
        </div>
      )}
    </div>
  );
};

export default AutoDSTIBadge;
