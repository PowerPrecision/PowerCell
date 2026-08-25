/**
 * Shared config field/section UI for SystemConfigPage dynamic tabs.
 */
import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import { Switch } from "../../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import RichTextEditor from "../../components/ui/RichTextEditor";
import { safeString } from "../../utils/safeString";
import { toast } from "sonner";
import {
  Settings,
  Cloud,
  Mail,
  Sparkles,
  Building,
  Building2,
  Save,
  Loader2,
  CheckCircle,
  XCircle,
  TestTube,
  Eye,
  EyeOff,
  Wrench,
  FileEdit,
  FileSignature,
  MailCheck,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

/** Ícones por secção dinâmica do system-config. */
export const SECTION_ICONS = {
  storage: Cloud,
  email: Mail,
  ai: Sparkles,
  settings: Building,
  maintenance: Wrench,
  document_recipients: Building2,
  auto_draft: FileEdit,
  rgpd: FileSignature,
  company_email: Building2,
  shared_email: MailCheck,
};

/**
 * Labels curtos para a navegação lateral do system-config.
 *
 * Por defeito a navegação mostra apenas a primeira palavra do título da
 * secção (`title.split(" ")[0]`) para caber no espaço compacto. Algumas
 * secções precisam de um rótulo mais descritivo do que essa primeira
 * palavra — por exemplo "document_recipients" (título completo
 * "Destinatários de Documentação") ficava truncado para "Destinatários",
 * que não deixa claro que se trata do envio de documentação para
 * balcões/bancos. Este mapa permite sobrepor esse truncamento por secção.
 */
export const SECTION_LABELS = {
  document_recipients: "Envio para Balcões",
};

/** Obtém o rótulo a mostrar na navegação lateral para uma secção. */
export const getSectionNavLabel = (key, fields) =>
  SECTION_LABELS[key] || fields[key]?.title?.split(" ")[0] || key;

export const ConfigFieldInput = ({ field, value, onChange, allValues, sectionName }) => {
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
        <h4 className="font-medium text-sm text-muted-foreground">{safeString(field.label)}</h4>
      </div>
    );
  }

  const inputType = field.type === "password" && !showPassword ? "password" : "text";

  switch (field.type) {
    case "select":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
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
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    case "boolean":
      return (
        <div className="flex items-center justify-between py-2">
          <div>
            <Label htmlFor={field.key}>{safeString(field.label)}</Label>
            {field.help_text && (
              <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
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
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
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
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    case "number":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <Input
            id={field.key}
            type="number"
            value={value || ""}
            onChange={(e) => onChange(field.key, parseInt(e.target.value) || "")}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    case "textarea":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <RichTextEditor
            value={value || ""}
            onChange={(val) => onChange(field.key, val)}
            placeholder={field.placeholder}
            advanced
            minHeight={200}
            className="min-h-[200px]"
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    default:
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <Input
            id={field.key}
            type="text"
            value={value || ""}
            onChange={(e) => onChange(field.key, e.target.value)}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );
  }
};

// Componente para secção de configuração
export const ConfigSection = ({ section, sectionKey, config, fields, onSave, onTest }) => {
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
    // Snapshot dos dados efectivamente enviados neste guardar. Só fechamos
    // o estado de "alterações por guardar" (isDirty) se o utilizador não
    // tiver editado mais nada enquanto o pedido estava em curso — caso
    // contrário, essa edição posterior ficaria incorretamente marcada como
    // guardada e a mensagem desapareceria sem os dados terem sido persistidos.
    const submittedConfig = localConfig;
    try {
      await onSave(sectionKey, submittedConfig);
      setLocalConfig((current) => {
        if (current === submittedConfig) {
          setHasChanges(false);
        }
        return current;
      });
      toast.success("Configuração guardada", { id: "config-save" });
    } catch {
      toast.error("Erro ao guardar", { id: "config-save" });
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
    } catch {
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
              <CardTitle className="text-lg">{safeString(section.title)}</CardTitle>
              <CardDescription>{safeString(section.description)}</CardDescription>
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

          {["storage", "email", "ai"].includes(sectionKey) && (
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

