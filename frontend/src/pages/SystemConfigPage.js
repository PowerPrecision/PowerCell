/**
 * SystemConfigPage — Página de configurações do sistema, exclusiva para Admin/CEO.
 *
 * PORQUÊ: O PowerCell tem múltiplas integrações externas (AWS S3, OpenAI, Gmail,
 * envio de emails) que precisam de configuração centralizada. Esta página
 * permite ao administrador configurar credenciais, activar/desactivar funcionalidades
 * e executar tarefas de manutenção sem aceder directamente ao backend ou a variáveis
 * de ambiente. Inclui ferramentas de diagnóstico (reparação de índices, limpeza de logs)
 * e sincronização entre ambientes de produção e desenvolvimento.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Configuração dinâmica: os campos são definidos pelo backend via /api/system-config,
 * permitindo adicionar novas secções sem alterar o frontend.
 * - Secção de manutenção incluída como tab separada com ferramentas de DB, migrações
 * e mapeamento S3.
 * - DocumentRecipientsManager integrado como tab para gestão visual de destinatários
 * de documentação bancária.
 * - Protecção de passwords: campos do tipo "password" são mascarados com reveal sob
 * demanda (endpoint /reveal-secrets).
 * - Acesso restrito a roles admin e ceo — redireciona com mensagem clara para outros.
 *
 * @context {AuthContext} — Consome token, user para verificar permissões de acesso
 *
 * @route /admin/config — Página acessível apenas a admin/ceo
 *
 * @example
 * <SystemConfigPage />
 * // Acesso via rota protegida: /admin/config?tab=storage
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
// Tabs removed — replaced with vertical master-detail layout
import DocumentRecipientsManager from "../components/DocumentRecipientsManager";
import MaintenanceSection from "./systemConfig/MaintenanceSection";
import IntegrationsConfigSection from "./systemConfig/IntegrationsConfigSection";
import SystemEmailsSection from "./systemConfig/SystemEmailsSection";
import { ConfigSection, SECTION_ICONS, getSectionNavLabel } from "./systemConfig/configFormHelpers";
import PortalSettingsSection from "./systemConfig/PortalSettingsSection";
import MandatoryDocumentsSection from "./systemConfig/MandatoryDocumentsSection";
import ChangelogSection from "./systemConfig/ChangelogSection";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { hasAnyRole } from "../utils/roleUtils";
import { toast } from "sonner";
import {
  Settings,
  XCircle,
  RefreshCw,
  Wrench,
  FileEdit,
  MessageSquare,
  Megaphone,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const SystemConfigPage = ({ embedded = false }) => {
  const { token, user, effectiveCompanyId } = useAuth();
  const [searchParams] = useSearchParams();
  const [config, setConfig] = useState(null);
  const [fields, setFields] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(() => searchParams.get("tab") || "storage");

  // MULTI-EMPRESA: a empresa activa vem do selector global (ContextSwitcher
  // no header principal), não deve existir um segundo selector aqui — só
  // reagimos à empresa activa escolhida globalmente.
  const selectedCompanyId = effectiveCompanyId || "default";

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/system-config?company_id=${encodeURIComponent(selectedCompanyId)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        // Converter arrays para string separada por vírgulas em campos de texto
        if (data.config?.auto_draft?.eligible_doc_types != null) {
          const docTypes = data.config.auto_draft.eligible_doc_types;
          data.config.auto_draft.eligible_doc_types = Array.isArray(docTypes)
            ? docTypes.join(", ")
            : String(docTypes);
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
  }, [token, selectedCompanyId]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // Recarregar config quando a empresa activa (global) mudar — ignora a
  // primeira execução (montagem) para não sobrepor o tab pedido via ?tab=
  const previousCompanyIdRef = useRef(selectedCompanyId);
  useEffect(() => {
    if (previousCompanyIdRef.current === selectedCompanyId) return;
    previousCompanyIdRef.current = selectedCompanyId;
    setLoading(true);
    setActiveTab("settings");
    fetchConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCompanyId]);

  const handleSave = async (section, data) => {
    // Pré-processar campos especiais
    const processedData = { ...data };
    if (section === "auto_draft" && typeof processedData.eligible_doc_types === "string") {
      const trimmed = processedData.eligible_doc_types.trim();
      if (!trimmed) {
        processedData.eligible_doc_types = [];
      } else {
        // Parsear string separada por vírgulas em array
        processedData.eligible_doc_types = trimmed
          .split(',')
          .map(s => s.trim())
          .filter(Boolean);
      }
    }
    // Pré-processar audit_trail: critical_fields (textarea → lista) e retention_days (string → int)
    if (section === "audit_trail") {
      if (typeof processedData.critical_fields === "string") {
        const trimmed = processedData.critical_fields.trim();
        if (!trimmed) {
          processedData.critical_fields = ["financial_data", "credit_data", "status"];
        } else {
          try {
            const parsed = JSON.parse(trimmed);
            processedData.critical_fields = Array.isArray(parsed) ? parsed : ["financial_data", "credit_data", "status"];
          } catch {
            processedData.critical_fields = ["financial_data", "credit_data", "status"];
          }
        }
      }
      if (typeof processedData.retention_days === "string") {
        const val = parseInt(processedData.retention_days, 10);
        processedData.retention_days = isNaN(val) ? 365 : val;
      }
    }

    const response = await fetch(`${API_URL}/api/system-config/${section}?company_id=${encodeURIComponent(selectedCompanyId)}`, {
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
    const loadingContent = (
      <div className="space-y-6">
        <div className="h-7 w-64 bg-muted animate-pulse rounded" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />)}
        </div>
      </div>
    );
    return embedded ? loadingContent : <DashboardLayout>{loadingContent}</DashboardLayout>;
  }
  if (!hasAnyRole(user, ["admin", "ceo"])) {
    const accessDeniedContent = (
      <div className="text-center py-12">
        <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold">Acesso Restrito</h2>
        <p className="text-muted-foreground">
          Apenas administradores podem aceder às configurações do sistema.
        </p>
      </div>
    );
    return embedded ? accessDeniedContent : <DashboardLayout>{accessDeniedContent}</DashboardLayout>;
  }

  const sections = Object.keys(fields).filter(key => key !== "email");


  const pageContent = (
    <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Settings className="h-6 w-6" />
              Configurações do Sistema
            </h1>
            <p className="text-muted-foreground">
              Configure as integrações e definições da aplicação
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* O seletor de empresa vive apenas no header global principal
                (ContextSwitcher) — esta página apenas reage à empresa activa. */}
            <Button variant="outline" onClick={fetchConfig}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Recarregar
            </Button>
          </div>
        </div>

        {/* Vertical Master-Detail Layout */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* ─── Left: Sidebar Navigation (Desktop) / Dropdown+Chips (Mobile) ─── */}
          <aside className="w-full lg:w-64 xl:w-72 shrink-0">
            {/* Desktop: Vertical sidebar */}
            <div className="hidden lg:block sticky top-20">
              <Card className="py-2">
                <CardContent className="p-2">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-2 mb-2">Categorias</p>
                  <nav className="space-y-1">
                    {sections.map((key) => {
                      const Icon = SECTION_ICONS[key] || Settings;
                      const isActive = activeTab === key;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setActiveTab(key)}
                          className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                            isActive
                              ? "bg-primary/10 text-primary font-medium"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground"
                          }`}
                        >
                          <Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-primary" : ""}`} />
                          <span className="truncate">{getSectionNavLabel(key, fields)}</span>
                          {isActive && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                        </button>
                      );
                    })}
                    <div className="my-1.5 border-t border-border" />
                    {/* Nota: "RGPD" foi removido daqui — vive apenas no tab Compliance do Painel de Administração (evita duplicação).
                        "Integrações" e "Emails Sistema" foram movidos para o tab Comunicações no Painel de Administração */}
                    <button
                      type="button"
                      onClick={() => setActiveTab("maintenance")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "maintenance"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Wrench className={`h-4 w-4 shrink-0 ${activeTab === "maintenance" ? "text-primary" : ""}`} />
                      <span className="truncate">Manutenção</span>
                      {activeTab === "maintenance" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("portal")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "portal"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <MessageSquare className={`h-4 w-4 shrink-0 ${activeTab === "portal" ? "text-primary" : ""}`} />
                      <span className="truncate">Portal</span>
                      {activeTab === "portal" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("mandatory_documents")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "mandatory_documents"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <FileEdit className={`h-4 w-4 shrink-0 ${activeTab === "mandatory_documents" ? "text-primary" : ""}`} />
                      <span className="truncate">Docs Obrigatórios</span>
                      {activeTab === "mandatory_documents" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("changelog")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "changelog"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Megaphone className={`h-4 w-4 shrink-0 ${activeTab === "changelog" ? "text-primary" : ""}`} />
                      <span className="truncate">Atualizações</span>
                      {activeTab === "changelog" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                  </nav>
                </CardContent>
              </Card>
              <p className="text-xs text-muted-foreground/60 px-1 mt-2">Cada categoria guarda as suas definições independentemente.</p>
            </div>

            {/* Mobile: Dropdown + Chips */}
            <div className="lg:hidden space-y-3">
              <Select value={activeTab} onValueChange={setActiveTab}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Selecionar categoria" />
                </SelectTrigger>
                <SelectContent>
                  {sections.map((key) => {
                    const Icon = SECTION_ICONS[key] || Settings;
                    return (
                      <SelectItem key={key} value={key}>
                        <span className="flex items-center gap-2">
                          <Icon className="h-4 w-4" />
                          {getSectionNavLabel(key, fields)}
                        </span>
                      </SelectItem>
                    );
                  })}
                  {/* Nota: RGPD removido (vive só em Compliance); Integrações e Emails Sistema movidos para Comunicações */}
                  <SelectItem value="maintenance">
                    <span className="flex items-center gap-2">
                      <Wrench className="h-4 w-4" />
                      Manutenção
                    </span>
                  </SelectItem>
                  <SelectItem value="portal">
                    <span className="flex items-center gap-2">
                      <MessageSquare className="h-4 w-4" />
                      Portal
                    </span>
                  </SelectItem>
                  <SelectItem value="mandatory_documents">
                    <span className="flex items-center gap-2">
                      <FileEdit className="h-4 w-4" />
                      Docs Obrigatórios
                    </span>
                  </SelectItem>
                  <SelectItem value="changelog">
                    <span className="flex items-center gap-2">
                      <Megaphone className="h-4 w-4" />
                      Atualizações
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
              {/* Horizontal scrollable chips for quick access */}
              <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1" style={{scrollbarWidth: "none", msOverflowStyle: "none"}}>
                {sections.map((key) => {
                  const Icon = SECTION_ICONS[key] || Settings;
                  const isActive = activeTab === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setActiveTab(key)}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all shrink-0 ${
                        isActive
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-muted text-muted-foreground hover:border-muted-foreground/50"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {getSectionNavLabel(key, fields)}
                    </button>
                  );
                })}
                {["maintenance", "portal", "mandatory_documents", "changelog"].map((key) => {
                  const Icon = key === "portal" ? MessageSquare : key === "mandatory_documents" ? FileEdit : key === "changelog" ? Megaphone : Wrench;
                  const isActive = activeTab === key;
                  const label = key === "portal" ? "Portal" : key === "mandatory_documents" ? "Docs Obrigatórios" : key === "changelog" ? "Atualizações" : "Manutenção";
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setActiveTab(key)}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all shrink-0 ${
                        isActive
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-muted text-muted-foreground hover:border-muted-foreground/50"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>

          {/* ─── Right: Content Area ─── */}
          <main className="min-w-0 flex-1">
            {activeTab === "document_recipients" && <DocumentRecipientsManager token={token} user={user} />}
            {activeTab === "integrations" && <IntegrationsConfigSection />}
            {activeTab === "system_emails" && <SystemEmailsSection token={token} />}
            {activeTab === "portal" && <PortalSettingsSection token={token} />}
            {activeTab === "mandatory_documents" && <MandatoryDocumentsSection token={token} />}
            {activeTab !== "document_recipients" && activeTab !== "maintenance" && activeTab !== "integrations" && activeTab !== "system_emails" && activeTab !== "portal" && activeTab !== "mandatory_documents" && activeTab !== "changelog" && (
              <ConfigSection
                section={fields[activeTab]}
                sectionKey={activeTab}
                config={config?.[activeTab]}
                fields={fields[activeTab]?.fields || []}
                onSave={handleSave}
                onTest={handleTest}
              />
            )}
            {activeTab === "maintenance" && <MaintenanceSection token={token} user={user} />}
            {activeTab === "changelog" && <ChangelogSection token={token} />}
          </main>
        </div>
      </div>
  );

  return embedded ? pageContent : <DashboardLayout>{pageContent}</DashboardLayout>;
};

export default SystemConfigPage;

// Named exports para uso no SystemAdminPanel (tab Comunicações)
export { default as IntegrationsConfigSection } from "./systemConfig/IntegrationsConfigSection";
export { default as SystemEmailsSection } from "./systemConfig/SystemEmailsSection";
