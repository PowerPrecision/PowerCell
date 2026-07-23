/**
 * ChangelogSection — changelog/anúncios do sistema.
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { safeString } from "../../utils/safeString";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { formatDateTime } from "../../lib/utils";
import { sanitizeHtml } from "../../utils/sanitize";
import { toast } from "sonner";
import { getSystemChangelogs, generateChangelogAI, diagnoseChangelog, createAnnouncement } from "../../services/api";
import {
  Sparkles,
  Loader2,
  Megaphone,
} from "lucide-react";

function markdownToHtml(md) {
  if (!md || typeof md !== 'string') return '';
  let html = md
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n\n/g, '</p><p class="mb-2">')
    .replace(/\n/g, '<br/>');
  html = `<p class="mb-2">${html}</p>`;
  html = html.replace(/<p class="mb-2"><\/p>/g, '');
  return html;
}

export default function ChangelogSection() {
  const [changelogs, setChangelogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosticResult, setDiagnosticResult] = useState(null);
  // CORREÇÃO (Pacote AE-fix): default 'worklog' em vez de 'git' porque
  // no Render a pasta .git não está disponível no container de deploy.
  // worklog.md é um ficheiro físico que está sempre presente.
  const [sourceType, setSourceType] = useState("worklog");

  const fetchChangelogs = useCallback(async () => {
    try {
      const res = await getSystemChangelogs(10);
      setChangelogs(res.data || []);
    } catch (err) {
      console.error("Erro ao carregar changelogs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchChangelogs(); }, [fetchChangelogs]);

  // ── Diagnóstico (Pacote AI): verifica ficheiros + credenciais IA ──
  const handleDiagnose = async () => {
    setDiagnosing(true);
    setDiagnosticResult(null);
    try {
      const res = await diagnoseChangelog();
      setDiagnosticResult(res.data);
      if (res.data?.can_generate) {
        toast.success("Diagnóstico: tudo OK! Pode gerar notas de atualização.");
      } else {
        toast.warning(res.data?.blocking_issue || "Problema detetado — veja o relatório abaixo.");
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, "Erro ao executar diagnóstico"));
    } finally {
      setDiagnosing(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await generateChangelogAI({ source_type: sourceType });
      toast.success("Notas de atualização geradas com sucesso!");
      // Adicionar o novo changelog ao início da lista
      if (res.data?.changelog) {
        setChangelogs(prev => [res.data.changelog, ...prev]);
      } else {
        fetchChangelogs(); // Refresh da lista
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, "Erro ao gerar notas de atualização"));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">📢 Mural de Atualizações (IA)</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Gere notas de lançamento amigáveis a partir de logs técnicos. A IA transforma o trabalho da equipa em anúncios claros para todos os utilizadores.
        </p>
      </div>

      {/* ── Gerar novo changelog ── */}
      <Card className="border-primary/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Gerar Notas de Atualização
          </CardTitle>
          <CardDescription className="text-xs">
            A IA analisa os commits/changes recentes e redige um anúncio de lançamento amigável
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Label className="text-xs mb-1.5 block">Fonte de dados</Label>
              <Select value={sourceType} onValueChange={setSourceType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="worklog">Ficheiro worklog.md (recomendado)</SelectItem>
                  <SelectItem value="changelog_file">Ficheiro CHANGELOG.md</SelectItem>
                  <SelectItem value="git">Commits Git (pode falhar no Render)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button onClick={handleGenerate} disabled={generating} className="gap-2">
                {generating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    A gerar...
                  </>
                ) : (
                  <>
                    ✨ Gerar Notas de Atualização (IA)
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={handleDiagnose} disabled={diagnosing} className="gap-2" title="Diagnosticar problemas">
                {diagnosing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    A diagnosticar...
                  </>
                ) : (
                  <>
                    🔍 Diagnosticar
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* ── Resultado do diagnóstico (Pacote AI) ── */}
          {diagnosticResult && (
            <div className={`mt-4 p-4 rounded-lg border ${diagnosticResult.can_generate ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
              <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                {diagnosticResult.can_generate ? "✅" : "⚠️"} Relatório de Diagnóstico
              </h4>
              {diagnosticResult.blocking_issue && (
                <p className="text-xs text-amber-700 mb-3 font-medium">{diagnosticResult.blocking_issue}</p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {/* Ficheiros */}
                <div className="bg-white/60 p-3 rounded">
                  <p className="font-medium mb-1">Ficheiros de Fonte</p>
                  <p>worklog.md local: {diagnosticResult.checks?.files?.worklog_md_local_exists ? "✅" : "❌"} {diagnosticResult.checks?.files?.worklog_md_local_path || "(não encontrado)"}</p>
                  <p>worklog.md legível: {diagnosticResult.checks?.files?.worklog_md_readable ? "✅" : "❌"}</p>
                  <p>CHANGELOG.md local: {diagnosticResult.checks?.files?.changelog_md_local_exists ? "✅" : "❌"} {diagnosticResult.checks?.files?.changelog_md_local_path || "(não encontrado)"}</p>
                  <p>CHANGELOG.md legível: {diagnosticResult.checks?.files?.changelog_md_readable ? "✅" : "❌"}</p>
                  {diagnosticResult.checks?.files?.worklog_md_sample && (
                    <p className="text-muted-foreground mt-1 truncate">Sample: {diagnosticResult.checks.files.worklog_md_sample}</p>
                  )}
                </div>
                {/* Credenciais IA */}
                <div className="bg-white/60 p-3 rounded">
                  <p className="font-medium mb-1">Credenciais de IA</p>
                  <p>Configuradas: {diagnosticResult.checks?.ai_credentials?.configured ? "✅" : "❌"}</p>
                  <p>Modelo: {diagnosticResult.checks?.ai_credentials?.model || "N/A"}</p>
                  <p>OPENAI_API_KEY env: {diagnosticResult.checks?.ai_credentials?.has_openai_env_key ? "✅" : "❌"}</p>
                  <p>EMERGENT_LLM_KEY env: {diagnosticResult.checks?.ai_credentials?.has_emergent_env_key ? "✅" : "❌"}</p>
                  {diagnosticResult.checks?.ai_credentials?.error && (
                    <p className="text-red-600 mt-1">Erro: {diagnosticResult.checks.ai_credentials.error}</p>
                  )}
                </div>
                {/* Git */}
                <div className="bg-white/60 p-3 rounded">
                  <p className="font-medium mb-1">Git Log</p>
                  <p>Disponível: {diagnosticResult.checks?.git?.available ? "✅" : "❌"}</p>
                  {diagnosticResult.checks?.git?.sample && (
                    <p className="text-muted-foreground mt-1 truncate">Sample: {diagnosticResult.checks.git.sample}</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Lista de changelogs ── */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : changelogs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Megaphone className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-muted-foreground">Nenhuma atualização publicada ainda.</p>
            <p className="text-xs text-muted-foreground mt-1">Clique no botão acima para gerar a primeira nota de atualização com IA.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {changelogs.map((entry) => (
            <Card key={entry.id} className="overflow-hidden">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Badge variant="outline" className="text-xs px-2 py-0.5">
                      v{safeString(entry.version)}
                    </Badge>
                    {entry.generated_by === "ai" && (
                      <Badge className="text-[10px] bg-primary/10 text-primary border-primary/20" variant="outline">
                        ✨ IA
                      </Badge>
                    )}
                  </CardTitle>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(entry.published_at)}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <div
                  className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed changelog-content"
                  dangerouslySetInnerHTML={{
                    __html: sanitizeHtml(markdownToHtml(entry.content_markdown))
                  }}
                />
                {/* PACOTE AW: Botão Publicar no Mural da Equipa */}
                <div className="mt-4 pt-3 border-t flex items-center justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 text-primary border-primary/30 hover:bg-primary/5"
                    onClick={async () => {
                      try {
                        await createAnnouncement({
                          content: entry.content_markdown,
                          title: `Notas de Atualização v${safeString(entry.version)}`,
                        });
                        toast.success("Nota publicada no mural da equipa!");
                      } catch (err) {
                        toast.error(extractErrorMessage(err, "Erro ao publicar no mural."));
                      }
                    }}
                  >
                    <Megaphone className="h-3.5 w-3.5" />
                    Publicar no Mural da Equipa
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

