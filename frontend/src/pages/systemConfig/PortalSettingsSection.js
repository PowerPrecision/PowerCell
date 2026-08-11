/**
 * PortalSettingsSection — textos/settings do portal do cliente.
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import { Textarea } from "../../components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../../components/ui/dialog";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { formatDateTime } from "../../lib/utils";
import { toast } from "sonner";
import {
  Save,
  Loader2,
  Eye,
  Info,
  RotateCcw,
  MessageSquare,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;



// =====================================================================
// PORTAL SETTINGS SECTION — Configuração do Portal do Cliente
// =====================================================================

export default function PortalSettingsSection({ token }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [template, setTemplate] = useState("");
  const [preview, setPreview] = useState("");
  const [showPreview, setShowPreview] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setTemplate(data.welcome_message_template || "");
      } else {
        toast.error("Erro ao carregar definições do portal");
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ welcome_message_template: template }),
      });
      if (res.ok) {
        toast.success("Mensagem de boas-vindas guardada");
        fetchSettings();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, "Erro ao guardar"));
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings/preview`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ welcome_message_template: template }),
      });
      if (res.ok) {
        const data = await res.json();
        setPreview(data.preview);
        setShowPreview(true);
      }
    } catch {
      toast.error("Erro ao gerar pré-visualização");
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Repor a mensagem de boas-vindas para o padrão? As alterações serão perdidas.")) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings/reset-welcome`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTemplate(data.welcome_message_template);
        toast.success("Template reposto para o padrão");
      }
    } catch {
      toast.error("Erro ao repor template");
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="ml-2 text-muted-foreground">A carregar definições do portal...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <MessageSquare className="h-5 w-5 text-primary" />
            Portal do Cliente
          </CardTitle>
          <CardDescription>
            Configure a mensagem de boas-vindas que os clientes veem no chat do portal.
            Use variáveis para personalizar automaticamente o conteúdo.
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Welcome Message Editor */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mensagem de Boas-Vindas</CardTitle>
          <CardDescription>
            Esta mensagem aparece como a primeira mensagem no chat do portal do cliente.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Variables Help */}
          <div className="rounded-lg border bg-muted/30 p-4">
            <p className="text-sm font-medium mb-2 flex items-center gap-1.5">
              <Info className="h-4 w-4 text-primary" />
              Variáveis disponíveis
            </p>
            <div className="flex flex-wrap gap-2">
              {settings?.available_variables?.map((v) => (
                <Badge key={v.key} variant="outline" className="font-mono text-xs">
                  {v.key} <span className="font-sans text-muted-foreground ml-1">— {v.description}</span>
                </Badge>
              ))}
            </div>
          </div>

          {/* Template Textarea */}
          <div className="space-y-2">
            <Label htmlFor="welcome-template">Template da mensagem</Label>
            <Textarea
              id="welcome-template"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              rows={14}
              className="font-mono text-sm leading-relaxed resize-y"
              placeholder="Escreva a mensagem de boas-vindas..."
            />
            <p className="text-xs text-muted-foreground">
              {template.length} caracteres
              {template.length > 2000 && " — recomendamos mensagens com menos de 2000 caracteres"}
            </p>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={handleSave} disabled={saving || !template.trim()} className="gap-2">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Guardar
            </Button>
            <Button variant="outline" onClick={handlePreview} disabled={!template.trim()} className="gap-2">
              <Eye className="h-4 w-4" />
              Pré-visualizar
            </Button>
            <Button variant="outline" onClick={handleReset} className="gap-2">
              <RotateCcw className="h-4 w-4" />
              Repor padrão
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Preview Dialog */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-primary" />
              Pré-visualização
            </DialogTitle>
            <DialogDescription>
              Como a mensagem vai aparecer para o cliente "João Silva" com o consultor "Ana Rodrigues"
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border bg-gray-50 p-4 max-h-80 overflow-y-auto">
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-2xl px-4 py-2.5 bg-white border border-gray-200 shadow-sm">
                <p className="text-xs font-semibold text-gray-600 mb-0.5">PowerCell</p>
                <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{preview}</p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPreview(false)}>Fechar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Last updated */}
      {settings?.updated_at && (
        <p className="text-xs text-muted-foreground text-right">
          Última atualização: {formatDateTime(settings.updated_at)}
        </p>
      )}
    </div>
  );
}

