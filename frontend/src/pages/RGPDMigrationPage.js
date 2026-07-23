/**
 * RGPDMigrationPage - Página de Migração de Encriptação RGPD
 * Permite ao admin executar a migração de encriptação de dados de clientes
 * 
 * Funcionalidades:
 * - Ver estado atual da migração
 * - Executar migração completa
 * - Testar migração com cliente específico
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Shield,
  Lock,
  Database,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Play,
  Search,
  Key,
  Hash,
  Eye,
  Server,
} from "lucide-react";
import {
  LoadingState,
  AccessRestricted,
  PageHeader,
} from "../components/admin/AdminPageShared";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Componente de estatística de migração
const MigrationStatCard = ({ title, value, percentage, icon: Icon, color, description }) => (
  <Card>
    <CardContent className="pt-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {percentage !== undefined && (
            <p className="text-xs text-muted-foreground mt-1">{percentage}% do total</p>
          )}
          {description && (
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          )}
        </div>
        <div className={`p-3 rounded-full ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </CardContent>
  </Card>
);

// Barra de progresso de migração
const MigrationProgress = ({ migrated, total }) => {
  const percentage = total > 0 ? Math.round((migrated / total) * 100) : 0;
  
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span>Progresso da Migração</span>
        <span>{migrated} de {total} clientes</span>
      </div>
      <Progress value={percentage} className="h-2" />
      <p className="text-xs text-muted-foreground text-right">{percentage}%</p>
    </div>
  );
};

// Página principal
const RGPDMigrationPage = () => {
  const { token, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [migrating, setMigrating] = useState(false);
  const [status, setStatus] = useState(null);
  const [testClientId, setTestClientId] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [confirmModal, setConfirmModal] = useState(false);

  // Verificar acesso - apenas Admin, CEO ou Diretor
  const allowedRoles = ["admin", "ceo", "diretor"];
  const hasAccess = allowedRoles.includes(user?.role?.toLowerCase());

  // Carregar estado da migração
  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/migration/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setStatus(data);
      } else if (response.status === 403) {
        toast.error("Não tem permissão para aceder a esta página");
      } else {
        toast.error("Erro ao carregar estado da migração");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar estado da migração");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (hasAccess) {
      fetchStatus();
    }
  }, [fetchStatus, hasAccess]);

  // Executar migração completa
  const handleRunMigration = async () => {
    setMigrating(true);
    setConfirmModal(false);
    
    try {
      const response = await fetch(`${API_URL}/api/admin/migration/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        
        // Polling para verificar progresso
        const pollInterval = setInterval(async () => {
          const statusResponse = await fetch(`${API_URL}/api/admin/migration/status`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          
          if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            setStatus(statusData);
            
            // Se migração concluída, parar polling
            if (statusData.needs_migration?.count === 0) {
              clearInterval(pollInterval);
              setMigrating(false);
              toast.success("Migração concluída com sucesso!");
            }
          }
        }, 3000);
        
        // Timeout após 5 minutos
        setTimeout(() => {
          clearInterval(pollInterval);
          setMigrating(false);
        }, 5 * 60 * 1000);
        
      } else {
        const error = await response.json();
        toast.error(extractErrorMessage(error.detail, "Erro ao iniciar migração"));
        setMigrating(false);
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao iniciar migração");
      setMigrating(false);
    }
  };

  // Testar migração com cliente específico
  const handleTestMigration = async () => {
    if (!testClientId.trim()) {
      toast.error("Introduza um ID de cliente válido");
      return;
    }

    setTestResult(null);
    
    try {
      const response = await fetch(`${API_URL}/api/admin/migration/run-single/${testClientId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setTestResult(data);
        
        if (data.success) {
          toast.success(data.message);
        }
      } else {
        const error = await response.json();
        setTestResult({ success: false, message: extractErrorMessage(error.detail, "Erro ao migrar cliente") });
        toast.error(extractErrorMessage(error.detail, "Erro ao migrar cliente"));
      }
    } catch (error) {
      console.error("Erro:", error);
      setTestResult({ success: false, message: "Erro de ligação" });
      toast.error("Erro de ligação");
    }
  };

  // Verificar acesso
  if (!hasAccess) {
    return (
      <DashboardLayout>
        <AccessRestricted userRole={user?.role} allowedRoles={allowedRoles} />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <PageHeader
          icon={Shield}
          title="Migração RGPD"
          description="Encriptação de dados sensíveis de clientes com blind indexing para pesquisa segura"
          onRefresh={fetchStatus}
        />

        {/* Alerta de Segurança */}
        <Alert className="border-blue-200 bg-blue-50 dark:bg-blue-950/30">
          <Shield className="h-4 w-4 text-blue-600" />
          <AlertTitle className="text-blue-800 dark:text-blue-200">Segurança RGPD</AlertTitle>
          <AlertDescription className="text-blue-700 dark:text-blue-300">
            Esta ferramenta encripta dados sensíveis (NIFs, telefones, moradas) e gera blind indexes
            para permitir pesquisa sem expor os dados reais. A migração é irreversível.
          </AlertDescription>
        </Alert>

        {loading ? (
          <Card>
            <CardContent className="py-12">
              <LoadingState />
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Estado do Serviço de Encriptação */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Server className="h-5 w-5" />
                  Estado do Serviço
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  {status?.encryption_service_available ? (
                    <>
                      <Badge className="bg-green-100 text-green-800 border-green-300">
                        <CheckCircle className="h-3 w-3 mr-1" />
                        Encriptação Disponível
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        Os dados serão encriptados com AES-128-CBC + HMAC
                      </span>
                    </>
                  ) : (
                    <>
                      <Badge className="bg-yellow-100 text-yellow-800 border-yellow-300">
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        Encriptação Parcial
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        Apenas blind indexes serão gerados (sem encriptação de dados)
                      </span>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Estatísticas */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MigrationStatCard
                title="Total de Clientes"
                value={status?.total_clients || 0}
                icon={Database}
                color="bg-blue-100 text-blue-600"
              />
              <MigrationStatCard
                title="Com NIF Hash"
                value={status?.blind_indexes?.nif_hash?.count || 0}
                percentage={status?.blind_indexes?.nif_hash?.percentage}
                icon={Hash}
                color="bg-green-100 text-green-600"
              />
              <MigrationStatCard
                title="NIF Encriptado"
                value={status?.encryption_status?.nif_encrypted?.count || 0}
                percentage={status?.encryption_status?.nif_encrypted?.percentage}
                icon={Lock}
                color="bg-purple-100 text-purple-600"
              />
              <MigrationStatCard
                title="Necessitam Migração"
                value={status?.needs_migration?.count || 0}
                percentage={status?.needs_migration?.percentage}
                icon={AlertTriangle}
                color="bg-orange-100 text-orange-600"
              />
            </div>

            {/* Detalhes de Blind Indexes */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Hash className="h-5 w-5" />
                  Blind Indexes (Hash Determinístico)
                </CardTitle>
                <CardDescription>
                  Permite pesquisar dados encriptados sem expor o valor real
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-4 bg-muted/50 rounded-lg">
                    <p className="text-2xl font-bold text-green-600">
                      {status?.blind_indexes?.nif_hash?.count || 0}
                    </p>
                    <p className="text-sm text-muted-foreground">nif_hash</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {status?.blind_indexes?.nif_hash?.percentage || 0}%
                    </p>
                  </div>
                  <div className="text-center p-4 bg-muted/50 rounded-lg">
                    <p className="text-2xl font-bold text-blue-600">
                      {status?.blind_indexes?.email_hash?.count || 0}
                    </p>
                    <p className="text-sm text-muted-foreground">email_hash</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {status?.blind_indexes?.email_hash?.percentage || 0}%
                    </p>
                  </div>
                  <div className="text-center p-4 bg-muted/50 rounded-lg">
                    <p className="text-2xl font-bold text-purple-600">
                      {status?.blind_indexes?.telefone_hash?.count || 0}
                    </p>
                    <p className="text-sm text-muted-foreground">telefone_hash</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {status?.blind_indexes?.telefone_hash?.percentage || 0}%
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Ações */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Executar Migração */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Play className="h-5 w-5" />
                    Executar Migração
                  </CardTitle>
                  <CardDescription>
                    Migra todos os clientes que ainda têm dados em plain text
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {status?.needs_migration?.count === 0 ? (
                    <Alert className="border-green-200 bg-green-50 dark:bg-green-950/30">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      <AlertTitle>Todos os clientes migrados!</AlertTitle>
                      <AlertDescription>
                        Não existem clientes que necessitem de migração.
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">
                        <strong>{status?.needs_migration?.count || 0}</strong> clientes 
                        ({status?.needs_migration?.percentage || 0}%) têm dados sensíveis 
                        que precisam de ser encriptados.
                      </p>
                      
                      <Button
                        onClick={() => setConfirmModal(true)}
                        disabled={migrating}
                        className="w-full"
                        size="lg"
                      >
                        {migrating ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            A migrar...
                          </>
                        ) : (
                          <>
                            <Lock className="h-4 w-4 mr-2" />
                            Executar Migração Completa
                          </>
                        )}
                      </Button>
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Testar com Cliente */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Search className="h-5 w-5" />
                    Testar Migração
                  </CardTitle>
                  <CardDescription>
                    Testar a migração com um cliente específico antes de executar em todos
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="clientId">ID do Cliente</Label>
                    <div className="flex gap-2">
                      <Input
                        id="clientId"
                        value={testClientId}
                        onChange={(e) => setTestClientId(e.target.value)}
                        placeholder="abc-123-def..."
                      />
                      <Button onClick={handleTestMigration}>
                        <Play className="h-4 w-4 mr-2" />
                        Testar
                      </Button>
                    </div>
                  </div>

                  {testResult && (
                    <Alert className={testResult.success ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}>
                      {testResult.success ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-600" />
                      )}
                      <AlertTitle>{testResult.success ? "Sucesso" : "Erro"}</AlertTitle>
                      <AlertDescription>
                        {testResult.message}
                        {testResult.changes && testResult.changes.length > 0 && (
                          <ul className="mt-2 text-sm list-disc list-inside">
                            {testResult.changes.map((change, i) => (
                              <li key={i}>{change}</li>
                            ))}
                          </ul>
                        )}
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Informações sobre dados encriptados */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Eye className="h-5 w-5" />
                  Estado da Encriptação
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {/* NIF */}
                  <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Key className="h-5 w-5 text-purple-600" />
                      <div>
                        <p className="font-medium">NIF (dados_pessoais.nif)</p>
                        <p className="text-xs text-muted-foreground">
                          {status?.encryption_status?.nif_encrypted?.count || 0} encriptados, {" "}
                          {status?.encryption_status?.nif_plain_text?.count || 0} em plain text
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <Badge variant={status?.encryption_status?.nif_plain_text?.count > 0 ? "destructive" : "default"}>
                        {status?.encryption_status?.nif_plain_text?.count > 0 ? "Pendente" : "OK"}
                      </Badge>
                    </div>
                  </div>

                  {/* Telefone */}
                  <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Key className="h-5 w-5 text-blue-600" />
                      <div>
                        <p className="font-medium">Telefone (contacto.telefone)</p>
                        <p className="text-xs text-muted-foreground">
                          {status?.encryption_status?.telefone_encrypted?.count || 0} encriptados
                        </p>
                      </div>
                    </div>
                    <Badge variant="outline">
                      {status?.encryption_status?.telefone_encrypted?.percentage || 0}%
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {/* Modal de Confirmação */}
        <Dialog open={confirmModal} onOpenChange={setConfirmModal}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-orange-500" />
                Confirmar Migração
              </DialogTitle>
              <DialogDescription>
                Está prestes a encriptar dados sensíveis de <strong>{status?.needs_migration?.count || 0}</strong> clientes.
                Esta operação irá:
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 py-4">
              <div className="flex items-start gap-3">
                <Lock className="h-5 w-5 text-purple-600 mt-0.5" />
                <div>
                  <p className="font-medium">Encriptar dados sensíveis</p>
                  <p className="text-sm text-muted-foreground">
                    NIFs, telefones, moradas e documentos serão encriptados
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Hash className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium">Gerar blind indexes</p>
                  <p className="text-sm text-muted-foreground">
                    Hashes determinísticos para pesquisa de dados encriptados
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-orange-500 mt-0.5" />
                <div>
                  <p className="font-medium text-orange-700">Irreversível</p>
                  <p className="text-sm text-muted-foreground">
                    Após encriptação, os dados só podem ser lidos pela aplicação
                  </p>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmModal(false)}>
                Cancelar
              </Button>
              <Button onClick={handleRunMigration} disabled={migrating}>
                {migrating ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Lock className="h-4 w-4 mr-2" />
                )}
                Confirmar Migração
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default RGPDMigrationPage;
