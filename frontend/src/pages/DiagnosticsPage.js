/**
 * DiagnosticsPage — Página de diagnósticos e verificação de saúde do sistema.
 *
 * PORQUÊ: Ferramenta administrativa para verificar o estado dos serviços externos (MongoDB, Redis, S3,
 * OpenAI), conexões WebSocket, e configurações do sistema.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { 
  RefreshCw, 
  CheckCircle, 
  XCircle, 
  AlertTriangle, 
  Settings,
  Mail,
  HardDrive,
  Brain,
  Trello,
  Database,
  Bell,
  ChevronRight,
  Clock,
  Timer,
  Play,
  Loader2
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { getTTLStatus, migrateTTLFields } from "../services/api";
import { toast } from "../hooks/use-toast";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const serviceIcons = {
  email: Mail,
  storage: HardDrive,
  ai: Brain,
  trello: Trello,
  backup: Database,
  notifications: Bell
};

const statusColors = {
  ok: "bg-green-500",
  warning: "bg-yellow-500", 
  error: "bg-red-500",
  not_configured: "bg-gray-400"
};

const statusLabels = {
  ok: "Operacional",
  warning: "Atenção",
  error: "Erro",
  not_configured: "Não Configurado"
};

const ServiceCard = ({ serviceKey, service, onConfigure }) => {
  const Icon = serviceIcons[serviceKey] || Settings;
  
  return (
    <Card className={`border-l-4 ${
      service.status === "ok" ? "border-l-green-500" :
      service.status === "warning" ? "border-l-yellow-500" :
      service.status === "error" ? "border-l-red-500" :
      "border-l-gray-400"
    }`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${
              service.status === "ok" ? "bg-green-100 text-green-700" :
              service.status === "warning" ? "bg-yellow-100 text-yellow-700" :
              service.status === "error" ? "bg-red-100 text-red-700" :
              "bg-gray-100 text-gray-500"
            }`}>
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base">{service.name}</CardTitle>
              <Badge 
                variant="outline" 
                className={`mt-1 ${
                  service.status === "ok" ? "text-green-700 border-green-300" :
                  service.status === "warning" ? "text-yellow-700 border-yellow-300" :
                  service.status === "error" ? "text-red-700 border-red-300" :
                  "text-gray-500 border-gray-300"
                }`}
              >
                {statusLabels[service.status]}
              </Badge>
            </div>
          </div>
          {!service.configured && (
            <Button 
              variant="outline" 
              size="sm"
              onClick={onConfigure}
              className="gap-1"
            >
              Configurar
              <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-2">{service.message}</p>
        
        {service.config_fields && service.config_fields.length > 0 && (
          <div className="mt-2 p-2 bg-muted rounded text-xs">
            <span className="font-medium">Campos em falta:</span>{" "}
            {service.config_fields.join(", ")}
          </div>
        )}
        
        {service.last_activity && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground mt-2">
            <Clock className="h-3 w-3" />
            Última actividade: {new Date(service.last_activity).toLocaleString("pt-PT")}
          </div>
        )}
        
        {service.stats && (
          <div className="mt-2 flex gap-4 text-xs">
            {Object.entries(service.stats).map(([key, value]) => (
              <div key={key} className="bg-muted px-2 py-1 rounded">
                <span className="text-muted-foreground">{key.replace(/_/g, " ")}:</span>{" "}
                <span className="font-medium">{String(value)}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const DiagnosticsPage = ({ embedded = false }) => {
  const [diagnostics, setDiagnostics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ttlStatus, setTTLStatus] = useState(null);
  const [ttlLoading, setTTLLoading] = useState(false);
  const [migrating, setMigrating] = useState(false);
  const [migrationResult, setMigrationResult] = useState(null);
  const { token } = useAuth();
  const navigate = useNavigate();

  const fetchDiagnostics = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_URL}/api/diagnostics`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      
      if (!response.ok) throw new Error("Erro ao carregar diagnósticos");
      
      const data = await response.json();
      setDiagnostics(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchTTLStatus = async () => {
    setTTLLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/diagnostics/ttl-status`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setTTLStatus(data);
      }
    } catch (err) {
      console.error("Erro ao carregar estado TTL:", err);
    } finally {
      setTTLLoading(false);
    }
  };

  const handleMigrateTTL = async () => {
    setMigrating(true);
    setMigrationResult(null);
    
    try {
      const response = await fetch(`${API_URL}/api/diagnostics/migrate-ttl-fields`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      
      if (!response.ok) throw new Error("Erro na migração");
      
      const data = await response.json();
      setMigrationResult(data);
      
      toast({
        title: "Migração Concluída",
        description: data.message,
        variant: data.total_migrated > 0 ? "default" : "default",
      });
      
      // Refrescar estado TTL
      await fetchTTLStatus();
    } catch (err) {
      toast({
        title: "Erro na Migração",
        description: err.message,
        variant: "destructive",
      });
    } finally {
      setMigrating(false);
    }
  };

  useEffect(() => {
    fetchDiagnostics();
    fetchTTLStatus();
  }, [token]);

  const handleConfigure = (service) => {
    navigate("/configuracoes");
  };

  if (loading && !diagnostics) {
    const loadingContent = (
      <div className="space-y-6">
        <div className="h-7 w-48 bg-muted animate-pulse rounded" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />)}
        </div>
      </div>
    );
    return embedded ? loadingContent : <DashboardLayout>{loadingContent}</DashboardLayout>;
  }

  const pageContent = (
    <div className="space-y-6" data-testid="diagnostics-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Diagnóstico do Sistema</h1>
          <p className="text-muted-foreground">
            Estado dos serviços e configurações
          </p>
        </div>
        <Button 
          onClick={fetchDiagnostics} 
          disabled={loading}
          variant="outline"
          className="gap-2"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertTitle>Erro</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {diagnostics && (
        <>
          {/* Resumo */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="bg-green-50 border-green-200">
              <CardContent className="pt-4 text-center">
                <CheckCircle className="h-8 w-8 text-green-600 mx-auto mb-2" />
                <div className="text-2xl font-bold text-green-700">{diagnostics.summary.ok}</div>
                <div className="text-sm text-green-600">Operacionais</div>
              </CardContent>
            </Card>
            
            <Card className="bg-yellow-50 border-yellow-200">
              <CardContent className="pt-4 text-center">
                <AlertTriangle className="h-8 w-8 text-yellow-600 mx-auto mb-2" />
                <div className="text-2xl font-bold text-yellow-700">{diagnostics.summary.warning}</div>
                <div className="text-sm text-yellow-600">Atenção</div>
              </CardContent>
            </Card>
            
            <Card className="bg-red-50 border-red-200">
              <CardContent className="pt-4 text-center">
                <XCircle className="h-8 w-8 text-red-600 mx-auto mb-2" />
                <div className="text-2xl font-bold text-red-700">{diagnostics.summary.error}</div>
                <div className="text-sm text-red-600">Erros</div>
              </CardContent>
            </Card>
            
            <Card className="bg-gray-50 border-gray-200">
              <CardContent className="pt-4 text-center">
                <Settings className="h-8 w-8 text-gray-500 mx-auto mb-2" />
                <div className="text-2xl font-bold text-gray-700">{diagnostics.summary.not_configured}</div>
                <div className="text-sm text-gray-600">Por Configurar</div>
              </CardContent>
            </Card>
          </div>

          {/* Serviços */}
          <div className="grid md:grid-cols-2 gap-4">
            {Object.entries(diagnostics.services).map(([key, service]) => (
              <ServiceCard 
                key={key}
                serviceKey={key}
                service={service}
                onConfigure={() => handleConfigure(key)}
              />
            ))}
          </div>

          {/* Erros Recentes */}
          {diagnostics.recent_errors && diagnostics.recent_errors.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-red-500" />
                  Erros Recentes
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {diagnostics.recent_errors.map((error, i) => (
                    <div key={i} className="p-3 bg-red-50 rounded text-sm">
                      <div className="flex justify-between">
                        <span className="font-medium text-red-800">{error.component || "Sistema"}</span>
                        <span className="text-xs text-red-600">
                          {error.timestamp ? new Date(error.timestamp).toLocaleString("pt-PT") : ""}
                        </span>
                      </div>
                      <p className="text-red-700 mt-1">{error.message}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Gestão de Ciclo de Vida de Dados (TTL) */}
          <Card className="border-t-4 border-t-purple-500">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-purple-100 text-purple-700">
                    <Timer className="h-5 w-5" />
                  </div>
                  <div>
                    <CardTitle className="text-lg">Gestão de Ciclo de Vida de Dados (TTL)</CardTitle>
                    <CardDescription>
                      Purga automática de dados efémeros (sessões, logs, rascunhos)
                    </CardDescription>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={fetchTTLStatus}
                  disabled={ttlLoading}
                >
                  <RefreshCw className={`h-4 w-4 ${ttlLoading ? "animate-spin" : ""}`} />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Estado das coleções TTL */}
              {ttlStatus && ttlStatus.collections && (
                <div className="space-y-3">
                  {ttlStatus.collections.map((col, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className={`p-1.5 rounded ${
                          col.status === "ok" ? "bg-green-100 text-green-600" :
                          col.status === "needs_migration" ? "bg-yellow-100 text-yellow-600" :
                          "bg-red-100 text-red-600"
                        }`}>
                          <Database className="h-4 w-4" />
                        </div>
                        <div>
                          <div className="font-medium text-sm">{col.name}</div>
                          <div className="text-xs text-muted-foreground">
                            TTL: {col.ttl_description} ({col.ttl_field})
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <div className="text-right">
                          <div className="font-medium">{col.with_datetime_field}/{col.total_documents}</div>
                          <div className="text-xs text-muted-foreground">migrados</div>
                        </div>
                        {col.pending_migration > 0 && (
                          <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300">
                            {col.pending_migration} pendentes
                          </Badge>
                        )}
                        {col.status === "ok" && (
                          <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            OK
                          </Badge>
                        )}
                        {col.ttl_index_exists && (
                          <Badge variant="outline" className="text-purple-700 border-purple-300">
                            Índice TTL ativo
                          </Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Resultado da migração */}
              {migrationResult && (
                <Alert className={migrationResult.total_migrated > 0 ? "border-green-500 bg-green-50" : ""}>
                  <CheckCircle className="h-4 w-4" />
                  <AlertTitle>Migração Concluída</AlertTitle>
                  <AlertDescription>
                    {migrationResult.message}
                    {migrationResult.results && (
                      <div className="mt-2 text-sm space-y-1">
                        {migrationResult.results.map((r, i) => (
                          <div key={i} className="flex justify-between">
                            <span>{r.collection}:</span>
                            <span>
                              {r.migrated} migrados, {r.already_migrated} já estavam migrados
                              {r.errors > 0 && <span className="text-red-600 ml-2">({r.errors} erros)</span>}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </AlertDescription>
                </Alert>
              )}

              {/* Botão de migração */}
              <div className="flex items-center gap-3 pt-2">
                <Button
                  onClick={handleMigrateTTL}
                  disabled={migrating}
                  className="gap-2"
                >
                  {migrating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      A migrar...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Correr Migração TTL
                    </>
                  )}
                </Button>
                <p className="text-xs text-muted-foreground">
                  Popula campos datetime nativos para que os índices TTL funcionem.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Timestamp */}
          <div className="text-xs text-muted-foreground text-right">
            Última verificação: {new Date(diagnostics.timestamp).toLocaleString("pt-PT")}
          </div>
        </>
      )}
    </div>
  );

  return embedded ? pageContent : <DashboardLayout>{pageContent}</DashboardLayout>;
};

export default DiagnosticsPage;

