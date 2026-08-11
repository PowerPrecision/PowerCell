/**
 * DocumentsTab — extraído de ProcessDetails.js (tab documents).
 * Painel de gestão de documentos do processo + pedidos do portal.
 * Inclui o bloco de Resumo Executivo IA (atualmente desativado via feature flag,
 * mantido para reativação futura — ver comentário original).
 */
import { Card, CardContent } from "../../ui/card";
import { Button } from "../../ui/button";
import UnifiedDocumentsPanel from "../../UnifiedDocumentsPanel";
import PortalDocumentRequests from "../../PortalDocumentRequests";
import { FolderOpen, BrainCircuit, Sparkles, Loader2, RefreshCw } from "lucide-react";
import { safeFormat } from "../../../lib/utils";
import { pt } from "date-fns/locale";

export default function DocumentsTab({
  hasAnyRole,
  user,
  aiSummary,
  aiAnalysisLoading,
  aiAnalysisDate,
  handleAiAnalysis,
  renderAiSummary,
  documentsRefreshKey,
  id,
  process,
  handleAIDataExtractedFromDocs,
  setDocumentsRefreshKey,
}) {
  return (
    <div className="space-y-4">
      {/* Header com info — só visível para admin e CEO */}
      {hasAnyRole(user, ["admin", "ceo"]) && (
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-amber-100 dark:bg-amber-900/40 rounded-lg">
            <FolderOpen className="h-6 w-6 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 className="font-semibold text-amber-800 dark:text-amber-200">Gestão de Documentos</h3>
            <p className="text-sm text-amber-600 dark:text-amber-400">
              Faça upload de ficheiros ou adicione links externos (Google Drive, OneDrive, etc.)
            </p>
          </div>
        </div>
      </div>
      )}

      {/* PACOTE DB — AI Executive Summary temporariamente oculto (display: none).
          O Card é mantido para reativação futura — não apagar.
          Originalmente: só visível para admin e CEO. */}
      {/* eslint-disable-next-line no-constant-binary-expression -- feature flag off until AI summary is re-enabled */}
      {hasAnyRole(user, ["admin", "ceo"]) && false && (
      <Card className="border-indigo-200 dark:border-indigo-800 bg-gradient-to-r from-indigo-50/50 to-purple-50/50 dark:from-indigo-900/10 dark:to-purple-900/10" style={{ display: 'none' }}>
        <CardContent className="pt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-100 dark:bg-indigo-900/40 rounded-lg">
                <BrainCircuit className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-indigo-800 dark:text-indigo-200">Resumo Executivo IA</h3>
                <p className="text-xs text-indigo-600 dark:text-indigo-400">
                  Auditoria cruzada entre dados declarados e documentos
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {aiAnalysisDate && (
                <span className="text-xs text-muted-foreground hidden sm:inline">
                  {safeFormat(aiAnalysisDate, "dd/MM/yyyy HH:mm", { locale: pt })}
                </span>
              )}
              {aiSummary && !aiAnalysisLoading ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleAiAnalysis(true)}
                  className="border-indigo-300 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-700 dark:text-indigo-300"
                >
                  <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                  Atualizar
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => handleAiAnalysis(true)}
                  disabled={aiAnalysisLoading}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {aiAnalysisLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      A cruzar dados e a ler documentos...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                      {aiSummary ? "Atualizar Análise IA" : "Analisar IA (Auditoria)"}
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>

          {/* Loading state */}
          {aiAnalysisLoading && (
            <div className="mt-4 flex items-center gap-3 p-4 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <p className="text-sm text-indigo-700 dark:text-indigo-300">
                A IA está a cruzar os dados do formulário com os documentos extraídos...
              </p>
            </div>
          )}

          {/* Summary result */}
          {aiSummary && !aiAnalysisLoading && (
            <div className="mt-4 p-4 bg-white dark:bg-gray-900 border rounded-lg max-h-[600px] overflow-y-auto">
              <div className="prose prose-sm dark:prose-invert max-w-none">
                {renderAiSummary(aiSummary)}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {/* Painel de Documentos Unificado */}
      <Card className="border-amber-200 dark:border-amber-800">
        <CardContent className="pt-6">
          <UnifiedDocumentsPanel
            key={documentsRefreshKey}
            processId={id}
            clientName={process?.client_name}
            onAIDataExtracted={handleAIDataExtractedFromDocs}
          />
        </CardContent>
      </Card>

      {/* Pedidos de Documentos do Portal */}
      <PortalDocumentRequests
        processId={id}
        onDocumentsChange={() => setDocumentsRefreshKey(k => k + 1)}
      />
    </div>
  );
}
