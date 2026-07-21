/**
 * MaintenanceSection — ferramentas de manutenção do SystemConfig.
 *
 * Extraído de SystemConfigPage.js (tab "maintenance"): índices DB,
 * limpeza jobs/logs, migração de números, mapeamento S3 e sync Prod→Dev.
 */
import React, { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../../components/ui/dialog";
import { hasRole } from "../../utils/roleUtils";
import { safeString } from "../../utils/safeString";
import { toast } from "sonner";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  Wrench,
  Database,
  Loader2,
  RefreshCw,
  CheckCircle,
  Eye,
  Trash2,
  AlertTriangle,
  FolderOpen,
  Sparkles,
  UserCheck,
  Users,
  Link,
  Save,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function MaintenanceSection({ token, user }) {
  const [repairingIndexes, setRepairingIndexes] = useState(false);
  const [cleaningJobs, setCleaningJobs] = useState(false);
  const [cleaningLogs, setCleaningLogs] = useState(false);
  const [indexStats, setIndexStats] = useState(null);

  const repairIndexes = async () => {
    setRepairingIndexes(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/db/indexes/repair`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.success) {
        const dropped = data.cleanup?.dropped?.length || 0;
        toast.success(`Índices reparados! ${dropped > 0 ? `${dropped} índices antigos removidos.` : "Todos os índices OK."}`);
        // Actualizar stats
        fetchIndexStats();
      } else {
        toast.error("Erro ao reparar índices");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setRepairingIndexes(false);
    }
  };

  const fetchIndexStats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/db/indexes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.success) {
        setIndexStats(data.indexes);
      }
    } catch (error) {
      console.error("Erro ao carregar stats:", error);
    }
  };

  const cleanOldJobs = async () => {
    setCleaningJobs(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/cleanup/jobs?days=7`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.success) {
        toast.success(`${data.deleted_count || 0} jobs antigos removidos`);
      }
    } catch (error) {
      toast.error("Erro ao limpar jobs");
    } finally {
      setCleaningJobs(false);
    }
  };

  const cleanOldLogs = async () => {
    setCleaningLogs(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/cleanup/error-logs?days=30`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.success) {
        toast.success(`${data.deleted_count || 0} logs antigos removidos`);
      }
    } catch (error) {
      toast.error("Erro ao limpar logs");
    } finally {
      setCleaningLogs(false);
    }
  };

  const [migratingProcessNumbers, setMigratingProcessNumbers] = useState(false);
  
  // Estado para mapeamento S3 (Clientes/Processos)
  const [s3MappingData, setS3MappingData] = useState(null);
  const [loadingS3Mapping, setLoadingS3Mapping] = useState(false);
  const [savingS3Mapping, setSavingS3Mapping] = useState(false);
  const [selectedMappings, setSelectedMappings] = useState({});
  const [s3SearchTerm, setS3SearchTerm] = useState("");
  const [showUnmappedOnly, setShowUnmappedOnly] = useState(false);
  const [autoMapping, setAutoMapping] = useState(false);
  const [fixingNames, setFixingNames] = useState(false);
  
  // Estado para Sincronização Prod → Dev
  const [syncing, setSyncing] = useState(false);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [showSyncConfirmModal, setShowSyncConfirmModal] = useState(false);
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncPolling, setSyncPolling] = useState(false);
  
  // Filtrar clientes para exibição
  const filteredS3Clients = s3MappingData?.processes?.filter(p => {
    const matchesSearch = !s3SearchTerm || 
      p.client_name?.toLowerCase().includes(s3SearchTerm.toLowerCase());
    const matchesUnmapped = !showUnmappedOnly || !p.s3_folder;
    return matchesSearch && matchesUnmapped;
  }) || [];
  
  const migrateProcessNumbers = async () => {
    setMigratingProcessNumbers(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/migrate-process-numbers`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.updated > 0) {
        toast.success(`${data.updated} processos actualizados com números sequenciais (${data.first_number} a ${data.last_number})`);
      } else {
        toast.info(data.message || "Todos os processos já têm número atribuído");
      }
    } catch (error) {
      toast.error("Erro ao migrar números de processo");
    } finally {
      setMigratingProcessNumbers(false);
    }
  };

  // Carregar dados de mapeamento S3 (Clientes/Processos)
  const loadS3MappingData = async () => {
    setLoadingS3Mapping(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/client-s3-mappings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setS3MappingData(data);
      // Limpar selecções anteriores
      setSelectedMappings({});
    } catch (error) {
      toast.error("Erro ao carregar mapeamentos S3");
    } finally {
      setLoadingS3Mapping(false);
    }
  };

  // Guardar um mapeamento individual de cliente
  const saveClientS3Mapping = async (processId, s3Folder) => {
    setSavingS3Mapping(true);
    try {
      const url = s3Folder 
        ? `${API_URL}/api/admin/client-s3-mappings?process_id=${processId}&s3_folder=${encodeURIComponent(s3Folder)}`
        : `${API_URL}/api/admin/client-s3-mappings?process_id=${processId}`;
      
      const response = await fetch(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.success) {
        // Fallback para nome do cliente da lista local se não vier do backend
        const clientName = data.client_name || s3MappingData?.processes?.find(p => p.id === processId)?.client_name || "cliente";
        toast.success(`Mapeamento ${s3Folder ? "guardado" : "removido"} para ${clientName}`);
        // Actualizar lista local
        loadS3MappingData();
      } else {
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar mapeamento"));
      }
    } catch (error) {
      toast.error("Erro ao guardar mapeamento");
    } finally {
      setSavingS3Mapping(false);
    }
  };

  // Guardar todos os mapeamentos alterados de clientes
  const saveAllClientS3Mappings = async () => {
    // Filtrar apenas mapeamentos que foram realmente alterados
    const changedMappings = Object.entries(selectedMappings)
      .filter(([processId, s3Folder]) => {
        const currentProcess = s3MappingData?.processes?.find(p => p.id === processId);
        const currentMapping = currentProcess?.s3_folder || "";
        const newMapping = s3Folder || "";
        return currentMapping !== newMapping;
      })
      .map(([processId, s3Folder]) => ({
        process_id: processId,
        s3_folder: s3Folder || null
      }));
    
    if (changedMappings.length === 0) {
      toast.info("Nenhuma alteração para guardar");
      return;
    }
    
    setSavingS3Mapping(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/client-s3-mappings/bulk`, {
        method: "POST",
        headers: { 
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(changedMappings)
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error("Erro na resposta:", response.status, errorText);
        toast.error(`Erro ${response.status}: Falha ao guardar mapeamentos`);
        return;
      }
      
      const data = await response.json();
      if (data.success) {
        toast.success(`${data.updated} mapeamento(s) actualizado(s)`);
        setSelectedMappings({});
        loadS3MappingData();
      } else {
        toast.error(data.message || "Erro ao guardar mapeamentos");
      }
    } catch (error) {
      console.error("Erro ao guardar mapeamentos:", error);
      toast.error("Erro de rede ao guardar mapeamentos");
    } finally {
      setSavingS3Mapping(false);
    }
  };
  
  // Auto-mapear clientes para pastas S3
  const handleAutoMapClients = async () => {
    setAutoMapping(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/client-s3-mappings/auto-map`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      
      if (response.ok) {
        const total = (data.mapped || 0) + (data.skipped || 0);
        if (data.mapped > 0) {
          toast.success(`${data.mapped} processos mapeados automaticamente (${data.skipped} já mapeados ou sem correspondência)`);
        } else {
          toast.info(`Nenhum novo mapeamento encontrado (${data.skipped} processos já mapeados ou sem correspondência)`);
        }
        if (data.errors && data.errors.length > 0) {
          toast.warning(`Alguns erros: ${data.errors.join(", ")}`);
        }
        loadS3MappingData();
      } else {
        toast.error(extractErrorMessage(data.detail, "Erro no auto-mapeamento"));
      }
    } catch (error) {
      toast.error("Erro ao auto-mapear clientes");
    } finally {
      setAutoMapping(false);
    }
  };
  
  // Corrigir nomes de clientes em falta
  const handleFixMissingNames = async () => {
    setFixingNames(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/client-s3-mappings/fix-missing-names`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      
      if (response.ok) {
        if (data.fixed_count > 0) {
          toast.success(`${data.fixed_count} processos corrigidos com nomes extraídos das pastas S3 ou emails`);
        } else {
          toast.info("Todos os processos já têm nome definido");
        }
        loadS3MappingData();
      } else {
        toast.error(extractErrorMessage(data.detail, "Erro ao corrigir nomes"));
      }
    } catch (error) {
      toast.error("Erro ao corrigir nomes de clientes");
    } finally {
      setFixingNames(false);
    }
  };

  // Guardar todos os mapeamentos alterados (legado - manter para compatibilidade)
  const saveAllS3Mappings = async () => {
    setSavingS3Mapping(true);
    try {
      const mappings = Object.entries(selectedMappings).map(([userId, s3Folder]) => ({
        user_id: userId,
        s3_folder: s3Folder || null
      }));

      const response = await fetch(`${API_URL}/api/admin/user-s3-mappings/bulk`, {
        method: "POST",
        headers: { 
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(mappings)
      });
      const data = await response.json();
      if (data.success) {
        toast.success(`${data.updated} mapeamentos actualizados`);
        loadS3MappingData();
      } else {
        toast.error("Erro ao guardar mapeamentos");
      }
    } catch (error) {
      toast.error("Erro ao guardar mapeamentos");
    } finally {
      setSavingS3Mapping(false);
    }
  };

  // ─── Sincronização Prod → Dev ───
  const isDevEnvironment = process.env.REACT_APP_ENVIRONMENT === "development" || 
                           process.env.REACT_APP_ENVIRONMENT === "dev" || 
                           !process.env.REACT_APP_ENVIRONMENT;

  const fetchSyncStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/sync-database/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSyncStatus(data);
        return data;
      }
    } catch (error) {
      console.error("Erro ao obter status do sync:", error);
    }
    return null;
  };

  const handleStartSync = async () => {
    setSyncing(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/sync-database`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        toast.error(extractErrorMessage(data.detail, `Erro ${response.status}: Não foi possível iniciar a sincronização`));
        setSyncing(false);
        return;
      }

      const data = await response.json();
      if (data.success) {
        toast.success("Sincronização iniciada em background");
        setShowSyncConfirmModal(false);
        setSyncPolling(true);
      } else {
        toast.error(extractErrorMessage(data.detail, "Erro ao iniciar sincronização"));
      }
    } catch (error) {
      toast.error("Erro de conexão ao iniciar sincronização");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    if (!syncPolling) return;
    const interval = setInterval(async () => {
      const status = await fetchSyncStatus();
      if (status && !status.in_progress && status.last_result) {
        setSyncPolling(false);
        if (status.last_result.success) {
          toast.success(`Sincronização concluída! ${status.last_result.total_documents} documentos copiados.`);
        } else {
          toast.error(`Erros na sincronização: ${status.last_result.errors?.length || 1} erro(s)`);
        }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [syncPolling]);

  return (
    <>
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Wrench className="h-5 w-5 text-primary" />
          <div>
            <CardTitle className="text-lg">Manutenção do Sistema</CardTitle>
            <CardDescription>Ferramentas de diagnóstico e reparação</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Reparação de Índices */}
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium flex items-center gap-2">
                <Database className="h-4 w-4" />
                Índices da Base de Dados
              </h4>
              <p className="text-sm text-muted-foreground">
                Remove índices antigos/incorretos e recria os correctos. Use se houver erros de "duplicate key".
              </p>
            </div>
            <Button onClick={repairIndexes} disabled={repairingIndexes}>
              {repairingIndexes ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Reparar Índices
            </Button>
          </div>
          {indexStats && (
            <div className="bg-muted/50 rounded p-3 text-sm">
              <p className="font-medium mb-2">Estado actual:</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(indexStats).map(([coll, info]) => (
                  <div key={coll} className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3 text-green-500" />
                    <span>{coll}: {info.count || 0} índices</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={fetchIndexStats}>
            <Eye className="h-4 w-4 mr-2" />
            Ver Estado dos Índices
          </Button>
        </div>

        {/* Limpeza de Jobs Antigos */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium flex items-center gap-2">
                <Trash2 className="h-4 w-4" />
                Limpar Jobs Antigos
              </h4>
              <p className="text-sm text-muted-foreground">
                Remove jobs de importação concluídos há mais de 7 dias.
              </p>
            </div>
            <Button variant="outline" onClick={cleanOldJobs} disabled={cleaningJobs}>
              {cleaningJobs ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Limpar
            </Button>
          </div>
        </div>

        {/* Limpeza de Logs Antigos */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Limpar Logs de Erro Antigos
              </h4>
              <p className="text-sm text-muted-foreground">
                Remove logs de erro com mais de 30 dias.
              </p>
            </div>
            <Button variant="outline" onClick={cleanOldLogs} disabled={cleaningLogs}>
              {cleaningLogs ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Limpar
            </Button>
          </div>
        </div>

        {/* Migração de Números de Processo */}
        <div className="border rounded-lg p-4 border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/30">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium flex items-center gap-2">
                <Database className="h-4 w-4 text-blue-600" />
                Migrar Números de Processo
              </h4>
              <p className="text-sm text-muted-foreground">
                Atribui números sequenciais a processos antigos que não têm. Use após actualizações do sistema.
              </p>
            </div>
            <Button onClick={migrateProcessNumbers} disabled={migratingProcessNumbers}>
              {migratingProcessNumbers ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Migrar
            </Button>
          </div>
        </div>

        {/* Mapeamento Clientes/Processos-S3 */}
        <div className="border rounded-lg p-4 border-purple-200 dark:border-purple-800 bg-purple-50/50 dark:bg-purple-950/30">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="font-medium flex items-center gap-2">
                <FolderOpen className="h-4 w-4 text-purple-600" />
                Mapeamento Clientes/Processos → Pastas S3
              </h4>
              <p className="text-sm text-muted-foreground">
                Associe cada cliente/processo à sua pasta de documentos no S3. Clientes sem mapeamento usarão a pasta baseada no nome.
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={loadS3MappingData} disabled={loadingS3Mapping}>
                {loadingS3Mapping ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Carregar
              </Button>
            </div>
          </div>
          
          {s3MappingData && (
            <div className="space-y-4">
              {!s3MappingData.s3_configured && (
                <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 rounded p-3 text-sm flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-yellow-600" />
                  <span>S3 não configurado. Configure as credenciais AWS nas definições de Storage.</span>
                </div>
              )}
              
              {s3MappingData.s3_configured && (
                <>
                  {/* Estatísticas */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
                    <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                      <p className="text-2xl font-bold text-purple-600">{safeString(s3MappingData.stats?.total ?? 0)}</p>
                      <p className="text-xs text-muted-foreground">Total de Clientes</p>
                    </div>
                    <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                      <p className="text-2xl font-bold text-green-600">{safeString(s3MappingData.stats?.mapped ?? 0)}</p>
                      <p className="text-xs text-muted-foreground">Com Mapeamento</p>
                    </div>
                    <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                      <p className="text-2xl font-bold text-orange-600">{safeString(s3MappingData.stats?.unmapped ?? 0)}</p>
                      <p className="text-xs text-muted-foreground">Sem Mapeamento</p>
                    </div>
                  </div>
                  
                  {/* Filtros */}
                  <div className="flex flex-wrap gap-3 items-center">
                    <Input
                      placeholder="Pesquisar por nome..."
                      value={s3SearchTerm}
                      onChange={(e) => setS3SearchTerm(e.target.value)}
                      className="max-w-xs"
                    />
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={showUnmappedOnly}
                        onChange={(e) => setShowUnmappedOnly(e.target.checked)}
                        className="rounded"
                      />
                      Apenas sem mapeamento
                    </label>
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={handleAutoMapClients}
                      disabled={autoMapping}
                    >
                      {autoMapping ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Sparkles className="h-4 w-4 mr-2" />
                      )}
                      Auto-Mapear
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={handleFixMissingNames}
                      disabled={fixingNames}
                      className="text-orange-600 border-orange-300 hover:bg-orange-50"
                    >
                      {fixingNames ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <UserCheck className="h-4 w-4 mr-2" />
                      )}
                      Corrigir Nomes
                    </Button>
                  </div>
                  
                  {/* Lista de Clientes */}
                  <div className="max-h-80 overflow-y-auto space-y-2">
                    {filteredS3Clients?.map((p) => (
                      <div key={p.id} className="flex items-center gap-3 p-2 bg-white dark:bg-gray-900 rounded border">
                        <div className="flex items-center gap-2 min-w-0 sm:min-w-[250px]">
                          <Users className="h-4 w-4 text-muted-foreground" />
                          <div className="text-sm">
                            <span className="font-medium block">{p.client_name || "Sem nome"}</span>
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              {p.process_number ? `#${p.process_number}` : ""} 
                              {p.status && <Badge variant="outline" className="text-[10px]">{p.status}</Badge>}
                            </span>
                          </div>
                        </div>
                        <Link className="h-4 w-4 text-muted-foreground" />
                        <select
                          className="flex-1 px-3 py-1.5 rounded border bg-background text-sm"
                          value={selectedMappings[p.id] || p.s3_folder || ""}
                          onChange={(e) => setSelectedMappings(prev => ({
                            ...prev,
                            [p.id]: e.target.value || null
                          }))}
                        >
                          <option value="">-- Sem mapeamento --</option>
                          {s3MappingData.available_folders?.map((folder) => (
                            <option key={folder.path} value={folder.path}>
                              {folder.name}
                            </option>
                          ))}
                        </select>
                        <Button 
                          size="sm" 
                          variant="outline"
                          onClick={() => saveClientS3Mapping(p.id, selectedMappings[p.id] || p.s3_folder)}
                          disabled={savingS3Mapping}
                        >
                          {savingS3Mapping ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Save className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    ))}
                    {filteredS3Clients?.length === 0 && (
                      <p className="text-center text-muted-foreground py-4">Nenhum cliente encontrado</p>
                    )}
                  </div>
                  
                  <div className="flex justify-between items-center pt-2 border-t">
                    <p className="text-xs text-muted-foreground">
                      {s3MappingData.available_folders?.length || 0} pastas S3 disponíveis • {s3MappingData.processes?.length || 0} clientes
                    </p>
                    <Button onClick={saveAllClientS3Mappings} disabled={savingS3Mapping || Object.keys(selectedMappings).length === 0}>
                      {savingS3Mapping ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Save className="h-4 w-4 mr-2" />
                      )}
                      Guardar Alterações ({Object.keys(selectedMappings).length})
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ Sincronização Produção → Desenvolvimento (RGPD) ═══ */}
        {isDevEnvironment && hasRole(user, "admin") && (
          <div className="border rounded-lg p-4 border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-950/30">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h4 className="font-medium flex items-center gap-2">
                  <Database className="h-4 w-4 text-red-600" />
                  Sincronizar BD com Produção (Anonimizado)
                </h4>
                <p className="text-sm text-muted-foreground mt-1">
                  Copia dados de Produção para Dev com anonimização RGPD. 
                  Dados pessoais (email, NIF, telefone) são mascarados automaticamente.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 mb-3">
              <Button
                variant="destructive"
                onClick={() => setShowSyncConfirmModal(true)}
                disabled={syncing || syncPolling}
              >
                {syncing || syncPolling ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Database className="h-4 w-4 mr-2" />
                )}
                {syncPolling ? "Sincronizando..." : "Sincronizar BD com Produção"}
              </Button>
              {syncStatus?.last_result && (
                <span className="text-xs text-muted-foreground">
                  Última: {syncStatus.last_result.success ? "Sucesso" : "Com erros"} — {syncStatus.last_result.total_documents || 0} docs
                </span>
              )}
            </div>

            <div className="bg-red-100 dark:bg-red-900/30 rounded p-3 text-xs space-y-1 text-red-800 dark:text-red-200">
              <p className="font-semibold">⚠️ Atenção — Esta ação é irreversível:</p>
              <ul className="list-disc list-inside space-y-0.5 ml-1">
                <li>Todos os dados atuais de Desenvolvimento serão <strong>apagados</strong></li>
                <li>Dados de clientes serão <strong>anonimizados</strong> (email, NIF, telefone)</li>
                <li>Links S3/AWS serão <strong>removidos</strong></li>
                <li>Dados financeiros ultra-sensíveis serão <strong>limpos</strong></li>
                <li>Consultores mantêm credenciais de login reais</li>
              </ul>
            </div>
          </div>
        )}
      </CardContent>
    </Card>

    {/* ═══ Modal de Confirmação Dupla para Sync ═══ */}
    <Dialog open={showSyncConfirmModal} onOpenChange={setShowSyncConfirmModal}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Confirmação de Sincronização
          </DialogTitle>
          <DialogDescription>
            Esta operação vai apagar todos os dados de Desenvolvimento e substituí-los por uma cópia anonimizada de Produção.
          </DialogDescription>
        </DialogHeader>

        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-4 space-y-2 text-sm">
          <p className="font-medium text-red-800 dark:text-red-200">
            ⚠️ AVISO: Ação irreversível
          </p>
          <p>
            Isto vai <strong>apagar todos os dados atuais de Desenvolvimento</strong> e importar uma 
            cópia <strong>mascarada de Produção</strong>.
          </p>
          <ul className="list-disc list-inside space-y-1 ml-1 text-muted-foreground">
            <li>Emails de clientes → <code className="text-xs bg-muted px-1 rounded">user&#123;id&#125;@powercell.dev</code></li>
            <li>NIFs → NIFs falsos mas válidos</li>
            <li>Telefones → Números baralhados</li>
            <li>Nomes → Apelidos ofuscados</li>
            <li>Links S3 → Removidos</li>
            <li>Dados financeiros → Limpos</li>
            <li>Consultores → Emails e passwords mantidos para login</li>
          </ul>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => setShowSyncConfirmModal(false)}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleStartSync}
            disabled={syncing}
          >
            {syncing ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Database className="h-4 w-4 mr-2" />
            )}
            Confirmar e Sincronizar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}

