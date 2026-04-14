/**
 * AIDataReviewPage — Página de revisão de dados extraídos por IA de documentos.
 *
 * PORQUÊ: Quando a IA extrai dados de documentos (OCR), pode gerar conflitos entre valores de
 * diferentes documentos. Esta página permite ao utilizador rever, comparar e validar os dados
 * extraídos antes de os aplicar ao processo, garantindo a precisão dos dados no CRM.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { Progress } from "../components/ui/progress";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  Eye,
  Check,
  X,
  ArrowRight,
  Clock,
  User,
  FileSearch,
  AlertTriangle,
  Sparkles,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Calendar,
  Target,
  Info,
  Mail,
  Settings,
} from "lucide-react";
import { toast } from "sonner";
import api from "../services/api";

// Mapeamento de nomes de campos para português
const fieldLabels = {
  "personal_data.nome": "Nome Completo",
  "personal_data.nif": "NIF",
  "personal_data.cc_number": "Nº Cartão Cidadão",
  "personal_data.data_nascimento": "Data de Nascimento",
  "personal_data.data_validade_cc": "Validade do CC",
  "personal_data.morada": "Morada",
  "personal_data.codigo_postal": "Código Postal",
  "personal_data.localidade": "Localidade",
  "personal_data.estado_civil": "Estado Civil",
  "personal_data.nacionalidade": "Nacionalidade",
  "financial_data.rendimento_mensal": "Rendimento Mensal",
  "financial_data.entidade_patronal": "Entidade Patronal",
  "financial_data.tipo_contrato": "Tipo de Contrato",
  "financial_data.antiguidade": "Antiguidade",
  "financial_data.encargos_mensais": "Encargos Mensais",
  "real_estate_data.valor_imovel": "Valor do Imóvel",
  "real_estate_data.tipologia": "Tipologia",
  "real_estate_data.morada_imovel": "Morada do Imóvel",
  "real_estate_data.artigo_matricial": "Artigo Matricial",
  "client_name": "Nome do Cliente",
  "client_email": "Email",
  "client_phone": "Telefone",
  "client_nif": "NIF",
};

// Mapeamento de tipos de documento para português
const documentTypeLabels = {
  "cc": "Cartão de Cidadão",
  "recibo_vencimento": "Recibo de Vencimento",
  "irs": "Declaração IRS",
  "contrato_trabalho": "Contrato de Trabalho",
  "cpcv": "CPCV",
  "caderneta_predial": "Caderneta Predial",
  "simulacao": "Simulação de Crédito",
  "extrato_bancario": "Extrato Bancário",
  "outro": "Outro Documento",
};

const AIDataReviewPage = () => {
  const [activeTab, setActiveTab] = useState("review");
  const [pendingReviews, setPendingReviews] = useState([]);
  const [selectedProcess, setSelectedProcess] = useState(null);
  const [processComparison, setProcessComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [applyingField, setApplyingField] = useState(null);
  
  // Relatório semanal
  const [weeklyReport, setWeeklyReport] = useState(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  
  // Configurações do relatório
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [reportConfig, setReportConfig] = useState({
    enabled: true,
    frequency: "weekly",
    send_day: 0,
    send_hour: 9,
    recipients_type: "admins",
    custom_recipients: [],
    include_insights: true,
    include_charts: true
  });
  const [availableRecipients, setAvailableRecipients] = useState([]);
  const [savingConfig, setSavingConfig] = useState(false);

  // Labels para dias da semana
  const weekDays = [
    { value: "0", label: "Segunda-feira" },
    { value: "1", label: "Terça-feira" },
    { value: "2", label: "Quarta-feira" },
    { value: "3", label: "Quinta-feira" },
    { value: "4", label: "Sexta-feira" },
    { value: "5", label: "Sábado" },
    { value: "6", label: "Domingo" }
  ];

  // Labels para frequências
  const frequencies = [
    { value: "daily", label: "Diário" },
    { value: "weekly", label: "Semanal" },
    { value: "monthly", label: "Mensal" },
    { value: "disabled", label: "Desactivado" }
  ];

  // Carregar configuração do relatório
  const loadReportConfig = useCallback(async () => {
    try {
      const [configRes, recipientsRes] = await Promise.all([
        api.get("/admin/ai-report-config"),
        api.get("/admin/ai-report-recipients")
      ]);
      setReportConfig(configRes.data);
      setAvailableRecipients(recipientsRes.data.users || []);
    } catch (error) {
      console.error("Erro ao carregar configuração:", error);
    }
  }, []);

  // Guardar configuração
  const saveReportConfig = async () => {
    try {
      setSavingConfig(true);
      await api.put("/admin/ai-report-config", reportConfig);
      toast.success("Configurações guardadas com sucesso!");
      setConfigDialogOpen(false);
    } catch (error) {
      console.error("Erro ao guardar configuração:", error);
      toast.error("Erro ao guardar configurações");
    } finally {
      setSavingConfig(false);
    }
  };

  // Toggle destinatário personalizado
  const toggleCustomRecipient = (userId) => {
    setReportConfig(prev => ({
      ...prev,
      custom_recipients: prev.custom_recipients.includes(userId)
        ? prev.custom_recipients.filter(id => id !== userId)
        : [...prev.custom_recipients, userId]
    }));
  };

  // Enviar relatório por email
  const sendReportByEmail = async () => {
    try {
      setSendingEmail(true);
      const response = await api.post("/admin/ai-weekly-report/send");
      
      if (response.data.success) {
        toast.success(`Relatório enviado para ${response.data.recipients?.length || 0} administrador(es)!`);
      } else {
        toast.error(response.data.error || "Erro ao enviar relatório");
      }
    } catch (error) {
      console.error("Erro ao enviar relatório:", error);
      toast.error("Erro ao enviar relatório por email");
    } finally {
      setSendingEmail(false);
    }
  };

  // Carregar revisões pendentes
  const loadPendingReviews = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get("/ai/bulk/pending-reviews");
      setPendingReviews(response.data.processes || []);
    } catch (error) {
      console.error("Erro ao carregar revisões pendentes:", error);
      toast.error("Erro ao carregar revisões pendentes");
    } finally {
      setLoading(false);
    }
  }, []);

  // Carregar relatório semanal
  const loadWeeklyReport = useCallback(async () => {
    try {
      setLoadingReport(true);
      const response = await api.get("/admin/ai-weekly-report");
      // Backend retorna { success, report: {...} }
      if (response.data?.success && response.data?.report) {
        // Transformar estrutura do backend para formato esperado pelo frontend
        const report = response.data.report;
        const transformedReport = {
          summary: {
            total_documents_analyzed: report.usage_summary?.total_calls || 0,
            successful_extractions: report.usage_summary?.total_success || 0,
            success_rate: report.usage_summary?.success_rate || 0,
            comparison: {
              documents_variation_percent: 0,
              prev_week_total: 0,
              success_rate_variation: 0
            }
          },
          period: {
            start: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
            end: new Date().toISOString()
          },
          insights: [],
          by_document_type: report.by_task?.map(t => ({
            type: t.task_type,
            count: t.count,
            success_rate: t.success_rate
          })) || [],
          top_extracted_fields: report.by_model?.map(m => ({
            field: m.model,
            count: m.count
          })) || [],
          generated_at: report.generated_at
        };
        setWeeklyReport(transformedReport);
      } else {
        setWeeklyReport(null);
      }
    } catch (error) {
      console.error("Erro ao carregar relatório semanal:", error);
      toast.error("Erro ao carregar relatório semanal");
    } finally {
      setLoadingReport(false);
    }
  }, []);

  // Carregar comparação de dados do processo
  const loadProcessComparison = async (processId) => {
    try {
      setLoadingComparison(true);
      const response = await api.get(`/ai/bulk/compare-data/${processId}`);
      setProcessComparison(response.data);
    } catch (error) {
      console.error("Erro ao carregar comparação:", error);
      toast.error("Erro ao carregar comparação de dados");
    } finally {
      setLoadingComparison(false);
    }
  };

  // Aplicar dados pendentes
  const applyPendingData = async (processId, itemIndex, force = false) => {
    try {
      setApplyingField(`apply-${itemIndex}`);
      const response = await api.post(`/ai/bulk/apply-pending/${processId}?item_index=${itemIndex}&force=${force}`);
      
      if (response.data.success) {
        toast.success("Dados aplicados com sucesso!");
        await loadPendingReviews();
        if (selectedProcess?.process_id === processId) {
          await loadProcessComparison(processId);
        }
      } else {
        toast.error("Falha ao aplicar dados");
      }
    } catch (error) {
      console.error("Erro ao aplicar dados:", error);
      toast.error("Erro ao aplicar dados pendentes");
    } finally {
      setApplyingField(null);
    }
  };

  // Descartar dados pendentes
  const discardPendingData = async (processId, itemIndex) => {
    try {
      setApplyingField(`discard-${itemIndex}`);
      const response = await api.delete(`/ai/bulk/discard-pending/${processId}?item_index=${itemIndex}`);
      
      if (response.data.success) {
        toast.success("Dados descartados");
        await loadPendingReviews();
        if (selectedProcess?.process_id === processId) {
          await loadProcessComparison(processId);
        }
      }
    } catch (error) {
      console.error("Erro ao descartar dados:", error);
      toast.error("Erro ao descartar dados");
    } finally {
      setApplyingField(null);
    }
  };

  // Abrir dialog de detalhes
  const openProcessDetails = async (process) => {
    setSelectedProcess(process);
    setDialogOpen(true);
    await loadProcessComparison(process.process_id);
  };

  useEffect(() => {
    loadPendingReviews();
    loadWeeklyReport();
    loadReportConfig();
  }, [loadPendingReviews, loadWeeklyReport, loadReportConfig]);

  // Formatar data
  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    try {
      return new Date(dateStr).toLocaleDateString("pt-PT", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  // Obter label do campo
  const getFieldLabel = (field) => fieldLabels[field] || field;
  
  // Obter label do tipo de documento
  const getDocumentTypeLabel = (type) => documentTypeLabels[type] || type;

  // Formatar valor para exibição
  const formatValue = (value) => {
    if (value === null || value === undefined) return <span className="text-muted-foreground italic">Não preenchido</span>;
    if (typeof value === "boolean") return value ? "Sim" : "Não";
    if (typeof value === "number") {
      if (value >= 1000) return value.toLocaleString("pt-PT", { style: "currency", currency: "EUR" });
      return value.toString();
    }
    return String(value);
  };

  // Obter cor do insight
  const getInsightColor = (type) => {
    switch (type) {
      case "success": return "text-green-600 bg-green-50 border-green-200";
      case "warning": return "text-amber-600 bg-amber-50 border-amber-200";
      case "info": return "text-blue-600 bg-blue-50 border-blue-200";
      default: return "text-gray-600 bg-gray-50 border-gray-200";
    }
  };

  // Obter ícone do insight
  const getInsightIcon = (type) => {
    switch (type) {
      case "success": return <CheckCircle2 className="h-4 w-4" />;
      case "warning": return <AlertTriangle className="h-4 w-4" />;
      case "info": return <Info className="h-4 w-4" />;
      default: return <AlertCircle className="h-4 w-4" />;
    }
  };

  return (
    <DashboardLayout title="Revisão de Dados IA">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Revisão de Dados IA</h1>
            <p className="text-muted-foreground">
              Compare dados extraídos pela IA e visualize estatísticas semanais
            </p>
          </div>
          <Button 
            onClick={() => {
              loadPendingReviews();
              loadWeeklyReport();
            }} 
            variant="outline" 
            disabled={loading || loadingReport}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${(loading || loadingReport) ? "animate-spin" : ""}`} />
            Actualizar
          </Button>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2 max-w-md">
            <TabsTrigger value="review" className="flex items-center gap-2">
              <FileSearch className="h-4 w-4" />
              Revisão de Dados
            </TabsTrigger>
            <TabsTrigger value="report" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Relatório Semanal
            </TabsTrigger>
          </TabsList>

          {/* Tab: Revisão de Dados */}
          <TabsContent value="review" className="mt-6 space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Processos Pendentes
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <FileSearch className="h-5 w-5 text-amber-500" />
                    <span className="text-2xl font-bold">{pendingReviews.length}</span>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Total de Itens para Revisão
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-orange-500" />
                    <span className="text-2xl font-bold">
                      {pendingReviews.reduce((acc, p) => acc + (p.pending_count || 0), 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Tipos de Documentos
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <FileText className="h-5 w-5 text-blue-500" />
                    <span className="text-2xl font-bold">
                      {[...new Set(pendingReviews.flatMap(p => p.document_types || []))].length}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Pending Reviews Table */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-amber-500" />
                  Processos com Dados Pendentes de Revisão
                </CardTitle>
                <CardDescription>
                  Estes processos têm dados extraídos pela IA que aguardam validação manual
                </CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex justify-center items-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                ) : pendingReviews.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <CheckCircle2 className="h-12 w-12 text-green-500 mb-4" />
                    <h3 className="text-lg font-medium">Tudo em dia!</h3>
                    <p className="text-muted-foreground mt-1">
                      Não há dados pendentes de revisão
                    </p>
                  </div>
                ) : (
                  <ScrollArea className="h-[400px] overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Cliente</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Itens Pendentes</TableHead>
                          <TableHead>Tipos de Documento</TableHead>
                          <TableHead>Mais Antigo</TableHead>
                          <TableHead className="text-right">Acções</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {pendingReviews.map((process) => (
                          <TableRow key={process.process_id} data-testid={`review-row-${process.process_id}`}>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <User className="h-4 w-4 text-muted-foreground" />
                                <span className="font-medium">{process.client_name}</span>
                              </div>
                            </TableCell>
                            <TableCell>
                              <Badge variant={process.status === "concluido" ? "secondary" : "outline"}>
                                {process.status}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="destructive" className="tabular-nums">
                                {process.pending_count}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                {(process.document_types || []).slice(0, 3).map((type) => (
                                  <Badge key={type} variant="outline" className="text-xs">
                                    {getDocumentTypeLabel(type)}
                                  </Badge>
                                ))}
                                {(process.document_types || []).length > 3 && (
                                  <Badge variant="outline" className="text-xs">
                                    +{process.document_types.length - 3}
                                  </Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1 text-muted-foreground text-sm">
                                <Clock className="h-3 w-3" />
                                {formatDate(process.oldest_pending)}
                              </div>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                size="sm"
                                onClick={() => openProcessDetails(process)}
                                data-testid={`review-details-btn-${process.process_id}`}
                              >
                                <Eye className="h-4 w-4 mr-1" />
                                Rever
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab: Relatório Semanal */}
          <TabsContent value="report" className="mt-6 space-y-6">
            {loadingReport ? (
              <div className="flex justify-center items-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : weeklyReport ? (
              <>
                {/* Summary Cards */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        Documentos Analisados
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-baseline gap-2">
                        <span className="text-3xl font-bold">
                          {weeklyReport.summary.total_documents_analyzed}
                        </span>
                        {weeklyReport.summary.comparison.documents_variation_percent !== 0 && (
                          <span className={`flex items-center text-sm ${
                            weeklyReport.summary.comparison.documents_variation_percent > 0 
                              ? "text-green-600" 
                              : "text-red-600"
                          }`}>
                            {weeklyReport.summary.comparison.documents_variation_percent > 0 ? (
                              <TrendingUp className="h-3 w-3 mr-1" />
                            ) : (
                              <TrendingDown className="h-3 w-3 mr-1" />
                            )}
                            {Math.abs(weeklyReport.summary.comparison.documents_variation_percent)}%
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        vs. {weeklyReport.summary.comparison.prev_week_total} semana anterior
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                        <Target className="h-4 w-4" />
                        Taxa de Sucesso
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-baseline gap-2">
                        <span className="text-3xl font-bold">
                          {weeklyReport.summary.success_rate}%
                        </span>
                        {weeklyReport.summary.comparison.success_rate_variation !== 0 && (
                          <span className={`flex items-center text-sm ${
                            weeklyReport.summary.comparison.success_rate_variation > 0 
                              ? "text-green-600" 
                              : "text-red-600"
                          }`}>
                            {weeklyReport.summary.comparison.success_rate_variation > 0 ? (
                              <TrendingUp className="h-3 w-3 mr-1" />
                            ) : (
                              <TrendingDown className="h-3 w-3 mr-1" />
                            )}
                            {Math.abs(weeklyReport.summary.comparison.success_rate_variation).toFixed(1)}pp
                          </span>
                        )}
                      </div>
                      <Progress 
                        value={weeklyReport.summary.success_rate} 
                        className="h-2 mt-2"
                      />
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4" />
                        Extracções com Sucesso
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <span className="text-3xl font-bold text-green-600">
                        {weeklyReport.summary.successful_extractions}
                      </span>
                      <p className="text-xs text-muted-foreground mt-1">
                        de {weeklyReport.summary.total_documents_analyzed} documentos
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                        <Calendar className="h-4 w-4" />
                        Período
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm font-medium">Últimos 7 dias</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {new Date(weeklyReport.period.start).toLocaleDateString("pt-PT")} - {new Date(weeklyReport.period.end).toLocaleDateString("pt-PT")}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                {/* Botão enviar por email */}
                <div className="flex justify-end">
                  <Button
                    onClick={sendReportByEmail}
                    disabled={sendingEmail}
                    variant="outline"
                    className="gap-2"
                    data-testid="send-report-email-btn"
                  >
                    {sendingEmail ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Mail className="h-4 w-4" />
                    )}
                    {sendingEmail ? "A enviar..." : "Enviar por Email"}
                  </Button>
                  <Button
                    onClick={() => setConfigDialogOpen(true)}
                    variant="outline"
                    className="gap-2"
                    data-testid="config-report-btn"
                  >
                    <Settings className="h-4 w-4" />
                    Configurações
                  </Button>
                </div>

                {/* Insights */}
                {weeklyReport.insights && weeklyReport.insights.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-amber-500" />
                        Insights Automáticos
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {weeklyReport.insights.map((insight, idx) => (
                        <div 
                          key={idx}
                          className={`flex items-start gap-3 p-3 rounded-lg border ${getInsightColor(insight.type)}`}
                        >
                          {getInsightIcon(insight.type)}
                          <p className="text-sm">{insight.message}</p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Charts Row */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* By Document Type */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Por Tipo de Documento</CardTitle>
                      <CardDescription>Distribuição das análises por tipo</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {weeklyReport.by_document_type.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-4">
                          Nenhum documento analisado neste período
                        </p>
                      ) : (
                        <div className="space-y-3">
                          {weeklyReport.by_document_type.map((item) => (
                            <div key={item.type} className="space-y-1">
                              <div className="flex justify-between text-sm">
                                <span>{item.label}</span>
                                <span className="font-medium">{item.count} ({item.percentage}%)</span>
                              </div>
                              <Progress value={item.percentage} className="h-2" />
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Top Extracted Fields */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Campos Mais Extraídos</CardTitle>
                      <CardDescription>Top 10 campos com extracção bem-sucedida</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {weeklyReport.top_extracted_fields.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-4">
                          Nenhum campo extraído neste período
                        </p>
                      ) : (
                        <ScrollArea className="h-[250px] overflow-x-auto">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Campo</TableHead>
                                <TableHead className="text-right">Extrações</TableHead>
                                <TableHead className="text-right">%</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {weeklyReport.top_extracted_fields.map((field, idx) => (
                                <TableRow key={field.field}>
                                  <TableCell className="font-medium">
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                                      {field.label}
                                    </div>
                                  </TableCell>
                                  <TableCell className="text-right tabular-nums">
                                    {field.count}
                                  </TableCell>
                                  <TableCell className="text-right tabular-nums text-muted-foreground">
                                    {field.percentage}%
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </ScrollArea>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium">Sem dados disponíveis</h3>
                <p className="text-muted-foreground mt-1">
                  Não foi possível carregar o relatório semanal
                </p>
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Dialog de Detalhes */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileSearch className="h-5 w-5 text-amber-500" />
                Revisão de Dados - {selectedProcess?.client_name}
              </DialogTitle>
              <DialogDescription>
                Compare os dados actuais com os dados extraídos pela IA e escolha quais aplicar
              </DialogDescription>
            </DialogHeader>

            {loadingComparison ? (
              <div className="flex justify-center items-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : processComparison ? (
              <Tabs defaultValue="differences" className="w-full">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="differences">
                    Diferenças ({processComparison.fields_with_differences})
                  </TabsTrigger>
                  <TabsTrigger value="all">
                    Todos os Campos ({processComparison.total_fields_compared})
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="differences" className="mt-4">
                  <ScrollArea className="h-[400px]">
                    {processComparison.comparisons
                      .filter((c) => c.has_difference)
                      .map((comparison, idx) => (
                        <Card key={comparison.field} className="mb-3" data-testid={`comparison-card-${comparison.field}`}>
                          <CardContent className="pt-4">
                            <div className="flex flex-col gap-3">
                              <div className="flex items-center justify-between">
                                <span className="font-medium text-sm">
                                  {getFieldLabel(comparison.field)}
                                </span>
                                {comparison.has_pending && (
                                  <Badge variant="destructive" className="text-xs">
                                    Pendente
                                  </Badge>
                                )}
                              </div>
                              
                              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
                                {/* Valor Actual */}
                                <div className="p-3 bg-muted rounded-lg">
                                  <p className="text-xs text-muted-foreground mb-1">Valor Actual</p>
                                  <p className="font-medium">{formatValue(comparison.current_value)}</p>
                                </div>

                                {/* Seta */}
                                <div className="flex items-center justify-center">
                                  <ArrowRight className="h-5 w-5 text-muted-foreground" />
                                </div>

                                {/* Valor Extraído */}
                                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                  <p className="text-xs text-amber-700 mb-1">
                                    {comparison.pending_document
                                      ? `Extraído de ${getDocumentTypeLabel(comparison.pending_document)}`
                                      : `Extraído de ${getDocumentTypeLabel(comparison.latest_document)}`}
                                  </p>
                                  <p className="font-medium text-amber-900">
                                    {formatValue(comparison.pending_value || comparison.latest_extracted)}
                                  </p>
                                  {(comparison.pending_value || comparison.latest_date) && (
                                    <p className="text-xs text-amber-600 mt-1">
                                      {formatDate(comparison.latest_date)}
                                    </p>
                                  )}
                                </div>
                              </div>

                              {/* Acções para campos pendentes */}
                              {comparison.has_pending && (
                                <div className="flex justify-end gap-2 mt-2">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => discardPendingData(selectedProcess.process_id, idx)}
                                    disabled={applyingField !== null}
                                    data-testid={`discard-btn-${comparison.field}`}
                                  >
                                    {applyingField === `discard-${idx}` ? (
                                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                                    ) : (
                                      <X className="h-4 w-4 mr-1" />
                                    )}
                                    Descartar
                                  </Button>
                                  <Button
                                    size="sm"
                                    onClick={() => applyPendingData(selectedProcess.process_id, idx)}
                                    disabled={applyingField !== null}
                                    data-testid={`apply-btn-${comparison.field}`}
                                  >
                                    {applyingField === `apply-${idx}` ? (
                                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                                    ) : (
                                      <Check className="h-4 w-4 mr-1" />
                                    )}
                                    Aplicar
                                  </Button>
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    
                    {processComparison.comparisons.filter((c) => c.has_difference).length === 0 && (
                      <div className="flex flex-col items-center justify-center py-8 text-center">
                        <CheckCircle2 className="h-10 w-10 text-green-500 mb-3" />
                        <p className="text-muted-foreground">
                          Não há diferenças entre os dados actuais e os extraídos
                        </p>
                      </div>
                    )}
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="all" className="mt-4">
                  <ScrollArea className="h-[400px] overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Campo</TableHead>
                          <TableHead>Valor Actual</TableHead>
                          <TableHead>Último Extraído</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {processComparison.comparisons.map((comparison) => (
                          <TableRow
                            key={comparison.field}
                            className={comparison.has_difference ? "bg-amber-50/50" : ""}
                          >
                            <TableCell className="font-medium text-sm">
                              {getFieldLabel(comparison.field)}
                            </TableCell>
                            <TableCell className="text-sm">
                              {formatValue(comparison.current_value)}
                            </TableCell>
                            <TableCell className="text-sm">
                              {formatValue(comparison.latest_extracted)}
                            </TableCell>
                            <TableCell>
                              {comparison.has_pending ? (
                                <Badge variant="destructive" className="text-xs">Pendente</Badge>
                              ) : comparison.has_difference ? (
                                <Badge variant="outline" className="text-xs text-amber-700 border-amber-300">Diferente</Badge>
                              ) : (
                                <Badge variant="outline" className="text-xs text-green-700 border-green-300">OK</Badge>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            ) : null}

            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Fechar
              </Button>
              <Button
                variant="default"
                onClick={() => window.open(`/processo/${selectedProcess?.process_id}`, "_blank")}
              >
                <Eye className="h-4 w-4 mr-2" />
                Ver Processo Completo
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Modal de Configurações do Relatório */}
        <Dialog open={configDialogOpen} onOpenChange={setConfigDialogOpen}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Configurações do Relatório
              </DialogTitle>
              <DialogDescription>
                Configure a periodicidade e os destinatários do relatório automático
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 py-4">
              {/* Activar/Desactivar */}
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Relatório Automático</Label>
                  <p className="text-xs text-muted-foreground">
                    Enviar relatório automaticamente
                  </p>
                </div>
                <Switch
                  checked={reportConfig.enabled && reportConfig.frequency !== "disabled"}
                  onCheckedChange={(checked) => 
                    setReportConfig(prev => ({
                      ...prev,
                      enabled: checked,
                      frequency: checked ? (prev.frequency === "disabled" ? "weekly" : prev.frequency) : "disabled"
                    }))
                  }
                />
              </div>

              {/* Frequência */}
              <div className="space-y-2">
                <Label>Frequência</Label>
                <Select
                  value={reportConfig.frequency}
                  onValueChange={(value) => setReportConfig(prev => ({ ...prev, frequency: value }))}
                  disabled={!reportConfig.enabled}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Seleccione a frequência" />
                  </SelectTrigger>
                  <SelectContent>
                    {frequencies.map(f => (
                      <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Dia da semana (apenas para semanal) */}
              {reportConfig.frequency === "weekly" && (
                <div className="space-y-2">
                  <Label>Dia de Envio</Label>
                  <Select
                    value={String(reportConfig.send_day)}
                    onValueChange={(value) => setReportConfig(prev => ({ ...prev, send_day: parseInt(value) }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Seleccione o dia" />
                    </SelectTrigger>
                    <SelectContent>
                      {weekDays.map(d => (
                        <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Hora de envio */}
              <div className="space-y-2">
                <Label>Hora de Envio</Label>
                <Select
                  value={String(reportConfig.send_hour)}
                  onValueChange={(value) => setReportConfig(prev => ({ ...prev, send_hour: parseInt(value) }))}
                  disabled={!reportConfig.enabled || reportConfig.frequency === "disabled"}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Seleccione a hora" />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 24 }, (_, i) => (
                      <SelectItem key={i} value={String(i)}>
                        {String(i).padStart(2, "0")}:00
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Destinatários */}
              <div className="space-y-2">
                <Label>Destinatários</Label>
                <Select
                  value={reportConfig.recipients_type}
                  onValueChange={(value) => setReportConfig(prev => ({ ...prev, recipients_type: value }))}
                  disabled={!reportConfig.enabled || reportConfig.frequency === "disabled"}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Seleccione os destinatários" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admins">Administradores e CEOs</SelectItem>
                    <SelectItem value="all_staff">Toda a Equipa</SelectItem>
                    <SelectItem value="custom">Personalizado</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Lista de destinatários personalizados */}
              {reportConfig.recipients_type === "custom" && (
                <div className="space-y-2">
                  <Label>Seleccionar Destinatários</Label>
                  <ScrollArea className="h-[150px] border rounded-md p-3">
                    {availableRecipients.map((user) => (
                      <div key={user.id} className="flex items-center space-x-2 py-1">
                        <Checkbox
                          id={user.id}
                          checked={reportConfig.custom_recipients.includes(user.id)}
                          onCheckedChange={() => toggleCustomRecipient(user.id)}
                        />
                        <label
                          htmlFor={user.id}
                          className="text-sm cursor-pointer flex-1"
                        >
                          {user.name}
                          <span className="text-xs text-muted-foreground ml-2">
                            ({user.email})
                          </span>
                        </label>
                      </div>
                    ))}
                  </ScrollArea>
                  <p className="text-xs text-muted-foreground">
                    {reportConfig.custom_recipients.length} destinatário(s) seleccionado(s)
                  </p>
                </div>
              )}

              {/* Opções adicionais */}
              <div className="space-y-3 pt-2 border-t">
                <Label className="text-sm font-medium">Opções do Conteúdo</Label>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="include_insights"
                    checked={reportConfig.include_insights}
                    onCheckedChange={(checked) => 
                      setReportConfig(prev => ({ ...prev, include_insights: !!checked }))
                    }
                  />
                  <label htmlFor="include_insights" className="text-sm cursor-pointer">
                    Incluir insights automáticos
                  </label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="include_charts"
                    checked={reportConfig.include_charts}
                    onCheckedChange={(checked) => 
                      setReportConfig(prev => ({ ...prev, include_charts: !!checked }))
                    }
                  />
                  <label htmlFor="include_charts" className="text-sm cursor-pointer">
                    Incluir gráficos e estatísticas detalhadas
                  </label>
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setConfigDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={saveReportConfig} disabled={savingConfig}>
                {savingConfig ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Check className="h-4 w-4 mr-2" />
                )}
                Guardar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default AIDataReviewPage;

