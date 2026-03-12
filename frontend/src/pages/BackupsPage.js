/**
 * BackupsPage - Gestão de Backups
 * Interface para administradores criarem e restaurarem backups
 */
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Database,
  Download,
  Upload,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  HardDrive,
  Cloud,
  Shield,
  AlertTriangle,
  Loader2,
  FileArchive,
  Calendar,
  User,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const BackupsPage = () => {
  const [statistics, setStatistics] = useState(null);
  const [history, setHistory] = useState([]);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [backupInProgress, setBackupInProgress] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const headers = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      };

      const [statsRes, historyRes, configRes] = await Promise.all([
        fetch(`${API_URL}/api/backup/statistics`, { headers }),
        fetch(`${API_URL}/api/backup/history?limit=20`, { headers }),
        fetch(`${API_URL}/api/backup/config`, { headers }),
      ]);

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStatistics(statsData.data);
      }

      if (historyRes.ok) {
        const historyData = await historyRes.json();
        setHistory(historyData.history || []);
      }

      if (configRes.ok) {
        const configData = await configRes.json();
        setConfig(configData.config);
      }
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast.error("Erro ao carregar dados de backup");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const triggerBackup = async () => {
    setBackupInProgress(true);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/backup/trigger`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          upload_to_cloud: true,
          cleanup_after: true,
        }),
      });

      if (response.ok) {
        toast.success("Backup iniciado em background");
        // Actualizar dados após 5 segundos
        setTimeout(() => {
          fetchData();
          setBackupInProgress(false);
        }, 5000);
      } else {
        throw new Error("Erro ao iniciar backup");
      }
    } catch (error) {
      toast.error("Erro ao iniciar backup");
      setBackupInProgress(false);
    }
  };

  const verifyBackups = async () => {
    setVerifying(true);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/backup/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setVerificationResult(data);
        if (data.success) {
          toast.success("Verificação concluída - Tudo OK!");
        } else {
          toast.warning("Verificação concluída - Existem problemas");
        }
      }
    } catch (error) {
      toast.error("Erro ao verificar backups");
    } finally {
      setVerifying(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/D";
    try {
      return new Date(dateStr).toLocaleString("pt-PT");
    } catch {
      return dateStr;
    }
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Gestao de Backups</h1>
            <p className="text-muted-foreground">
              Criar, restaurar e verificar backups da base de dados
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={verifyBackups}
              disabled={verifying}
            >
              {verifying ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Shield className="h-4 w-4 mr-2" />
              )}
              Verificar Integridade
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button disabled={backupInProgress}>
                  {backupInProgress ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Database className="h-4 w-4 mr-2" />
                  )}
                  Criar Backup
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Criar Novo Backup?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Isto vai criar um backup completo da base de dados.
                    O processo corre em background e pode demorar alguns minutos.
                    O backup sera automaticamente enviado para a cloud.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={triggerBackup}>
                    Criar Backup
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>

        {/* Estatisticas */}
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total de Backups</CardTitle>
              <FileArchive className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{statistics?.total_backups || 0}</div>
              <p className="text-xs text-muted-foreground">
                {statistics?.successful_backups || 0} bem sucedidos
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Taxa de Sucesso</CardTitle>
              <CheckCircle className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {statistics?.success_rate ? `${statistics.success_rate.toFixed(1)}%` : "N/D"}
              </div>
              <p className="text-xs text-muted-foreground">
                Ultimos 30 dias
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Tamanho Total</CardTitle>
              <HardDrive className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {formatBytes(statistics?.total_size_bytes || 0)}
              </div>
              <p className="text-xs text-muted-foreground">
                Armazenamento local
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Ultimo Backup</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-lg font-bold">
                {statistics?.last_backup?.started_at
                  ? formatDate(statistics.last_backup.started_at)
                  : "Nunca"}
              </div>
              <p className="text-xs text-muted-foreground">
                {statistics?.last_backup?.success ? (
                  <span className="text-green-500">Sucesso</span>
                ) : statistics?.last_backup ? (
                  <span className="text-red-500">Falhou</span>
                ) : null}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Resultado da Verificacao */}
        {verificationResult && (
          <Card className={verificationResult.success ? "border-green-500" : "border-yellow-500"}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {verificationResult.success ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                )}
                Resultado da Verificacao
              </CardTitle>
              <CardDescription>
                Verificado em: {formatDate(verificationResult.verified_at)}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {verificationResult.issues?.length > 0 && (
                <div className="mb-4">
                  <h4 className="font-medium mb-2 text-yellow-600">Problemas Encontrados:</h4>
                  <ul className="list-disc list-inside space-y-1">
                    {verificationResult.issues.map((issue, idx) => (
                      <li key={idx} className="text-sm text-muted-foreground">{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
              {verificationResult.verified_files?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2">Ficheiros Verificados:</h4>
                  <div className="grid gap-2">
                    {verificationResult.verified_files.map((file, idx) => (
                      <div key={idx} className="flex items-center justify-between text-sm p-2 bg-muted rounded">
                        <span>{file.filename}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">{file.size_mb} MB</span>
                          {file.valid ? (
                            <CheckCircle className="h-4 w-4 text-green-500" />
                          ) : (
                            <XCircle className="h-4 w-4 text-red-500" />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Configuracao */}
        {config && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cloud className="h-5 w-5" />
                Configuracao
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <div>
                  <p className="text-sm font-medium">Directorio Local</p>
                  <p className="text-sm text-muted-foreground truncate">{config.backup_dir}</p>
                </div>
                <div>
                  <p className="text-sm font-medium">Pasta Drive</p>
                  <p className="text-sm text-muted-foreground">{config.onedrive_folder || "N/D"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium">Retencao Local</p>
                  <p className="text-sm text-muted-foreground">{config.local_retention_days} dias</p>
                </div>
                <div>
                  <p className="text-sm font-medium">Tamanho Max.</p>
                  <p className="text-sm text-muted-foreground">{config.max_backup_size_mb} MB</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Historico */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Historico de Backups</CardTitle>
              <CardDescription>Ultimos 20 backups</CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={fetchData}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[400px]">
              {history.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  Nenhum backup registado
                </p>
              ) : (
                <div className="space-y-3">
                  {history.map((backup, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-3 border rounded-lg"
                    >
                      <div className="flex items-center gap-3">
                        {backup.status === "completed" ? (
                          <CheckCircle className="h-5 w-5 text-green-500" />
                        ) : backup.status === "failed" ? (
                          <XCircle className="h-5 w-5 text-red-500" />
                        ) : (
                          <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
                        )}
                        <div>
                          <div className="flex items-center gap-2">
                            <Calendar className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">
                              {formatDate(backup.started_at)}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <User className="h-3 w-3" />
                            <span>
                              {backup.triggered_by_email || "Sistema"}
                            </span>
                            <Badge variant="outline" className="text-xs">
                              {backup.trigger_type === "manual" ? "Manual" : "Automatico"}
                            </Badge>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <Badge
                          variant={
                            backup.status === "completed"
                              ? "success"
                              : backup.status === "failed"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {backup.status === "completed"
                            ? "Concluido"
                            : backup.status === "failed"
                            ? "Falhou"
                            : "Em Progresso"}
                        </Badge>
                        {backup.result?.size_bytes && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {formatBytes(backup.result.size_bytes)}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default BackupsPage;
