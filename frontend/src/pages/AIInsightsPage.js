/**
 * AIInsightsPage - Página de Insights e Sugestões de IA
 * Mostra análise preditiva e prescritiva dos processos
 */
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Progress } from "../components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../components/ui/accordion";
import { toast } from "sonner";
import {
  Brain,
  AlertTriangle,
  Lightbulb,
  TrendingUp,
  Users,
  Clock,
  RefreshCw,
  Loader2,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  ArrowUpRight,
  BarChart3,
  Target,
  Zap,
} from "lucide-react";
import { format } from "date-fns";
import { pt } from "date-fns/locale";
import { useNavigate } from "react-router-dom";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Cores por severidade
const SEVERITY_COLORS = {
  high: "bg-red-100 text-red-800 border-red-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-blue-100 text-blue-800 border-blue-200",
};

const SEVERITY_ICONS = {
  high: <AlertTriangle className="h-4 w-4 text-red-500" />,
  medium: <AlertCircle className="h-4 w-4 text-yellow-500" />,
  low: <Clock className="h-4 w-4 text-blue-500" />,
};

// Cores por prioridade de sugestão
const PRIORITY_COLORS = {
  high: "border-l-4 border-l-red-500",
  medium: "border-l-4 border-l-yellow-500",
  low: "border-l-4 border-l-green-500",
};

const AIInsightsPage = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");

  // Fetch analysis data
  const fetchAnalysis = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    else setRefreshing(true);

    try {
      const response = await fetch(`${API_URL}/api/ai-agent/analyze`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const result = await response.json();
        setData(result);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao carregar análise");
      }
    } catch (error) {
      console.error("Error fetching analysis:", error);
      toast.error("Erro de conexão");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    fetchAnalysis();
  }, [fetchAnalysis]);

  // Formatar data
  const formatDate = (dateStr) => {
    try {
      return format(new Date(dateStr), "d MMM yyyy, HH:mm", { locale: pt });
    } catch {
      return dateStr;
    }
  };

  // Navegar para processo
  const goToProcess = (processId) => {
    navigate(`/processo/${processId}`);
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-center">
            <Brain className="h-12 w-12 mx-auto mb-4 text-primary animate-pulse" />
            <p className="text-muted-foreground">A analisar processos...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  const stats = data?.stats || {};
  const alerts = data?.alerts || [];
  const suggestions = data?.suggestions || [];

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="ai-insights-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Brain className="h-6 w-6 text-primary" />
              Agente de Melhoria IA
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Análise preditiva e sugestões para optimizar processos
            </p>
          </div>
          <div className="flex items-center gap-2">
            {data?.generated_at && (
              <span className="text-xs text-muted-foreground">
                Actualizado: {formatDate(data.generated_at)}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => fetchAnalysis(false)}
              disabled={refreshing}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              Actualizar
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Processos Analisados</p>
                  <p className="text-2xl font-bold">{data?.total_analyzed || 0}</p>
                </div>
                <BarChart3 className="h-8 w-8 text-blue-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Alertas Activos</p>
                  <p className="text-2xl font-bold text-red-500">{alerts.length}</p>
                </div>
                <AlertTriangle className="h-8 w-8 text-red-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Processos Parados</p>
                  <p className="text-2xl font-bold text-yellow-500">
                    {stats.stalled_processes || 0}
                    <span className="text-sm font-normal text-muted-foreground ml-1">
                      ({stats.stalled_percentage || 0}%)
                    </span>
                  </p>
                </div>
                <Clock className="h-8 w-8 text-yellow-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Tempo Médio</p>
                  <p className="text-2xl font-bold">{stats.avg_days_in_system || 0} dias</p>
                </div>
                <TrendingUp className="h-8 w-8 text-green-500 opacity-50" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Content */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="overview" className="gap-2">
              <Target className="h-4 w-4" />
              Visão Geral
            </TabsTrigger>
            <TabsTrigger value="suggestions" className="gap-2">
              <Lightbulb className="h-4 w-4" />
              Sugestões ({suggestions.length})
            </TabsTrigger>
            <TabsTrigger value="alerts" className="gap-2">
              <AlertTriangle className="h-4 w-4" />
              Alertas ({alerts.length})
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="mt-4 space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Por Status */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Processos por Estado</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {Object.entries(stats.by_status || {}).map(([status, count]) => (
                      <div key={status} className="flex items-center justify-between">
                        <span className="text-sm">{status}</span>
                        <div className="flex items-center gap-2">
                          <Progress
                            value={(count / (data?.total_analyzed || 1)) * 100}
                            className="w-24 h-2"
                          />
                          <span className="text-sm font-medium w-8 text-right">{count}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Por Consultor */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Processos por Consultor</CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-[200px]">
                    <div className="space-y-3">
                      {Object.entries(stats.by_consultant || {})
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 10)
                        .map(([consultant, count]) => (
                          <div key={consultant} className="flex items-center justify-between">
                            <span className="text-sm truncate max-w-[200px]">{consultant}</span>
                            <Badge variant="secondary">{count}</Badge>
                          </div>
                        ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            </div>

            {/* Top Sugestões */}
            {suggestions.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Zap className="h-4 w-4 text-yellow-500" />
                    Sugestões Prioritárias
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {suggestions.slice(0, 3).map((suggestion, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-lg bg-card border ${PRIORITY_COLORS[suggestion.priority] || ''}`}
                      >
                        <div className="flex items-start justify-between">
                          <div>
                            <p className="font-medium text-sm">{suggestion.title}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {suggestion.description}
                            </p>
                          </div>
                          {suggestion.generated_by === "AI" && (
                            <Badge variant="outline" className="text-[10px]">
                              <Brain className="h-3 w-3 mr-1" />
                              IA
                            </Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Suggestions Tab */}
          <TabsContent value="suggestions" className="mt-4">
            <Card>
              <CardContent className="p-4">
                {suggestions.length > 0 ? (
                  <div className="space-y-4">
                    {suggestions.map((suggestion, idx) => (
                      <div
                        key={idx}
                        className={`p-4 rounded-lg bg-card border ${PRIORITY_COLORS[suggestion.priority] || ''}`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Lightbulb className="h-5 w-5 text-yellow-500" />
                            <span className="font-medium">{suggestion.title}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={
                                suggestion.priority === "high"
                                  ? "text-red-500"
                                  : suggestion.priority === "medium"
                                  ? "text-yellow-500"
                                  : "text-green-500"
                              }
                            >
                              {suggestion.priority === "high"
                                ? "Alta"
                                : suggestion.priority === "medium"
                                ? "Média"
                                : "Baixa"}
                            </Badge>
                            {suggestion.generated_by === "AI" && (
                              <Badge variant="secondary" className="text-xs">
                                <Brain className="h-3 w-3 mr-1" />
                                IA
                              </Badge>
                            )}
                          </div>
                        </div>
                        <p className="text-sm text-muted-foreground mb-3">
                          {suggestion.description}
                        </p>
                        <div className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-4">
                            <span className="text-muted-foreground">
                              <strong>Acção:</strong> {suggestion.action}
                            </span>
                          </div>
                          <span className="text-green-600">
                            <strong>Impacto:</strong> {suggestion.impact}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-500" />
                    <p>Sem sugestões de melhoria no momento</p>
                    <p className="text-sm">Os processos estão a decorrer normalmente</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Alerts Tab */}
          <TabsContent value="alerts" className="mt-4">
            <Card>
              <CardContent className="p-4">
                {alerts.length > 0 ? (
                  <Accordion type="single" collapsible className="w-full">
                    {alerts.map((alert, idx) => (
                      <AccordionItem key={idx} value={`alert-${idx}`}>
                        <AccordionTrigger className="hover:no-underline">
                          <div className="flex items-center gap-3 text-left">
                            {SEVERITY_ICONS[alert.severity]}
                            <div>
                              <p className="font-medium text-sm">{alert.client_name}</p>
                              <p className="text-xs text-muted-foreground">{alert.message}</p>
                            </div>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="pl-7 space-y-2">
                            <div className="flex items-center gap-2">
                              <Badge className={SEVERITY_COLORS[alert.severity]}>
                                {alert.severity === "high"
                                  ? "Alta Prioridade"
                                  : alert.severity === "medium"
                                  ? "Média Prioridade"
                                  : "Baixa Prioridade"}
                              </Badge>
                              <Badge variant="outline">{alert.type}</Badge>
                            </div>
                            <p className="text-sm">
                              <strong>Sugestão:</strong> {alert.suggestion}
                            </p>
                            {alert.days_stalled && (
                              <p className="text-sm text-muted-foreground">
                                Parado há {alert.days_stalled} dias
                              </p>
                            )}
                            <Button
                              size="sm"
                              variant="outline"
                              className="mt-2"
                              onClick={() => goToProcess(alert.process_id)}
                            >
                              Ver Processo
                              <ArrowUpRight className="h-4 w-4 ml-1" />
                            </Button>
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-green-500" />
                    <p>Sem alertas activos</p>
                    <p className="text-sm">Todos os processos estão em bom estado</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default AIInsightsPage;
