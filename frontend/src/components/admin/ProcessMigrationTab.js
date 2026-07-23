/**
 * ProcessMigrationTab — Painel de Migração Fase 1: Separação Cliente ↔ Processo
 *
 * Permite ao administrador:
 * - Ver o estado actual da migração
 * - Executar simulação (dry-run)
 * - Executar migração real
 * - Reverter migração (rollback)
 *
 * Acesso: Apenas Admin (no separador "Técnico" do SystemAdminPanel)
 */
import { useState, useEffect, useCallback } from "react";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Progress } from "../ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Eye,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  XCircle,
  ArrowRight,
  Users,
  FileText,
  ShieldCheck,
} from "lucide-react";
import {
  getProcessMigrationStatus,
  dryRunProcessMigration,
  runProcessMigration,
  rollbackProcessMigration,
} from "../../services/api";
import { toast } from "../../hooks/use-toast";

const ProcessMigrationTab = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // 'dry-run' | 'run' | 'rollback'
  const [confirmDialog, setConfirmDialog] = useState(null); // { type, title, description }
  const [confirmText, setConfirmText] = useState("");

  // ── Carregar estado ───────────────────────────────────────────────────
  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await getProcessMigrationStatus();
      setStatus(data);
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Erro ao carregar estado",
        description: extractErrorMessage(err.response?.data?.detail, "Não foi possível obter o estado da migração."),
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // Auto-refresh enquanto migração está em execução
  useEffect(() => {
    if (status?.current_state?.status === "running") {
      const interval = setInterval(loadStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [status?.current_state?.status, loadStatus]);

  // ── Ações ─────────────────────────────────────────────────────────────
  const handleDryRun = async () => {
    setActionLoading("dry-run");
    setConfirmDialog(null);
    setConfirmText("");
    try {
      await dryRunProcessMigration();
      toast({
        title: "Simulação iniciada",
        description: "A simulação (dry-run) está a correr em background. Verifique o estado dentro de alguns segundos.",
      });
      setTimeout(loadStatus, 2000);
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Erro ao iniciar simulação",
        description: extractErrorMessage(err.response?.data?.detail, "Não foi possível iniciar a simulação."),
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleRunMigration = async () => {
    setActionLoading("run");
    setConfirmDialog(null);
    setConfirmText("");
    try {
      await runProcessMigration();
      toast({
        title: "Migração iniciada",
        description: "A migração Fase 1 está a correr em background. Um backup foi criado automaticamente.",
      });
      setTimeout(loadStatus, 2000);
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Erro ao iniciar migração",
        description: extractErrorMessage(err.response?.data?.detail, "Não foi possível iniciar a migração."),
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleRollback = async () => {
    setActionLoading("rollback");
    setConfirmDialog(null);
    setConfirmText("");
    try {
      const { data } = await rollbackProcessMigration();
      toast({
        title: "Rollback executado",
        description: data.message || "As colecções foram restauradas para o estado anterior.",
      });
      loadStatus();
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Erro ao reverter",
        description: extractErrorMessage(err.response?.data?.detail, "Não foi possível reverter a migração."),
      });
    } finally {
      setActionLoading(null);
    }
  };

  // ── Helpers ───────────────────────────────────────────────────────────
  const getStatusBadge = () => {
    const state = status?.current_state;
    if (!state) return null;

    const variants = {
      idle: { variant: "secondary", icon: Database, label: "Inativa" },
      running: { variant: "default", icon: Loader2, label: "Em execução" },
      completed: { variant: "default", icon: CheckCircle2, label: "Concluída" },
      failed: { variant: "destructive", icon: XCircle, label: "Falhou" },
      rolled_back: { variant: "outline", icon: RotateCcw, label: "Revertida" },
    };

    const config = variants[state.status] || variants.idle;
    const Icon = config.icon;

    return (
      <Badge variant={config.variant} className="gap-1.5">
        <Icon className={`h-3.5 w-3.5 ${state.status === "running" ? "animate-spin" : ""}`} />
        {config.label}
        {state.mode && state.status !== "idle" && (
          <span className="text-xs opacity-70">({state.mode})</span>
        )}
      </Badge>
    );
  };

  const isRunning = status?.current_state?.status === "running";

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Database className="h-5 w-5" />
            Migração Fase 1: Separação Cliente ↔ Processo
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Separa a entidade Cliente (dados pessoais/fiscais) da entidade Processo (dossier/negócio)
          </p>
        </div>
        <div className="flex items-center gap-2">
          {getStatusBadge()}
          <Button variant="outline" size="sm" onClick={loadStatus} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            Atualizar
          </Button>
        </div>
      </div>

      {/* Diagrama explicativo */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row items-center justify-center gap-4 text-sm">
            <div className="flex items-center gap-2 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-4 py-3 border border-amber-200 dark:border-amber-800">
              <Users className="h-5 w-5 text-amber-600" />
              <div>
                <p className="font-semibold text-amber-700 dark:text-amber-400">Cliente</p>
                <p className="text-xs text-amber-600/70 dark:text-amber-400/70">Nome, NIF, Email, Telefone, Morada...</p>
              </div>
            </div>
            <div className="flex flex-col items-center gap-1">
              <ArrowRight className="h-5 w-5 text-muted-foreground hidden md:block" />
              <span className="text-xs text-muted-foreground md:hidden">→</span>
              <span className="text-xs text-muted-foreground">1:N</span>
            </div>
            <div className="flex items-center gap-2 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg px-4 py-3 border border-emerald-200 dark:border-emerald-800">
              <FileText className="h-5 w-5 text-emerald-600" />
              <div>
                <p className="font-semibold text-emerald-700 dark:text-emerald-400">Processo</p>
                <p className="text-xs text-emerald-600/70 dark:text-emerald-400/70">Tipo, Status, Valor, Banco, Financiamento...</p>
              </div>
            </div>
          </div>
          <p className="text-center text-xs text-muted-foreground mt-3">
            Um cliente pode ter múltiplos processos. Cada processo tem obrigatoriamente um <code className="bg-muted px-1 rounded">client_id</code>.
          </p>
        </CardContent>
      </Card>

      {/* Estatísticas */}
      {status && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Clientes</p>
                  <p className="text-2xl font-bold">{status.overview?.total_clients ?? 0}</p>
                </div>
                <Users className="h-8 w-8 text-amber-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Processos</p>
                  <p className="text-2xl font-bold">{status.overview?.total_processes ?? 0}</p>
                </div>
                <FileText className="h-8 w-8 text-emerald-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Com client_id</p>
                  <p className="text-2xl font-bold text-green-600">
                    {status.process_migration?.with_client_id?.count ?? 0}
                  </p>
                </div>
                <CheckCircle2 className="h-8 w-8 text-green-500 opacity-50" />
              </div>
              <Progress
                value={status.process_migration?.with_client_id?.percentage ?? 0}
                className="mt-2 h-1.5"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {status.process_migration?.with_client_id?.percentage ?? 0}% dos processos
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Sem client_id</p>
                  <p className="text-2xl font-bold text-red-600">
                    {status.process_migration?.without_client_id?.count ?? 0}
                  </p>
                </div>
                <AlertTriangle className="h-8 w-8 text-red-500 opacity-50" />
              </div>
              {status.process_migration?.without_client_id?.count > 0 && (
                <p className="text-xs text-red-600 mt-1 font-medium">Precisam de migração</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Estado detalhado */}
      {status && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Migração de processos */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Estado dos Processos</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Já migrados (phase1)</span>
                <Badge variant="outline">{status.process_migration?.already_migrated ?? 0}</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Com property_value</span>
                <Badge variant="outline">{status.process_migration?.with_property_value ?? 0}</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Com loan_value</span>
                <Badge variant="outline">{status.process_migration?.with_loan_value ?? 0}</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Com bank_assigned</span>
                <Badge variant="outline">{status.process_migration?.with_bank_assigned ?? 0}</Badge>
              </div>
            </CardContent>
          </Card>

          {/* Backups */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldCheck className="h-4 w-4" />
                Backups & Segurança
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm items-center">
                <span className="text-muted-foreground">Backup de clients</span>
                {status.backups?.clients_legacy_exists ? (
                  <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                    <CheckCircle2 className="h-3 w-3 mr-1" /> Existe ({status.backups.clients_backup_count} docs)
                  </Badge>
                ) : (
                  <Badge variant="destructive">Não existe</Badge>
                )}
              </div>
              <div className="flex justify-between text-sm items-center">
                <span className="text-muted-foreground">Backup de processes</span>
                {status.backups?.processes_legacy_exists ? (
                  <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                    <CheckCircle2 className="h-3 w-3 mr-1" /> Existe ({status.backups.processes_backup_count} docs)
                  </Badge>
                ) : (
                  <Badge variant="destructive">Não existe</Badge>
                )}
              </div>
              <div className="flex justify-between text-sm items-center">
                <span className="text-muted-foreground">Clientes c/ dados financeiros</span>
                <Badge variant={status.client_cleanup?.with_financial_data > 0 ? "destructive" : "outline"}>
                  {status.client_cleanup?.with_financial_data ?? 0}
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Relatório da última execução */}
      {status?.current_state?.last_report && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Relatório da Última Execução</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {[
                { label: "Clientes processados", value: status.current_state.last_report.clients_deduplicated },
                { label: "Clientes criados", value: status.current_state.last_report.clients_created },
                { label: "Processos migrados", value: status.current_state.last_report.processes_migrated },
                { label: "Documentos ref.", value: status.current_state.last_report.documents_referenced },
                { label: "Erros", value: status.current_state.last_report.errors?.length ?? 0 },
              ].map((item, i) => (
                <div key={i} className="text-center p-2 rounded-lg bg-muted/50">
                  <p className="text-lg font-bold">{item.value ?? 0}</p>
                  <p className="text-xs text-muted-foreground">{item.label}</p>
                </div>
              ))}
            </div>
            {status.current_state.last_report.errors?.length > 0 && (
              <div className="mt-3 p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800">
                <p className="text-sm font-medium text-red-700 dark:text-red-400">Erros encontrados:</p>
                <ul className="mt-1 space-y-1">
                  {status.current_state.last_report.errors.map((err, i) => (
                    <li key={i} className="text-xs text-red-600 dark:text-red-400">{err}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Botões de ação */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Ações de Migração</CardTitle>
          <CardDescription>
            Recomendamos executar primeiro a simulação (dry-run) para verificar o que será alterado.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {/* Dry-run */}
            <Button
              variant="outline"
              onClick={() =>
                setConfirmDialog({
                  type: "dry-run",
                  title: "Executar Simulação (Dry-Run)",
                  description:
                    "A simulação analisa os dados SEM modificar a base de dados. " +
                    "Permite verificar quantos clientes seriam criados/deduplicados e quantos processos migrados. " +
                    "Deseja continuar?",
                  confirmLabel: "Executar Simulação",
                  confirmVariant: "default",
                })
              }
              disabled={isRunning || actionLoading !== null}
            >
              {actionLoading === "dry-run" ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Eye className="h-4 w-4 mr-2" />
              )}
              Simulação (Dry-Run)
            </Button>

            {/* Executar migração */}
            <Button
              variant="default"
              onClick={() =>
                setConfirmDialog({
                  type: "run",
                  title: "⚠️ Executar Migração Fase 1",
                  description:
                    "ATENÇÃO: Esta ação MODIFICA a base de dados. Um backup automático será criado antes. " +
                    "A migração pode demorar alguns minutos dependendo do volume de dados. " +
                    "Para confirmar, escreva MIGRAR abaixo:",
                  confirmLabel: "Executar Migração",
                  confirmVariant: "default",
                  requiresText: "MIGRAR",
                })
              }
              disabled={isRunning || actionLoading !== null}
            >
              {actionLoading === "run" ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Executar Migração
            </Button>

            {/* Rollback */}
            <Button
              variant="destructive"
              onClick={() =>
                setConfirmDialog({
                  type: "rollback",
                  title: "⚠️ Reverter Migração (Rollback)",
                  description:
                    "ATENÇÃO: Esta ação restaura as colecções clients e processes para o estado anterior à migração. " +
                    "Qualquer alteração feita após a migração será perdida. " +
                    "Para confirmar, escreva REVERTER abaixo:",
                  confirmLabel: "Reverter Migração",
                  confirmVariant: "destructive",
                  requiresText: "REVERTER",
                })
              }
              disabled={isRunning || actionLoading !== null || !status?.backups?.clients_legacy_exists}
            >
              {actionLoading === "rollback" ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <RotateCcw className="h-4 w-4 mr-2" />
              )}
              Reverter (Rollback)
            </Button>
          </div>

          {!status?.backups?.clients_legacy_exists && (
            <p className="text-xs text-muted-foreground mt-2">
              <AlertTriangle className="h-3 w-3 inline mr-1" />
              O rollback requer um backup prévio. Execute a migração primeiro (cria backup automaticamente).
            </p>
          )}
        </CardContent>
      </Card>

      {/* Dialog de confirmação */}
      <Dialog
        open={confirmDialog !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmDialog(null);
            setConfirmText("");
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {(confirmDialog?.type === "run" || confirmDialog?.type === "rollback") && (
                <AlertTriangle className="h-5 w-5 text-red-500" />
              )}
              {confirmDialog?.title}
            </DialogTitle>
            <DialogDescription>{confirmDialog?.description}</DialogDescription>
          </DialogHeader>

          {confirmDialog?.requiresText && (
            <div className="py-2">
              <Input
                placeholder={`Escreva ${confirmDialog.requiresText} para confirmar`}
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
              />
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setConfirmDialog(null);
                setConfirmText("");
              }}
              disabled={actionLoading !== null}
            >
              Cancelar
            </Button>
            <Button
              variant={confirmDialog?.confirmVariant || "default"}
              disabled={
                actionLoading !== null ||
                (confirmDialog?.requiresText && confirmText !== confirmDialog.requiresText)
              }
              onClick={() => {
                if (confirmDialog?.type === "dry-run") handleDryRun();
                else if (confirmDialog?.type === "run") handleRunMigration();
                else if (confirmDialog?.type === "rollback") handleRollback();
              }}
            >
              {actionLoading !== null ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              {confirmDialog?.confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProcessMigrationTab;
