/**
 * ClientDetailPage — Página de ficha detalhada de um cliente.
 *
 * PORQUÊ: Antes desta página, o botão "Ver Ficha" nos clientes navegava para o
 * primeiro processo do cliente, não para uma página própria do cliente. Esta página
 * centraliza todos os dados do cliente (pessoais, contacto, processos associados)
 * numa vista dedicada, seguindo o padrão visual do PowerCell.
 *
 * ROTA: /cliente/:id (ID do cliente, não do processo)
 *
 * @context {AuthContext} — Consome user para autenticação e permissões
 */

import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Separator } from "../components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  ArrowLeft,
  User,
  Phone,
  Mail,
  Hash,
  MapPin,
  Briefcase,
  Heart,
  Calendar,
  Tag,
  FileText,
  ExternalLink,
  Loader2,
  AlertCircle,
  RefreshCw,
  Info,
} from "lucide-react";
import { toast } from "sonner";
import { getClient } from "../services/api";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

/**
 * Calcula a cor de texto (preto ou branco) com base na luminosidade da cor de fundo.
 */
const getContrastColor = (bgColor) => {
  if (!bgColor) return "#ffffff";
  const namedColors = {
    yellow: "#EAB308",
    orange: "#F97316",
    blue: "#3B82F6",
    green: "#22C55E",
    red: "#EF4444",
    purple: "#A855F7",
    gray: "#6B7280",
    grey: "#6B7280",
  };
  let hex = namedColors[bgColor?.toLowerCase()] || bgColor;
  if (!hex.startsWith("#")) return "#ffffff";
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? "#1a1a1a" : "#ffffff";
};

/**
 * Formata um tipo de processo: substitui underscores por espaços e capitaliza.
 */
const formatProcessType = (type) => {
  if (!type) return "-";
  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * Retorna a classe de cor do badge de prioridade.
 */
const getPriorityBadge = (priority) => {
  const p = (priority || "").toLowerCase();
  if (p === "alta" || p === "high")
    return "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800";
  if (p === "media" || p === "medium")
    return "bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-800";
  if (p === "baixa" || p === "low")
    return "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800";
  return "bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700";
};

/**
 * Retorna a classe de cor do badge de status.
 */
const getStatusBadgeClasses = (statusColor) => {
  return {
    backgroundColor: statusColor || "#6B7280",
    color: getContrastColor(statusColor),
  };
};

const formatDate = (dateString) => {
  if (!dateString) return "-";
  try {
    return format(parseISO(dateString), "dd MMM yyyy", { locale: pt });
  } catch {
    return dateString;
  }
};

export default function ClientDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchClientData = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      // Fetch client data (backend returns processes array with enriched data)
      const clientRes = await getClient(id);
      const clientData = clientRes.data;
      setClient(clientData);

      // Processes are now included in the client response from the backend
      if (clientData.processes && Array.isArray(clientData.processes)) {
        setProcesses(clientData.processes);
      } else {
        setProcesses([]);
      }
    } catch (err) {
      console.error("Erro ao carregar cliente:", err);
      if (err.response?.status === 404) {
        setError("Cliente não encontrado.");
      } else {
        setError("Erro ao carregar dados do cliente. Tente novamente.");
      }
      toast.error("Erro ao carregar dados do cliente");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchClientData();
  }, [fetchClientData]);

  // Loading state
  if (loading) {
    return (
      <DashboardLayout title="Ficha do Cliente">
        <div className="flex items-center justify-center min-h-[400px]" data-testid="loading-state">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-muted-foreground text-sm">A carregar ficha do cliente...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // Error state
  if (error || !client) {
    return (
      <DashboardLayout title="Ficha do Cliente">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="flex flex-col items-center gap-4 text-center max-w-md">
            <div className="p-4 bg-red-100 dark:bg-red-900/30 rounded-full">
              <AlertCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
            </div>
            <h2 className="text-xl font-semibold">
              {error || "Cliente não encontrado"}
            </h2>
            <p className="text-muted-foreground text-sm">
              Não foi possível carregar os dados deste cliente.
            </p>
            <Button
              variant="outline"
              onClick={() => navigate("/clientes")}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Voltar aos Clientes
            </Button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  const contato = client.contacto || {};
  const dadosPessoais = client.dados_pessoais || {};

  return (
    <DashboardLayout title="Ficha do Cliente">
      <div className="space-y-6" data-testid="client-detail-page">
        {/* Header with back button */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/clientes")}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Button>
          <div className="flex-1">
            <h1 className="text-2xl font-bold flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="text-lg font-semibold text-primary">
                  {client.nome?.charAt(0)?.toUpperCase() || "?"}
                </span>
              </div>
              {client.nome}
            </h1>
            <p className="text-muted-foreground text-sm mt-1 ml-[52px]">
              Ficha do Cliente
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchClientData}
            className="gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Client Info Card - spans 2 columns on large screens */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <User className="h-5 w-5 text-primary" />
                Dados do Cliente
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Contact & Personal Data Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
                {/* NIF */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Hash className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">NIF</p>
                    <p className="font-medium font-mono">{dadosPessoais.nif || "-"}</p>
                  </div>
                </div>

                {/* Email */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Email</p>
                    {contato.email ? (
                      <a
                        href={`mailto:${contato.email}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {contato.email}
                      </a>
                    ) : (
                      <p className="font-medium">-</p>
                    )}
                  </div>
                </div>

                {/* Telefone */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Telefone</p>
                    {contato.telefone ? (
                      <a
                        href={`tel:${contato.telefone}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {contato.telefone}
                      </a>
                    ) : (
                      <p className="font-medium">-</p>
                    )}
                  </div>
                </div>

                {/* Estado Civil */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Heart className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Estado Civil</p>
                    <p className="font-medium">{dadosPessoais.estado_civil || "-"}</p>
                  </div>
                </div>

                {/* Profissão */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Briefcase className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Profissão</p>
                    <p className="font-medium">{dadosPessoais.profissao || "-"}</p>
                  </div>
                </div>

                {/* Morada Fiscal */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Morada Fiscal</p>
                    <p className="font-medium">{dadosPessoais.morada_fiscal || "-"}</p>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Fonte & Tags row */}
              <div className="flex flex-col sm:flex-row gap-6">
                {/* Fonte */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Fonte</p>
                    {client.fonte ? (
                      <Badge variant="outline" className="mt-0.5">
                        {client.fonte}
                      </Badge>
                    ) : (
                      <p className="font-medium">-</p>
                    )}
                  </div>
                </div>

                {/* Tags */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Tag className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Tags</p>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {client.tags && client.tags.length > 0 ? (
                        client.tags.map((tag, idx) => (
                          <Badge key={idx} variant="secondary" className="text-xs">
                            {tag}
                          </Badge>
                        ))
                      ) : (
                        <p className="font-medium">-</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Data de Criação */}
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-muted rounded-lg mt-0.5">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider">Data de Criação</p>
                    <p className="font-medium">{formatDate(client.created_at)}</p>
                  </div>
                </div>
              </div>

              {/* Notas */}
              {client.notas && (
                <>
                  <Separator />
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Notas</p>
                    <div className="bg-muted/50 rounded-lg p-3 text-sm whitespace-pre-wrap">
                      {client.notas}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Side info card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" />
                Resumo
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <FileText className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{processes.length}</p>
                  <p className="text-xs text-muted-foreground">Processos Associados</p>
                </div>
              </div>

              <Separator />

              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <FileText className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold">
                    {processes.filter((p) => p.is_active !== false).length}
                  </p>
                  <p className="text-xs text-muted-foreground">Processos Ativos</p>
                </div>
              </div>

              {client.process_ids && client.process_ids.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wider mb-2">
                      IDs dos Processos
                    </p>
                    <div className="space-y-1">
                      {client.process_ids.map((pid, idx) => (
                        <p key={idx} className="text-xs font-mono text-muted-foreground">
                          {pid}
                        </p>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Associated Processes Table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Processos Associados
            </CardTitle>
          </CardHeader>
          <CardContent>
            {processes.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  Este cliente ainda não tem processos associados.
                </p>
              </div>
            ) : (
              <>
                {/* Desktop Table */}
                <div className="hidden md:block overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50">
                        <TableHead>Nº Processo</TableHead>
                        <TableHead>Tipo</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Prioridade</TableHead>
                        <TableHead>Data Criação</TableHead>
                        <TableHead className="text-right">Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {processes.map((process) => (
                        <TableRow key={process.id}>
                          <TableCell>
                            <span className="font-mono font-medium">
                              {process.process_number || process.id?.substring(0, 8) || "-"}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs">
                              {formatProcessType(process.process_type)}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {process.status_label || process.status ? (
                              <Badge
                                className="text-xs"
                                style={getStatusBadgeClasses(process.status_color)}
                              >
                                {process.status_label || process.status}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell>
                            {process.prioridade || process.priority ? (
                              <Badge
                                variant="outline"
                                className={`text-xs ${getPriorityBadge(process.prioridade || process.priority)}`}
                              >
                                {process.prioridade || process.priority}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDate(process.created_at)}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => navigate(`/process/${process.id}`)}
                              className="gap-1"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                              Abrir
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Mobile Card View */}
                <div className="md:hidden space-y-3">
                  {processes.map((process) => (
                    <div
                      key={process.id}
                      className="border rounded-lg p-4 space-y-3 bg-card"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-medium text-sm">
                          Nº {process.process_number || process.id?.substring(0, 8) || "-"}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/process/${process.id}`)}
                          className="gap-1 h-8"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Abrir
                        </Button>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline" className="text-xs">
                          {formatProcessType(process.process_type)}
                        </Badge>
                        {process.status_label || process.status ? (
                          <Badge
                            className="text-xs"
                            style={getStatusBadgeClasses(process.status_color)}
                          >
                            {process.status_label || process.status}
                          </Badge>
                        ) : null}
                        {(process.prioridade || process.priority) && (
                          <Badge
                            variant="outline"
                            className={`text-xs ${getPriorityBadge(process.prioridade || process.priority)}`}
                          >
                            {process.prioridade || process.priority}
                          </Badge>
                        )}
                      </div>

                      <p className="text-xs text-muted-foreground">
                        Criado em {formatDate(process.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
