/**
 * AuditTrailPage — Página de registo de auditoria do sistema.
 *
 * PORQUÊ: Por exigência RGPD, todas as acções relevantes são registadas. Esta página permite ao
 * administrador consultar o histórico completo de acções (quem fez o quê, quando), essencial
 * para investigação de incidentes e conformidade regulatória.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Shield,
  Download,
  Trash2,
  Search,
  RefreshCw,
  TrendingUp,
  Bot,
  AlertTriangle,
  Activity,
  ChevronLeft,
  ChevronRight,
  FileText,
} from "lucide-react";
import { exportAuditTrail, cleanupAuditTrail } from "../services/api";
import { toast } from "../hooks/use-toast";
import { formatDateTime } from "../lib/utils";
import { useAuditTrailQuery, buildAuditTrailFilterParams } from "../hooks/queries/useAuditTrailQuery";
import { useAuditStatsQuery } from "../hooks/queries/useAuditStatsQuery";

// Mapeamento de cores para badges de origem
const sourceConfig = {
  web: { label: "Web", className: "bg-purple-100 text-purple-800 border-purple-200" },
  api: { label: "API", className: "bg-blue-100 text-blue-800 border-blue-200" },
  ai_automation: { label: "IA Autom.", className: "bg-orange-100 text-orange-800 border-orange-200" },
  email: { label: "Email", className: "bg-green-100 text-green-800 border-green-200" },
};

// (formatDateTime is now imported from lib/utils)

// Truncar texto longo
function truncate(str, maxLen = 60) {
  if (!str) return "-";
  if (str.length <= maxLen) return str;
  return str.substring(0, maxLen) + "...";
}

const AuditTrailPage = ({ embedded = false }) => {
  const wrapLayout = (children) => embedded ? children : <DashboardLayout title="Auditoria">{children}</DashboardLayout>;
  const [exporting, setExporting] = useState(false);
  const [page, setPage] = useState(1);

  // Filtros
  const [filterProcessId, setFilterProcessId] = useState("");
  const [filterSource, setFilterSource] = useState("all");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [filterAction, setFilterAction] = useState("");

  // ── Dados de servidor via TanStack Query (hooks dedicados) ────
  const {
    events,
    totalPages,
    total,
    isLoading: loading,
    isError: trailError,
    refetch: fetchAuditTrail,
  } = useAuditTrailQuery({
    page,
    filterProcessId,
    filterSource,
    filterDateFrom,
    filterDateTo,
    filterAction,
  });

  const { stats, refetch: fetchStats } = useAuditStatsQuery();

  useEffect(() => {
    if (trailError) {
      toast({
        variant: "destructive",
        title: "Erro",
        description: "Não foi possível carregar os registos de auditoria.",
      });
    }
  }, [trailError]);

  // Reset para página 1 ao mudar filtros
  useEffect(() => {
    setPage(1);
  }, [filterProcessId, filterSource, filterDateFrom, filterDateTo, filterAction]);

  // Exportar CSV — reutiliza os mesmos filtros da listagem (sem paginação)
  const handleExport = async () => {
    setExporting(true);
    try {
      const params = buildAuditTrailFilterParams({
        filterProcessId,
        filterSource,
        filterDateFrom,
        filterDateTo,
        filterAction,
      });

      const response = await exportAuditTrail(params);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `audit_trail_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast({ title: "Exportação concluída", description: "Ficheiro CSV descarregado com sucesso." });
    } catch (error) {
      console.error("Erro ao exportar:", error);
      toast({
        variant: "destructive",
        title: "Erro",
        description: "Não foi possível exportar os registos.",
      });
    } finally {
      setExporting(false);
    }
  };

  // Limpar registos antigos
  const handleCleanup = async () => {
    if (!window.confirm("Tem a certeza que pretende eliminar registos antigos? Esta acção é irreversível.")) return;
    try {
      const response = await cleanupAuditTrail();
      const deleted = response.data.deleted_count;
      toast({
        title: "Limpeza concluída",
        description: `${deleted} registos antigos foram eliminados.`,
      });
      fetchAuditTrail();
      fetchStats();
    } catch (error) {
      console.error("Erro na limpeza:", error);
      toast({
        variant: "destructive",
        title: "Erro",
        description: "Não foi possível efectuar a limpeza.",
      });
    }
  };

  // Limpar filtros
  const handleClearFilters = () => {
    setFilterProcessId("");
    setFilterSource("all");
    setFilterDateFrom("");
    setFilterDateTo("");
    setFilterAction("");
  };

  return wrapLayout(
    <div className="space-y-6">
      {/* Cabeçalho */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-6 w-6 text-purple-600" />
            Auditoria
          </h1>
          <p className="text-muted-foreground mt-1">
            Registo detalhado de todas as alterações ao sistema
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
            <Download className="h-4 w-4 mr-1" />
            {exporting ? "A exportar..." : "Exportar CSV"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              fetchAuditTrail();
              fetchStats();
            }}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            Actualizar
          </Button>
          <Button variant="destructive" size="sm" onClick={handleCleanup}>
            <Trash2 className="h-4 w-4 mr-1" />
            Limpar antigos
          </Button>
        </div>
      </div>

      {/* Cartões de estatísticas */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <Activity className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Alterações Hoje</p>
                  <p className="text-2xl font-bold">{stats.total_today}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-teal-100 rounded-lg">
                  <TrendingUp className="h-5 w-5 text-teal-600" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Esta Semana</p>
                  <p className="text-2xl font-bold">{stats.total_week}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-100 rounded-lg">
                  <Bot className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Aprovações IA</p>
                  <p className="text-2xl font-bold">{stats.ai_approvals_week}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-100 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-red-600" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Alterações Críticas</p>
                  <p className="text-2xl font-bold">{stats.critical_changes_week}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filtros */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Search className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Filtros</span>
            {(filterProcessId || filterSource !== "all" || filterDateFrom || filterDateTo || filterAction) && (
              <Button variant="ghost" size="sm" onClick={handleClearFilters} className="text-xs ml-auto">
                Limpar filtros
              </Button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <Input
              placeholder="ID do Processo..."
              value={filterProcessId}
              onChange={(e) => setFilterProcessId(e.target.value)}
            />
            <Select value={filterSource} onValueChange={setFilterSource}>
              <SelectTrigger>
                <SelectValue placeholder="Origem" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas as origens</SelectItem>
                <SelectItem value="web">Web</SelectItem>
                <SelectItem value="api">API</SelectItem>
                <SelectItem value="ai_automation">IA Automática</SelectItem>
                <SelectItem value="email">Email</SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="date"
              placeholder="Data inicial"
              value={filterDateFrom}
              onChange={(e) => setFilterDateFrom(e.target.value)}
            />
            <Input
              type="date"
              placeholder="Data final"
              value={filterDateTo}
              onChange={(e) => setFilterDateTo(e.target.value)}
            />
            <Input
              placeholder="Tipo de acção..."
              value={filterAction}
              onChange={(e) => setFilterAction(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Tabela de eventos */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Registros de Auditoria
            {!loading && (
              <span className="text-sm font-normal text-muted-foreground">
                ({total} no total)
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="whitespace-nowrap">Data/Hora</TableHead>
                  <TableHead className="whitespace-nowrap">Utilizador</TableHead>
                  <TableHead className="whitespace-nowrap">Acção</TableHead>
                  <TableHead className="whitespace-nowrap">Campo</TableHead>
                  <TableHead className="whitespace-nowrap">Valor Anterior</TableHead>
                  <TableHead className="whitespace-nowrap">Novo Valor</TableHead>
                  <TableHead className="whitespace-nowrap">Origem</TableHead>
                  <TableHead className="whitespace-nowrap">IP</TableHead>
                  <TableHead className="whitespace-nowrap">Justificação</TableHead>
                  <TableHead className="whitespace-nowrap">IA</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={10} className="text-center py-8 text-muted-foreground">
                      <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2" />
                      A carregar registos...
                    </TableCell>
                  </TableRow>
                ) : events.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={10} className="text-center py-8 text-muted-foreground">
                      Nenhum registo encontrado.
                    </TableCell>
                  </TableRow>
                ) : (
                  events.map((event) => {
                    const srcCfg = sourceConfig[event.source] || {
                      label: event.source || "-",
                      className: "bg-gray-100 text-gray-800 border-gray-200",
                    };
                    return (
                      <TableRow key={event.id}>
                        <TableCell className="whitespace-nowrap text-xs">
                          {formatDateTime(event.created_at)}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          <div className="flex flex-col">
                            <span className="font-medium text-sm">{event.user_name || "-"}</span>
                            {event.user_role && (
                              <span className="text-xs text-muted-foreground">{event.user_role}</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="max-w-[200px]">
                          <span className="text-sm">{truncate(event.action, 40)}</span>
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                            {event.field || "-"}
                          </code>
                        </TableCell>
                        <TableCell className="max-w-[120px]">
                          <span className="text-xs text-red-600" title={event.old_value || ""}>
                            {truncate(event.old_value, 30)}
                          </span>
                        </TableCell>
                        <TableCell className="max-w-[120px]">
                          <span className="text-xs text-green-700" title={event.new_value || ""}>
                            {truncate(event.new_value, 30)}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={srcCfg.className}>
                            {srcCfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs font-mono text-muted-foreground">
                          {event.ip_address || "-"}
                        </TableCell>
                        <TableCell className="max-w-[150px]">
                          <span className="text-xs" title={event.audit_reason || ""}>
                            {truncate(event.audit_reason, 25)}
                          </span>
                        </TableCell>
                        <TableCell>
                          {event.ai_suggested ? (
                            <div className="flex flex-col gap-0.5">
                              <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-200 text-xs w-fit">
                                <Bot className="h-3 w-3 mr-0.5" />
                                IA
                              </Badge>
                              {event.ai_approved_by && (
                                <span className="text-xs text-muted-foreground">
                                  ✓ Aprovado
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>

          {/* Paginação */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <p className="text-sm text-muted-foreground">
                Página {page} de {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  Seguinte
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AuditTrailPage;

