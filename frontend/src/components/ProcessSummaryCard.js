/**
 * ProcessSummaryCard - Resumo do Processo
 * Card com informações resumidas no topo da ficha do cliente
 */
import { Card, CardContent } from "./ui/card";
import { Badge } from "./ui/badge";
import { safeNumber } from "./dashboard/DashboardShared";
import { 
  User, Phone, MapPin, Euro, Building2, Clock, Users, Percent
} from "lucide-react";
import { differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";
import { safeParseISO, safeFormat } from "../lib/utils";
import { safeString, safeStringArray } from "../utils/safeString";
import { formatCurrency as formatCurrencyShared } from "../utils/formatCurrency";

const ProcessSummaryCard = ({ process, consultorName, mediadorName, consultorNames, mediadorNames }) => {
  if (!process) return null;

  // Usar arrays se disponíveis, senão usar nomes únicos
  const consultoresDisplay = safeStringArray(
    consultorNames?.length > 0 ? consultorNames : (consultorName ? [consultorName] : [])
  );
  const mediadoresDisplay = safeStringArray(
    mediadorNames?.length > 0 ? mediadorNames : (mediadorName ? [mediadorName] : [])
  );

  // Calcular dias no sistema (protecção defensiva contra datas inválidas / Safari)
  const createdDate = safeParseISO(process.created_at);
  const daysInSystem = createdDate ? differenceInDays(new Date(), createdDate) : 0;

  // Formatar valor
  const formatCurrency = (value) => {
    if (!value) return "N/D";
    return formatCurrencyShared(safeNumber(value), { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  };

  return (
    <Card className="border-border bg-gradient-to-r from-blue-50 to-slate-50 dark:from-blue-950/30 dark:to-slate-950/30">
      <CardContent className="pt-4 pb-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {/* Cliente */}
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <User className="h-3 w-3" />
              Cliente
            </div>
            <p className="font-semibold text-sm truncate">{safeString(process?.client_name)}</p>
            {process.under_35 && (
              <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700 border-green-200">
                &lt;35 anos
              </Badge>
            )}
          </div>

          {/* Contacto */}
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Phone className="h-3 w-3" />
              Contacto
            </div>
            <p className="font-medium text-sm">{safeString(process?.client_phone, "N/D")}</p>
            <p className="text-xs text-muted-foreground truncate">{safeString(process?.client_email, "N/D")}</p>
          </div>

          {/* Valor do Imóvel */}
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Building2 className="h-3 w-3" />
              Imóvel
            </div>
            <p className="font-semibold text-sm text-blue-700 dark:text-blue-400">
              {formatCurrency(process.property_value)}
            </p>
            <div className="flex items-center gap-1 flex-wrap">
              {process.real_estate_data?.num_quartos && (
                <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700 border-blue-200">
                  {safeString(process.real_estate_data.num_quartos)}
                </Badge>
              )}
              {process.real_estate_data?.district && (
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {safeString(process.real_estate_data.district)}
                </p>
              )}
            </div>
          </div>

          {/* Financiamento */}
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Euro className="h-3 w-3" />
              Financiamento
            </div>
            <p className="font-semibold text-sm text-emerald-700 dark:text-emerald-400">
              {formatCurrency(process.financing_amount || process.credit_data?.approved_amount)}
            </p>
            {process.credit_data?.interest_rate && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Percent className="h-3 w-3" />
                {safeNumber(process.credit_data.interest_rate)}%
              </p>
            )}
          </div>

          {/* Equipa */}
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Users className="h-3 w-3" />
              Equipa
            </div>
            <div className="space-y-0.5">
              {consultoresDisplay.length > 0 && (
                <p className="text-xs">
                  <span className="text-blue-600">C:</span> {consultoresDisplay.map(n => n.split(' ')[0]).join(', ')}
                </p>
              )}
              {mediadoresDisplay.length > 0 && (
                <p className="text-xs">
                  <span className="text-emerald-600">I:</span> {mediadoresDisplay.map(n => n.split(' ')[0]).join(', ')}
                </p>
              )}
              {consultoresDisplay.length === 0 && mediadoresDisplay.length === 0 && (
                <p className="text-xs text-muted-foreground">Não atribuído</p>
              )}
            </div>
          </div>

          {/* Tempo no Sistema */}
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              No Sistema
            </div>
            <p className="font-semibold text-sm">
              {daysInSystem} {daysInSystem === 1 ? 'dia' : 'dias'}
            </p>
            {createdDate && (
              <p className="text-xs text-muted-foreground">
                desde {safeFormat(process.created_at, "dd/MM/yy", { locale: pt })}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ProcessSummaryCard;
