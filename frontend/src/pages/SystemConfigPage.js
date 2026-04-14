/**
 * SystemConfigPage - Página de Configurações do Sistema
 * Permite ao admin configurar integrações e definições
 */
import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Textarea } from "../components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import DocumentRecipientsManager from "../components/DocumentRecipientsManager";
import RichTextEditor from "../components/ui/RichTextEditor";
import SmartRichEditor from "../components/ui/SmartRichEditor";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Settings,
  Cloud,
  Mail,
  Sparkles,
  Trello,
  Building,
  Building2,
  Save,
  Loader2,
  CheckCircle,
  XCircle,
  RefreshCw,
  TestTube,
  Eye,
  EyeOff,
  Wrench,
  Database,
  AlertTriangle,
  Trash2,
  Users,
  FolderOpen,
  Link,
  UserCheck,
  FileEdit,
  FileSignature,
  History,
  Info,
  RotateCcw,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícones por secção
const SECTION_ICONS = {
  storage: Cloud,
  email: Mail,
  ai: Sparkles,
  trello: Trello,
  settings: Building,
  maintenance: Wrench,
  document_recipients: Building2,
  auto_draft: FileEdit,
  rgpd: FileSignature,
};

// Componente para campo de configuração
const ConfigFieldInput = ({ field, value, onChange, allValues, sectionName }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [revealedValue, setRevealedValue] = useState(null);
  const [loadingReveal, setLoadingReveal] = useState(false);

  const handleRevealSecret = async () => {
    setLoadingReveal(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/system-config/reveal-secrets?section=${sectionName}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const secretVal = data.secrets?.[field.key];
        if (secretVal) {
          setRevealedValue(secretVal);
          setShowPassword(true);
        }
      }
    } catch (err) {
      console.error("Erro ao revelar password:", err);
    } finally {
      setLoadingReveal(false);
    }
  };

  // Reset revealed value when password field value changes
  useEffect(() => {
    if (field.type === "password" && value && value !== "••••••••" && value !== revealedValue) {
      setRevealedValue(null);
    }
  }, [value]);

  // Verificar dependências
  if (field.depends_on) {
    const [depKey, depValue] = Object.entries(field.depends_on)[0];
    const actualValue = allValues[depKey];
    
    // Comparação flexível para lidar com diferentes tipos (boolean/string)
    const matches = 
      actualValue === depValue || 
      String(actualValue) === String(depValue) ||
      (depValue === true && (actualValue === true || actualValue === "true")) ||
      (depValue === false && (actualValue === false || actualValue === "false"));
    
    if (!matches) {
      return null;
    }
  }

  // Ignorar campos de divisor (dividers) - são só para UI
  if (field.key?.startsWith("_divider")) {
    return (
      <div className="pt-6 pb-2 border-t mt-4">
        <h4 className="font-medium text-sm text-muted-foreground">{field.label}</h4>
      </div>
    );
  }

  const inputType = field.type === "password" && !showPassword ? "password" : "text";

  switch (field.type) {
    case "select":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <Select
            value={value || ""}
            onValueChange={(v) => onChange(field.key, v)}
          >
            <SelectTrigger id={field.key}>
              <SelectValue placeholder="Seleccione..." />
            </SelectTrigger>
            <SelectContent>
              {field.options?.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    case "boolean":
      return (
        <div className="flex items-center justify-between py-2">
          <div>
            <Label htmlFor={field.key}>{field.label}</Label>
            {field.help_text && (
              <p className="text-xs text-muted-foreground">{field.help_text}</p>
            )}
          </div>
          <Switch
            id={field.key}
            checked={value || false}
            onCheckedChange={(v) => onChange(field.key, v)}
          />
        </div>
      );

    case "password":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                id={field.key}
                type={inputType}
                value={showPassword && revealedValue ? revealedValue : (value || "")}
                onChange={(e) => { setRevealedValue(null); onChange(field.key, e.target.value); }}
                placeholder={field.placeholder}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                onClick={() => { if (showPassword) { setShowPassword(false); setRevealedValue(null); } else { handleRevealSecret(); } }}
                title={showPassword ? "Ocultar valor" : "Mostrar valor actual"}
              >
                {loadingReveal ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    case "number":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <Input
            id={field.key}
            type="number"
            value={value || ""}
            onChange={(e) => onChange(field.key, parseInt(e.target.value) || "")}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    case "textarea":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <RichTextEditor
            value={value || ""}
            onChange={(val) => onChange(field.key, val)}
            placeholder={field.placeholder}
            advanced
            minHeight={200}
            className="min-h-[200px]"
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    default:
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <Input
            id={field.key}
            type="text"
            value={value || ""}
            onChange={(e) => onChange(field.key, e.target.value)}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );
  }
};

// Componente para secção de configuração
const ConfigSection = ({ section, sectionKey, config, fields, onSave, onTest }) => {
  const [localConfig, setLocalConfig] = useState(config || {});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setLocalConfig(config || {});
    setHasChanges(false);
  }, [config]);

  const handleChange = (key, value) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
    setTestResult(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(sectionKey, localConfig);
      setHasChanges(false);
      toast.success("Configuração guardada");
    } catch (error) {
      toast.error("Erro ao guardar");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await onTest(sectionKey);
      setTestResult(result);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      setTestResult({ success: false, message: "Erro ao testar" });
    } finally {
      setTesting(false);
    }
  };

  const Icon = SECTION_ICONS[sectionKey] || Settings;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-lg">{section.title}</CardTitle>
              <CardDescription>{section.description}</CardDescription>
            </div>
          </div>
          {hasChanges && (
            <Badge variant="outline" className="bg-yellow-50 text-yellow-700">
              Alterações por guardar
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {fields.map((field) => (
          <ConfigFieldInput
            key={field.key}
            field={field}
            value={localConfig[field.key]}
            onChange={handleChange}
            allValues={localConfig}
            sectionName={sectionKey}
          />
        ))}

        {/* Test result */}
        {testResult && (
          <div
            className={`flex items-center gap-2 p-3 rounded-lg ${
              testResult.success
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            {testResult.success ? (
              <CheckCircle className="h-4 w-4" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
            <span className="text-sm">{testResult.message}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-4 border-t">
          <Button onClick={handleSave} disabled={saving || !hasChanges}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Guardar
          </Button>

          {["storage", "email", "ai", "trello"].includes(sectionKey) && (
            <Button variant="outline" onClick={handleTest} disabled={testing}>
              {testing ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <TestTube className="h-4 w-4 mr-2" />
              )}
              Testar Ligação
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

const SystemConfigPage = () => {
  const { token, user } = useAuth();
  const [searchParams] = useSearchParams();
  const [config, setConfig] = useState(null);
  const [fields, setFields] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(() => searchParams.get("tab") || "storage");

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/system-config`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        // Converter arrays para string em campos textarea
        if (data.config?.auto_draft?.eligible_doc_types) {
          data.config.auto_draft.eligible_doc_types = JSON.stringify(
            data.config.auto_draft.eligible_doc_types,
            null,
            2
          );
        }
        setConfig(data.config);
        setFields(data.fields);
      } else {
        toast.error("Erro ao carregar configurações");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar configurações");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = async (section, data) => {
    // Pré-processar campos especiais
    const processedData = { ...data };
    if (section === "auto_draft" && typeof processedData.eligible_doc_types === "string") {
      try {
        processedData.eligible_doc_types = JSON.parse(processedData.eligible_doc_types);
      } catch {
        toast.error("Formato inválido em Tipos de Documento Elegíveis (deve ser JSON array)");
        return;
      }
    }

    const response = await fetch(`${API_URL}/api/system-config/${section}`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(processedData),
    });

    if (!response.ok) {
      throw new Error("Erro ao guardar");
    }

    // Recarregar config
    await fetchConfig();
  };

  const handleTest = async (service) => {
    const response = await fetch(
      `${API_URL}/api/system-config/test-connection/${service}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    return await response.json();
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="h-7 w-64 bg-muted animate-pulse rounded" />
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1,2,3,4,5,6].map(i => <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />)}
          </div>
        </div>
      </DashboardLayout>
    );
  }
  if (!["admin", "ceo"].includes(user?.role)) {
    return (
      <DashboardLayout>
        <div className="text-center py-12">
          <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold">Acesso Restrito</h2>
          <p className="text-muted-foreground">
            Apenas administradores podem aceder às configurações do sistema.
          </p>
        </div>
      </DashboardLayout>
    );
  }

  const sections = Object.keys(fields);

  // Componente de Manutenção do Sistema
  const MaintenanceSection = () => {
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
          toast.error(data.detail || "Erro ao guardar mapeamento");
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
          toast.error(data.detail || "Erro no auto-mapeamento");
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
          toast.error(data.detail || "Erro ao corrigir nomes");
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

    return (
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
                        <p className="text-2xl font-bold text-purple-600">{s3MappingData.stats?.total || 0}</p>
                        <p className="text-xs text-muted-foreground">Total de Clientes</p>
                      </div>
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-green-600">{s3MappingData.stats?.mapped || 0}</p>
                        <p className="text-xs text-muted-foreground">Com Mapeamento</p>
                      </div>
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-orange-600">{s3MappingData.stats?.unmapped || 0}</p>
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
        </CardContent>
      </Card>
    );
  };

  // Componente de Gestão RGPD
  const RGPDTab = () => {
    const [templateContent, setTemplateContent] = useState("");
    const [originalContent, setOriginalContent] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [templateMeta, setTemplateMeta] = useState({
      is_default: true,
      version: null,
      updated_at: null,
      updated_by: null,
    });
    const [versions, setVersions] = useState([]);
    const [loadingVersions, setLoadingVersions] = useState(false);
    const [changelog, setChangelog] = useState("");
    const [showRgpdPreview, setShowRgpdPreview] = useState(false);
    
    const isAdminOrCEO = user?.role === "admin" || user?.role === "ceo";

    useEffect(() => {
      fetchTemplate();
    }, [token]);

    const fetchTemplate = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setTemplateContent(data.content);
          setOriginalContent(data.content);
          setTemplateMeta({
            is_default: data.is_default,
            version: data.version,
            updated_at: data.updated_at,
            updated_by: data.updated_by,
          });
        }
      } catch (error) {
        console.error("Erro:", error);
        toast.error("Erro ao carregar o template RGPD");
      } finally {
        setLoading(false);
      }
    };

    const fetchVersions = async () => {
      setLoadingVersions(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template/versions`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setVersions(data.versions || []);
        }
      } catch (error) {
        console.error("Erro:", error);
      } finally {
        setLoadingVersions(false);
      }
    };

    const handleSave = async () => {
      if (!templateContent.trim()) {
        toast.error("O template não pode estar vazio");
        return;
      }
      setSaving(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: templateContent, changelog: changelog || undefined }),
        });
        if (response.ok) {
          const data = await response.json();
          toast.success(`Template RGPD guardado (v${data.version || ""})`);
          setOriginalContent(templateContent);
          setChangelog("");
          fetchTemplate();
          fetchVersions();
        } else if (response.status === 403) {
          toast.error("Apenas Admin ou CEO podem editar o template");
        } else {
          toast.error("Erro ao guardar o template");
        }
      } catch (error) {
        toast.error("Erro ao guardar o template RGPD");
      } finally {
        setSaving(false);
      }
    };

    const handleReset = async () => {
      setSaving(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: "", changelog: "Restaurado para template padrão" }),
        });
        if (response.ok) {
          toast.success("Template restaurado para o valor padrão");
          fetchTemplate();
          fetchVersions();
        }
      } catch (error) {
        toast.error("Erro ao restaurar o template padrão");
      } finally {
        setSaving(false);
      }
    };

    const hasChanges = templateContent !== originalContent;

    if (loading) {
      return (
        <Card>
          <CardContent className="py-12 flex justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      );
    }

    return (
      <div className="space-y-4">
        {/* Info Bar */}
        <Card>
          <CardContent className="py-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-3">
                <Info className="h-4 w-4 text-blue-500" />
                <span className="text-sm text-muted-foreground">
                  {templateMeta.is_default
                    ? "A utilizar o template padrão. Edite para personalizar."
                    : `Versão ${templateMeta.version || "1.0"} — Última atualização: ${
                        templateMeta.updated_at
                          ? new Date(templateMeta.updated_at).toLocaleString("pt-PT")
                          : "N/A"
                      } ${templateMeta.updated_by ? `por ${templateMeta.updated_by}` : ""}`}
                </span>
              </div>
              {templateMeta.is_default ? (
                <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                  Template Padrão
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                  v{templateMeta.version || "1.0"}
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Editor */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileEdit className="h-5 w-5" />
              Texto do Formulário RGPD
            </CardTitle>
            <CardDescription>
              Edite o texto legal do formulário de consentimento RGPD. As variáveis serão substituídas automaticamente pelos dados do cliente.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SmartRichEditor
              value={templateContent}
              onChange={setTemplateContent}
              placeholder="Introduza o texto do template RGPD..."
              readOnly={!isAdminOrCEO}
              minHeight={300}
              advanced
            />

            {/* Variáveis disponíveis */}
            <div className="bg-muted/50 rounded-lg p-3">
              <p className="text-sm font-medium mb-2">Variáveis disponíveis:</p>
              <div className="flex flex-wrap gap-2">
                {[
                  "{{NOME_CLIENTE}}",
                  "{{NOME_EMPRESA}}",
                  "{{CONTRIBUINTE}}",
                  "{{MORADA}}",
                  "{{CODIGO_POSTAL}}",
                  "{{TIPO_DOCUMENTO}}",
                  "{{NUMERO_DOCUMENTO}}",
                  "{{VALIDADE_DOCUMENTO}}",
                  "{{DATA_ASSINATURA}}",
                ].map((variable) => (
                  <Badge key={variable} variant="secondary" className="font-mono text-xs">
                    {variable}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Changelog input */}
            {isAdminOrCEO && hasChanges && (
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Notas da alteração (opcional)</Label>
                <Input
                  value={changelog}
                  onChange={(e) => setChangelog(e.target.value)}
                  placeholder="Ex: Adicionado ponto sobre partilha de dados com bancos"
                />
              </div>
            )}

            {/* Actions */}
            {isAdminOrCEO ? (
              <div className="flex items-center justify-between pt-2 border-t">
                <Button
                  variant="outline"
                  onClick={handleReset}
                  disabled={saving || templateMeta.is_default}
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Restaurar Padrão
                </Button>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setShowRgpdPreview(true)}
                    className="gap-2"
                  >
                    👁️ Pré-visualizar RGPD
                  </Button>
                  {hasChanges && (
                    <span className="text-sm text-amber-600 font-medium">
                      Alterações por guardar
                    </span>
                  )}
                  <Button onClick={handleSave} disabled={saving || !hasChanges}>
                    {saving ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Save className="h-4 w-4 mr-2" />
                    )}
                    Guardar Template
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground pt-2 border-t">
                Apenas utilizadores Admin ou CEO podem editar o template RGPD.
              </p>
            )}

            {/* RGPD Preview Dialog */}
            <Dialog open={showRgpdPreview} onOpenChange={setShowRgpdPreview}>
              <DialogContent className="sm:max-w-[700px] max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Pré-visualização RGPD</DialogTitle>
                  <DialogDescription>
                    Visualização do texto tal como o cliente final o verá
                  </DialogDescription>
                </DialogHeader>
                <div className="prose prose-sm max-w-none bg-white border rounded-lg p-6"
                  dangerouslySetInnerHTML={{
                    __html: (templateContent || "")
                      .replace(/\{\{NOME_CLIENTE\}\}/g, "João Silva")
                      .replace(/\{\{NOME_EMPRESA\}\}/g, "Power Real Estate")
                      .replace(/\{\{CONTRIBUINTE\}\}/g, "123456789")
                      .replace(/\{\{MORADA\}\}/g, "Rua Example, 123, Lisboa")
                      .replace(/\{\{CODIGO_POSTAL\}\}/g, "1000-001")
                      .replace(/\{\{TIPO_DOCUMENTO\}\}/g, "Cartão de Cidadão")
                      .replace(/\{\{NUMERO_DOCUMENTO\}\}/g, "CC 00000000")
                      .replace(/\{\{VALIDADE_DOCUMENTO\}\}/g, "01/01/2030")
                      .replace(/\{\{DATA_ASSINATURA\}\}/g, new Date().toLocaleDateString("pt-PT"))
                  }}
                />
                <DialogFooter>
                  <Button variant="outline" onClick={() => setShowRgpdPreview(false)}>
                    Fechar
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </CardContent>
        </Card>

        {/* Version History */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-lg">Histórico de Versões</CardTitle>
                  <CardDescription>Cada alteração ao template cria uma nova versão para rastreio legal</CardDescription>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={fetchVersions} disabled={loadingVersions}>
                {loadingVersions ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-1" />
                )}
                Atualizar
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {versions.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Nenhuma versão anterior registada.
              </p>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {versions.map((v) => (
                  <div
                    key={v.id}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      v.is_active
                        ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                        : "bg-muted/30"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {v.is_active && <CheckCircle className="h-4 w-4 text-green-600" />}
                      <div>
                        <p className="text-sm font-medium">
                          Versão {v.version}
                          {v.is_active && (
                            <Badge variant="outline" className="ml-2 text-xs bg-green-100 text-green-700 border-green-300">
                              Ativa
                            </Badge>
                          )}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {v.created_at
                            ? new Date(v.created_at).toLocaleString("pt-PT")
                            : "N/A"}
                          {v.created_by ? ` — ${v.created_by}` : ""}
                        </p>
                        {v.changelog && (
                          <p className="text-xs text-muted-foreground italic mt-0.5">
                            {v.changelog}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Settings className="h-6 w-6" />
              Configurações do Sistema
            </h1>
            <p className="text-muted-foreground">
              Configure as integrações e definições da aplicação
            </p>
          </div>
          <Button variant="outline" onClick={fetchConfig}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Recarregar
          </Button>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-4 sm:grid-cols-6 lg:grid-cols-9">
            {sections.map((key) => {
              const Icon = SECTION_ICONS[key] || Settings;
              return (
                <TabsTrigger key={key} value={key} className="gap-2">
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{fields[key]?.title?.split(" ")[0]}</span>
                </TabsTrigger>
              );
            })}
            <TabsTrigger value="rgpd" className="gap-2">
              <FileSignature className="h-4 w-4" />
              <span className="hidden sm:inline">RGPD</span>
            </TabsTrigger>
            <TabsTrigger value="maintenance" className="gap-2">
              <Wrench className="h-4 w-4" />
              <span className="hidden sm:inline">Manutenção</span>
            </TabsTrigger>
          </TabsList>

          {sections.map((key) => (
            <TabsContent key={key} value={key} className="mt-6">
              {key === "document_recipients" ? (
                <DocumentRecipientsManager token={token} user={user} />
              ) : (
                <ConfigSection
                  section={fields[key]}
                  sectionKey={key}
                  config={config?.[key]}
                  fields={fields[key]?.fields || []}
                  onSave={handleSave}
                  onTest={handleTest}
                />
              )}
            </TabsContent>
          ))}
          
          <TabsContent value="rgpd" className="mt-6">
            <RGPDTab />
          </TabsContent>
          
          <TabsContent value="maintenance" className="mt-6">
            <MaintenanceSection />
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default SystemConfigPage;
