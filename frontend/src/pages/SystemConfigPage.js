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
import SlaThresholdsSection from "./systemConfig/SlaThresholdsSection";
import EmpresaConfigSelector from "./systemConfig/EmpresaConfigSelector";
import { getSystemConfigCompanies } from "../services/api";
import {
  deveMostrarSeletorDeEmpresa,
  empresaEmVigor,
  normalizarEmpresas,
} from "../utils/empresaDeConfiguracao";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { hasAnyRole, hasRole } from "../utils/roleUtils";
import { toast } from "sonner";
import {
  Settings,
  XCircle,
  RefreshCw,
  Wrench,
  FileEdit,
  MessageSquare,
  Gauge,
  Megaphone,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Separadores com ecrã PRÓPRIO — ponto único.
 *
 * Isto era uma lista de EXCLUSÃO no render (`activeTab !== "a" && activeTab
 * !== "b" && …`) ao lado de um `activeTab === "a" &&` por secção: a mesma
 * informação em dois sítios, que divergem sem dar erro. Acrescentei o
 * `dashboard_slas` só no lado positivo e o cartão genérico passou a
 * renderizar-se A PAR dele, com `section` a `undefined` — `section.title`
 * rebenta e a página fica em branco.
 *
 * Com um registo, um separador é dedicado OU genérico, nunca os dois, e
 * acrescentar um obriga a decidir. Todas recebem `token` e `user`: as que não
 * os usam ignoram-nos, e uniformizar evita um terceiro sítio com a lista de
 * quem precisa de quê.
 */
export const SECCOES_DEDICADAS = {
  document_recipients: DocumentRecipientsManager,
  maintenance: MaintenanceSection,
  integrations: IntegrationsConfigSection,
  system_emails: SystemEmailsSection,
  portal: PortalSettingsSection,
  mandatory_documents: MandatoryDocumentsSection,
  changelog: ChangelogSection,
  dashboard_slas: SlaThresholdsSection,
};

/**
 * As secções com ecrã próprio que aparecem na NAVEGAÇÃO, por ordem.
 *
 * PORQUE É QUE ISTO EXISTE (Lote 6, ponto 1)
 * ==========================================
 * A navegação desta página estava escrita À MÃO em TRÊS sítios: a barra
 * lateral (`hidden lg:block`), o `<Select>` do telemóvel e a fila de chips
 * ao lado dele (`lg:hidden`). Ao acrescentar os Limiares de SLA pus o
 * botão só na barra lateral — e num ecrã estreito o separador deixava
 * simplesmente de EXISTIR. Não é um problema de overflow: a fila de chips
 * já tem `overflow-x-auto`, e um item que não é renderizado não se alcança
 * com scroll nenhum.
 *
 * É a mesma forma do defeito que corrigi no dia anterior neste mesmo
 * ficheiro (o cartão genérico a renderizar-se a par do dedicado, por a
 * decisão estar escrita duas vezes) e a regra que eu próprio escrevi em
 * `FRONTEND_GUIDELINES.md` § 27.9. Uma lista repetida três vezes divergirá
 * numa delas, e a que divergir não dá erro: fica um separador invisível.
 *
 * As três navs derivam agora desta lista. Acrescentar uma secção é
 * acrescentar uma linha aqui; esquecer uma nav deixou de ser possível.
 *
 * `SECCOES_DEDICADAS` continua a ser a autoridade sobre QUAL o componente
 * (inclui entradas que não são separadores próprios, como
 * `document_recipients`); esta lista diz quais se OFERECEM e com que
 * rótulo. Há um teste a afirmar que toda a chave daqui existe lá.
 */
export const SECCOES_NA_NAVEGACAO_COMPLETAS = [
  { key: "maintenance", label: "Manutenção", Icon: Wrench },
  { key: "portal", label: "Portal", Icon: MessageSquare },
  { key: "mandatory_documents", label: "Docs Obrigatórios", Icon: FileEdit },
  { key: "changelog", label: "Atualizações", Icon: Megaphone },
  { key: "dashboard_slas", label: "Limiares de SLA", Icon: Gauge },
];

/**
 * O que cada perfil vê na navegação — ponto único.
 *
 * TODAS as secções com ecrã próprio lêem e escrevem a configuração GLOBAL
 * (limiares de SLA, documentos obrigatórios, integrações, emails do sistema,
 * manutenção…), que é infraestrutura partilhada e **exclusiva do
 * administrador**. O CEO só configura a(s) sua(s) empresa(s), nas secções
 * genéricas. Mostrar-lhe as dedicadas daria um ecrã de erros 403.
 */
export const seccoesDaNavegacao = (isAdmin) =>
  isAdmin ? SECCOES_NA_NAVEGACAO_COMPLETAS : [];

/** Compatibilidade: a lista completa (o que o administrador vê). */
export const SECCOES_NA_NAVEGACAO = SECCOES_NA_NAVEGACAO_COMPLETAS;

const SystemConfigPage = ({ embedded = false }) => {
  const { token, user, effectiveCompanyId } = useAuth();
  const [searchParams] = useSearchParams();
  const [config, setConfig] = useState(null);
  const [fields, setFields] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(() => searchParams.get("tab") || "storage");

  // MULTI-EMPRESA: por omissão reagimos à empresa activa do selector global
  // (ContextSwitcher). Mas esse selector só lista os UCR de quem pergunta, e
  // o ADMIN configura TODAS as empresas do CRM: a lista abaixo vem do
  // servidor, já filtrada pelo âmbito (admin: todas; CEO: as dele), e só há
  // selector quando tem mais do que uma. Ver `utils/empresaDeConfiguracao`.
  const [empresas, setEmpresas] = useState([]);
  const [listaPronta, setListaPronta] = useState(false);
  const [empresaEscolhida, setEmpresaEscolhida] = useState(null);
  const selectedCompanyId = empresaEmVigor({
    escolhida: empresaEscolhida,
    activa: effectiveCompanyId,
    empresas,
  });

  useEffect(() => {
    let cancelado = false;
    getSystemConfigCompanies()
      .then((res) => {
        if (!cancelado) setEmpresas(normalizarEmpresas(res?.data));
      })
      // Sem lista, o servidor continua a ser a parede: cai no comportamento
      // de sempre (a empresa activa) em vez de bloquear o ecrã.
      .catch((error) => console.warn("Lista de empresas indisponível:", error))
      .finally(() => {
        if (!cancelado) setListaPronta(true);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  // Trocar a empresa activa no cabeçalho global anula a escolha local.
  useEffect(() => {
    setEmpresaEscolhida(null);
  }, [effectiveCompanyId]);

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

  // Só pede depois de saber que empresas se oferecem: um CEO de uma ilha
  // não tem a global, e abrir o ecrã a pedi-la daria um 403 e um toast.
  useEffect(() => {
    if (listaPronta) fetchConfig();
  }, [fetchConfig, listaPronta]);

  // Recarregar config quando a empresa mostrada mudar — ignora a primeira
  // execução (montagem) para não sobrepor o tab pedido via ?tab=
  const previousCompanyIdRef = useRef(null);
  useEffect(() => {
    if (!listaPronta) return;
    if (previousCompanyIdRef.current === null) {
      previousCompanyIdRef.current = selectedCompanyId;
      return;
    }
    if (previousCompanyIdRef.current === selectedCompanyId) return;
    previousCompanyIdRef.current = selectedCompanyId;
    setLoading(true);
    setActiveTab("settings");
    fetchConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCompanyId, listaPronta]);

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
  // Qual secção o separador activo pede. Deriva do registo — ver
  // `SECCOES_DEDICADAS`: é o que garante que nunca se renderizam as duas.
  // A configuração GLOBAL é exclusiva do administrador: o CEO só vê as secções
  // genéricas da(s) sua(s) empresa(s). Um `?tab=` antigo que aponte para uma
  // dedicada diz-se, em vez de abrir um ecrã de erros 403.
  const isAdmin = hasRole(user, "admin");
  const navegacao = seccoesDaNavegacao(isAdmin);
  const SeccaoDedicada = isAdmin ? SECCOES_DEDICADAS[activeTab] : undefined;
  const seccaoReservada = !isAdmin && Boolean(SECCOES_DEDICADAS[activeTab]);


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
            {deveMostrarSeletorDeEmpresa(empresas) && (
              <EmpresaConfigSelector
                empresas={empresas}
                valor={selectedCompanyId}
                onChange={setEmpresaEscolhida}
              />
            )}
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
                    {navegacao.map(({ key, label, Icon }) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setActiveTab(key)}
                        className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                          activeTab === key
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground"
                        }`}
                        data-testid={`nav-${key.replace(/_/g, "-")}`}
                      >
                        <Icon className={`h-4 w-4 shrink-0 ${activeTab === key ? "text-primary" : ""}`} />
                        <span className="truncate">{label}</span>
                        {activeTab === key && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                      </button>
                    ))}
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
                  {navegacao.map(({ key, label, Icon }) => (
                    <SelectItem key={key} value={key}>
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4" />
                        {label}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* Chips de acesso rápido.
                  `flex-wrap` e NÃO `overflow-x-auto`: a versão anterior
                  rolava na horizontal com a barra de rolagem ESCONDIDA
                  (`scrollbarWidth: none`) — num telemóvel não havia nada a
                  indicar que havia mais separadores à direita, e num rato
                  sem scroll horizontal não havia forma de lá chegar. A
                  quebra de linha mostra todos, em qualquer largura, e não
                  precisa de afordância nenhuma. */}
              <div className="flex flex-wrap gap-2 pb-1">
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
                {navegacao.map(({ key, label, Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setActiveTab(key)}
                    className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all shrink-0 ${
                      activeTab === key
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-muted text-muted-foreground hover:border-muted-foreground/50"
                    }`}
                    data-testid={`chip-${key.replace(/_/g, "-")}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {/* ─── Right: Content Area ─── */}
          <main className="min-w-0 flex-1">
            {SeccaoDedicada ? <SeccaoDedicada token={token} user={user} /> : null}
            {!SeccaoDedicada && fields[activeTab] && (
              <ConfigSection
                section={fields[activeTab]}
                sectionKey={activeTab}
                companyId={selectedCompanyId}
                config={config?.[activeTab]}
                fields={fields[activeTab]?.fields || []}
                onSave={handleSave}
                onTest={handleTest}
              />
            )}
            {/* Um separador desconhecido (um `?tab=` antigo num favorito) não
                é dedicado nem tem campos: DIZ-SE, em vez de deixar a área de
                conteúdo vazia sem explicação. */}
            {seccaoReservada && (
              <Card data-testid="config-seccao-reservada">
                <CardContent className="py-12 text-center space-y-2">
                  <p className="font-medium">Secção reservada ao administrador</p>
                  <p className="text-sm text-muted-foreground">
                    Esta definição é global (partilhada por todas as empresas). Como CEO,
                    configura as definições da sua empresa nas restantes categorias.
                  </p>
                </CardContent>
              </Card>
            )}
            {!SeccaoDedicada && !seccaoReservada && !fields[activeTab] && !loading && (
              <Card data-testid="config-seccao-desconhecida">
                <CardContent className="py-12 text-center space-y-2">
                  <p className="font-medium">Secção desconhecida</p>
                  <p className="text-sm text-muted-foreground">
                    O separador &quot;{activeTab}&quot; não existe nesta configuração.
                    Escolha um da lista ao lado.
                  </p>
                </CardContent>
              </Card>
            )}
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
