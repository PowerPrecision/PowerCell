/**
 * RGPDTab — editor do template de consentimento RGPD (SystemConfig).
 *
 * Extraído de SystemConfigPage.js (tab "rgpd"): edição do texto legal,
 * pré-visualização com variáveis e histórico de versões.
 */
import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../../components/ui/dialog";
import { hasAnyRole } from "../../utils/roleUtils";
import { safeString } from "../../utils/safeString";
import { formatDateTime } from "../../lib/utils";
import { toast } from "sonner";
import {
  Loader2,
  Info,
  FileEdit,
  RotateCcw,
  History,
  RefreshCw,
  Save,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function RGPDTab({ token, user }) {
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
  
  const isAdminOrCEO = hasAnyRole(user, ["admin", "ceo"]);

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
        toast.success(`Template RGPD guardado (v${data.version || ""})`, { id: "rgpd-save" });
        setOriginalContent(templateContent);
        setChangelog("");
        fetchTemplate();
        fetchVersions();
      } else if (response.status === 403) {
        toast.error("Apenas Admin ou CEO podem editar o template");
      } else {
        toast.error("Erro ao guardar o template");
      }
    } catch {
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
    } catch {
      toast.error("Erro ao restaurar o template padrão");
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = templateContent !== originalContent;

  // Insert a variable at the current textarea cursor position
  const insertVariable = (variableKey) => {
    const textarea = document.querySelector('.rgpd-editor-textarea');
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const before = templateContent.substring(0, start);
      const after = templateContent.substring(end);
      const insertion = `{{${variableKey}}}`;
      setTemplateContent(before + insertion + after);
      // Restore cursor position after React re-render
      requestAnimationFrame(() => {
        textarea.selectionStart = textarea.selectionEnd = start + insertion.length;
        textarea.focus();
      });
    } else {
      // Fallback: append at end
      setTemplateContent((prev) => prev + `{{${variableKey}}}`);
    }
  };

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
                  : `Versão ${safeString(templateMeta.version) || "1.0"} — Última atualização: ${
                      templateMeta.updated_at
                        ? formatDateTime(templateMeta.updated_at)
                        : "N/A"
                    } ${templateMeta.updated_by ? `por ${safeString(templateMeta.updated_by)}` : ""}`}
              </span>
            </div>
            {templateMeta.is_default ? (
              <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                Template Padrão
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                v{safeString(templateMeta.version) || "1.0"}
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
          {/* Variable chips — click to insert at cursor position */}
          {isAdminOrCEO && (
            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground font-medium">
                Clique numa variável para inserir no texto:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { key: "NOME_CLIENTE", label: "Nome Cliente" },
                  { key: "NOME", label: "Nome" },
                  { key: "NOME_EMPRESA", label: "Empresa" },
                  { key: "MORADA_EMPRESA", label: "Morada Empresa" },
                  { key: "CONTACTO_EMPRESA", label: "Contacto Empresa" },
                  { key: "CONTRIBUINTE", label: "NIF" },
                  { key: "MORADA", label: "Morada" },
                  { key: "LOCALIDADE", label: "Localidade" },
                  { key: "CODIGO_POSTAL", label: "C. Postal" },
                  { key: "TIPO_DOCUMENTO", label: "Tipo Doc." },
                  { key: "NUMERO_DOCUMENTO", label: "Nº Doc." },
                  { key: "VALIDADE_DOCUMENTO", label: "Validade" },
                  { key: "DATA_ASSINATURA", label: "Data Assinatura" },
                ].map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => insertVariable(key)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border bg-muted/40 hover:bg-muted text-xs font-mono text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Textarea editor — plain text, no WYSIWYG corruption of {{variables}} */}
          <textarea
            value={safeString(templateContent)}
            onChange={(e) => setTemplateContent(e.target.value)}
            disabled={!isAdminOrCEO}
            placeholder="Introduza o texto do template RGPD... Use {{NOME_CLIENTE}} para variáveis dinâmicas."
            spellCheck={false}
            className="rgpd-editor-textarea w-full rounded-lg border border-input bg-background p-4 font-mono text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 text-foreground placeholder:text-muted-foreground"
            style={{ minHeight: "380px" }}
          />
          {isAdminOrCEO && (
            <p className="text-[11px] text-muted-foreground">
              Use as variáveis acima para personalizar o documento. Não edite as chavetas {'{{ }}'} manualmente — use os botões.
            </p>
          )}

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

        </CardContent>
      </Card>

      {/* RGPD Preview Dialog - outside Card to avoid layout interference */}
      <Dialog open={showRgpdPreview} onOpenChange={setShowRgpdPreview}>
        <DialogContent className="sm:max-w-[700px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Pré-visualização RGPD</DialogTitle>
            <DialogDescription>
              Visualização do texto tal como o cliente final o verá
            </DialogDescription>
          </DialogHeader>
          <div className="prose prose-sm max-w-none bg-white dark:bg-gray-900 border rounded-lg p-6 overflow-y-auto max-h-[70vh] break-words"
            dangerouslySetInnerHTML={{
              __html: (() => {
                // 1. Escape HTML first to prevent unclosed tags from leaking
                let safe = (templateContent || "")
                  .replace(/&/g, '&amp;')
                  .replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;');
                // 2. Replace variables with styled example spans
                safe = safe
                  .replace(/\{\{NOME_CLIENTE\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">João Silva</span>')
                  .replace(/\{\{NOME_EMPRESA\}\}/g, '<span class="bg-amber-100 dark:bg-amber-900/60 px-1.5 py-0.5 rounded font-medium text-amber-800 dark:text-amber-200">Power Real Estate</span>')
                  .replace(/\{\{CONTRIBUINTE\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">123456789</span>')
                  .replace(/\{\{MORADA\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Rua Example, 123, Lisboa</span>')
                  .replace(/\{\{LOCALIDADE\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Lisboa</span>')
                  .replace(/\{\{CODIGO_POSTAL\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">1000-001</span>')
                  .replace(/\{\{TIPO_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Cartão de Cidadão</span>')
                  .replace(/\{\{NUMERO_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">CC 00000000</span>')
                  .replace(/\{\{VALIDADE_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">01/01/2030</span>')
                  .replace(/\{\{DATA_ASSINATURA\}\}/g, '<span class="bg-green-100 dark:bg-green-900/60 px-1.5 py-0.5 rounded font-medium text-green-800 dark:text-green-200">' + new Date().toLocaleDateString("pt-PT") + '</span>')
                  .replace(/\{\{NOME\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">João Silva</span>')
                  .replace(/\{\{MORADA_EMPRESA\}\}/g, '<span class="bg-amber-100 dark:bg-amber-900/60 px-1.5 py-0.5 rounded font-medium text-amber-800 dark:text-amber-200">Rua da Empresa, 1, Lisboa</span>')
                  .replace(/\{\{CONTACTO_EMPRESA\}\}/g, '<span class="bg-amber-100 dark:bg-amber-900/60 px-1.5 py-0.5 rounded font-medium text-amber-800 dark:text-amber-200">info@empresa.pt / 210000000</span>');
                // 3. Convert newlines
                safe = safe.replace(/\n/g, '<br/>');
                return safe;
              })()
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRgpdPreview(false)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
                        Versão {safeString(v.version)}
                        {v.is_active && (
                          <Badge variant="outline" className="ml-2 text-xs bg-green-100 text-green-700 border-green-300">
                            Ativa
                          </Badge>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {v.created_at
                          ? formatDateTime(v.created_at)
                          : "N/A"}
                        {v.created_by ? ` — ${safeString(v.created_by)}` : ""}
                      </p>
                      {v.changelog && (
                        <p className="text-xs text-muted-foreground italic mt-0.5">
                          {safeString(v.changelog)}
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
}

