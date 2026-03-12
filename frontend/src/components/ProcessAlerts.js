import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { 
  AlertTriangle, 
  Clock, 
  FileText, 
  Star, 
  Calendar, 
  ChevronDown, 
  ChevronUp,
  CheckCircle,
  XCircle,
  Loader2
} from "lucide-react";
import { getProcessAlerts } from "../services/api";

const alertIcons = {
  age_under_35: Star,
  pre_approval_countdown: Clock,
  document_expiry: FileText,
  property_docs_check: FileText,
  deed_reminder: Calendar,
  default: AlertTriangle
};

const priorityColors = {
  critical: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-blue-100 text-blue-800 border-blue-200",
  info: "bg-emerald-100 text-emerald-800 border-emerald-200",
  success: "bg-green-100 text-green-800 border-green-200",
  warning: "bg-yellow-100 text-yellow-800 border-yellow-200"
};

const priorityLabels = {
  critical: "Crítico",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
  info: "Info",
  success: "OK",
  warning: "Atenção"
};

const ProcessAlerts = ({ processId, className = "" }) => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(true);
  const [hasCritical, setHasCritical] = useState(false);
  const [hasHigh, setHasHigh] = useState(false);

  useEffect(() => {
    if (processId) {
      fetchAlerts();
    }
  }, [processId]);

  const fetchAlerts = async () => {
    try {
      setLoading(true);
      const res = await getProcessAlerts(processId);
      setAlerts(res.data.alerts || []);
      setHasCritical(res.data.has_critical || false);
      setHasHigh(res.data.has_high || false);
    } catch (error) {
      console.error("Erro ao carregar alertas:", error);
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  };

  const getIcon = (type) => {
    return alertIcons[type] || alertIcons.default;
  };

  if (loading) {
    return (
      <Card className={`${className} animate-pulse`}>
        <CardHeader className="py-3">
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm text-muted-foreground">A carregar alertas...</span>
          </div>
        </CardHeader>
      </Card>
    );
  }

  if (alerts.length === 0) {
    return (
      <Card className={`${className} border-green-200 bg-green-50/30`}>
        <CardHeader className="py-3">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-green-600" />
            <CardTitle className="text-sm font-medium text-green-800">
              Sem alertas ativos
            </CardTitle>
          </div>
        </CardHeader>
      </Card>
    );
  }

  const borderColor = hasCritical ? "border-red-300" : hasHigh ? "border-orange-300" : "border-amber-200";
  const bgColor = hasCritical ? "bg-red-50/50" : hasHigh ? "bg-orange-50/50" : "bg-amber-50/30";

  return (
    <Card className={`${className} ${borderColor} ${bgColor}`} data-testid="process-alerts">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <CardHeader className="py-3 cursor-pointer hover:bg-muted/20 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className={`h-5 w-5 ${hasCritical ? 'text-red-600' : hasHigh ? 'text-orange-600' : 'text-amber-600'}`} />
                <CardTitle className="text-sm font-medium">
                  {alerts.length} Alerta{alerts.length !== 1 ? 's' : ''} Ativo{alerts.length !== 1 ? 's' : ''}
                </CardTitle>
                {hasCritical && <Badge className="bg-red-500 text-white text-xs">Crítico</Badge>}
                {!hasCritical && hasHigh && <Badge className="bg-orange-500 text-white text-xs">Alta</Badge>}
              </div>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        
        <CollapsibleContent>
          <CardContent className="pt-0 pb-3 space-y-2">
            {alerts.map((alert, index) => {
              const Icon = getIcon(alert.type);
              const colorClass = priorityColors[alert.priority] || priorityColors.medium;
              
              return (
                <div 
                  key={`${alert.type}-${index}`}
                  className={`flex items-start gap-3 p-3 rounded-lg border ${colorClass}`}
                  data-testid={`alert-${alert.type}`}
                >
                  <div className="shrink-0 mt-0.5">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">
                      {alert.message}
                    </p>
                    {alert.details && (
                      <p className="text-xs mt-1 opacity-80">
                        {alert.details}
                      </p>
                    )}
                    {alert.days_remaining !== undefined && (
                      <div className="mt-2">
                        <Badge variant="outline" className="text-xs">
                          {alert.days_remaining > 0 
                            ? `${alert.days_remaining} dias restantes`
                            : alert.days_remaining === 0 
                              ? 'Expira hoje!'
                              : `Expirado há ${Math.abs(alert.days_remaining)} dias`
                          }
                        </Badge>
                      </div>
                    )}
                  </div>
                  <Badge variant="outline" className="shrink-0 text-xs">
                    {priorityLabels[alert.priority] || alert.priority}
                  </Badge>
                </div>
              );
            })}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
};

export default ProcessAlerts;
