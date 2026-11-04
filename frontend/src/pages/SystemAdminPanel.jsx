/**
 * SystemAdminPanel — «Administração»: o ÚNICO painel de administração.
 *
 * REVISÃO DO PAINEL (Flavio, Nov 2026)
 * ====================================
 * Antes havia três ecrãs com o mesmo nome (`/admin`, `/admin/organizacao` e este),
 * Empresas e Utilizadores repetidos e definições globais misturadas com as da
 * empresa. Agora é um painel em cinco grupos — Equipa, A empresa, Operação,
 * Conformidade e Sistema — e cada definição aparece num só sítio. O registo dos
 * grupos, das secções e de quem vê cada uma está em `utils/painelAdminGrupos.js`.
 *
 * * O grupo e a secção vivem no URL (`?grupo=&seccao=`): sobrevivem a um refresh e
 *   partilham-se. Links antigos (`?tab=` e `/admin/organizacao`) são traduzidos.
 * * Decide-se pelo PERFIL EFECTIVO (o do seletor), nunca pelo `user.role`; a conta
 *   Master vê tudo (como o servidor, `conta_master_passa`).
 * * Divulgação progressiva: primeiro escolhe-se o grupo, depois a secção.
 *
 * @route /system-admin
 */
import { lazy, Suspense, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useAuth } from "../contexts/AuthContext";
import { isMaster as eContaMaster } from "../utils/roleUtils";
import {
  DESTINOS_ANTIGOS,
  gruposVisiveis,
  seccaoEmVigor,
} from "../utils/painelAdminGrupos";
import { nomeDaEmpresaActiva } from "../utils/painelAdminAmbitos";
import { Building2, Cog, ShieldCheck, Users, Workflow } from "lucide-react";

import UsersAccessAdminTab from "../components/admin/UsersAccessAdminTab";
import CompaniesAdminTab from "../components/admin/CompaniesAdminTab";
import PartnersAdminTab from "../components/admin/PartnersAdminTab";
import PermissionsTab from "../components/admin/PermissionsTab";
import HistoryTrackingPanel from "../components/admin/HistoryTrackingPanel";
import RgpdAnonimizacaoPanel from "../components/admin/RgpdAnonimizacaoPanel";
import WorkflowSoLeitura from "../components/admin/WorkflowSoLeitura";
import AutomationPage from "./AutomationPage";

// PACOTE AZ: páginas pesadas em lazy (dependências circulares do bundle do Vite).
const SystemConfigPage = lazy(() => import("./SystemConfigPage"));
const WorkflowStatusesPage = lazy(() => import("./WorkflowStatusesPage"));
const FormManagementPage = lazy(() => import("./FormManagementPage"));
const TemplatesPage = lazy(() => import("./TemplatesPage"));
const EmailAccountsPage = lazy(() => import("./EmailAccountsPage"));
const NotificationSettingsPage = lazy(() => import("./NotificationSettingsPage"));
const RGPDAdminPage = lazy(() => import("./RGPDAdminPage"));
const AuditTrailPage = lazy(() => import("./AuditTrailPage"));
const BackupsPage = lazy(() => import("./BackupsPage"));
const UnifiedLogsPage = lazy(() => import("./UnifiedLogsPage"));
const DiagnosticsPage = lazy(() => import("./DiagnosticsPage"));
const AIConfigPage = lazy(() => import("./AIConfigPage"));
const BackgroundJobsPage = lazy(() => import("./BackgroundJobsPage"));
const FinanceTab = lazy(() => import("../components/admin/FinanceTab"));

const ICONES_DOS_GRUPOS = {
  equipa: Users,
  empresa: Building2,
  operacao: Workflow,
  conformidade: ShieldCheck,
  sistema: Cog,
};

const TabLoader = () => (
  <div className="flex items-center justify-center py-12">
    <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
);

/** O conteúdo de cada secção. `soLeitura` é o acesso «consulta» (Diretor). */
function ConteudoDaSeccao({ id, soLeitura, contaMaster }) {
  const lazyPage = (Pagina, props = {}) => (
    <Suspense fallback={<TabLoader />}>
      <Pagina embedded {...props} />
    </Suspense>
  );
  switch (id) {
    case "utilizadores":
      return <UsersAccessAdminTab isMaster={contaMaster} soLeitura={soLeitura} />;
    case "parceiros":
      return <PartnersAdminTab isMaster={contaMaster} />;
    case "permissoes":
      return <PermissionsTab />;
    case "dados":
      return <CompaniesAdminTab isMaster={contaMaster} />;
    case "definicoes":
      return lazyPage(SystemConfigPage, { ambito: "empresa" });
    case "financas":
      return (
        <Suspense fallback={<TabLoader />}>
          <FinanceTab soLeitura={soLeitura} podeGravarGlobal={contaMaster} />
        </Suspense>
      );
    case "workflow":
      return soLeitura ? <WorkflowSoLeitura /> : lazyPage(WorkflowStatusesPage);
    case "formulario":
      return lazyPage(FormManagementPage);
    case "automacoes":
      return <AutomationPage embedded />;
    case "minutas":
      return lazyPage(TemplatesPage);
    case "rgpd":
      return lazyPage(RGPDAdminPage);
    case "auditoria":
      return lazyPage(AuditTrailPage);
    case "anonimizacao":
      return <RgpdAnonimizacaoPanel isMaster={contaMaster} />;
    case "historico":
      return <HistoryTrackingPanel />;
    case "configuracao":
      return lazyPage(SystemConfigPage, { ambito: "sistema" });
    case "contas-email":
      return lazyPage(EmailAccountsPage);
    case "notificacoes":
      return lazyPage(NotificationSettingsPage);
    case "backups":
      return lazyPage(BackupsPage);
    case "logs":
      return lazyPage(UnifiedLogsPage);
    case "diagnosticos":
      return lazyPage(DiagnosticsPage);
    case "ia":
      return lazyPage(AIConfigPage);
    case "processos-bg":
      return lazyPage(BackgroundJobsPage);
    default:
      return null;
  }
}

const SystemAdminPanel = () => {
  const { user, effectiveRole, activeCompanyId } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const contaMaster = eContaMaster(user);
  const grupos = useMemo(
    () => gruposVisiveis({ perfil: effectiveRole || user?.role, contaMaster }),
    [effectiveRole, user?.role, contaMaster],
  );

  // Links antigos (`?tab=` do painel antigo e de `/admin/organizacao`).
  const antigo = DESTINOS_ANTIGOS[searchParams.get("tab")];
  const grupoPedido = searchParams.get("grupo") || antigo?.grupo;
  const seccaoPedida = searchParams.get("seccao") || antigo?.seccao;
  const { grupo, seccao } = seccaoEmVigor(grupos, grupoPedido, seccaoPedida);

  useEffect(() => {
    if (!antigo) return;
    const novo = new URLSearchParams(searchParams);
    novo.delete("tab");
    novo.set("grupo", antigo.grupo);
    novo.set("seccao", antigo.seccao);
    setSearchParams(novo, { replace: true });
  }, [antigo, searchParams, setSearchParams]);

  const irPara = (grupoId, seccaoId) => {
    // `tab` é o sub-separador de algumas secções (Definições): não passa de uma para outra.
    setSearchParams(seccaoId ? { grupo: grupoId, seccao: seccaoId } : { grupo: grupoId }, { replace: true });
  };

  const nomeDaEmpresa = nomeDaEmpresaActiva(user, activeCompanyId);

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="system-admin-panel">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Administração</h1>
          <p className="text-muted-foreground">
            {nomeDaEmpresa
              ? `A configurar: ${nomeDaEmpresa}. Muda a empresa no seletor do topo.`
              : "Escolha o que quer configurar."}
          </p>
        </div>

        {!grupo ? (
          <p className="rounded-md border border-border bg-muted/40 px-3 py-6 text-center text-sm text-muted-foreground" data-testid="painel-sem-acesso">
            O seu perfil não tem nada para configurar aqui.
          </p>
        ) : (
          <>
            {/* 1.º passo — o grupo (divulgação progressiva) */}
            <nav
              aria-label="Grupos da administração"
              className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5"
              data-testid="grupos-do-painel"
            >
              {grupos.map((g) => {
                const Icone = ICONES_DOS_GRUPOS[g.id] || Cog;
                const activo = g.id === grupo.id;
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => irPara(g.id)}
                    aria-current={activo ? "page" : undefined}
                    data-testid={`grupo-${g.id}`}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors ${
                      activo
                        ? "border-primary bg-primary/10 font-semibold text-foreground"
                        : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    <Icone className={`h-4 w-4 shrink-0 ${activo ? "text-primary" : ""}`} />
                    <span className="truncate">{g.rotulo}</span>
                  </button>
                );
              })}
            </nav>

            <p
              className={`rounded-md border px-3 py-2 text-xs ${
                grupo.id === "sistema"
                  ? "border-destructive/40 bg-destructive/10 text-foreground"
                  : "border-border bg-muted/40 text-muted-foreground"
              }`}
              data-testid="descricao-do-grupo"
            >
              <strong>{grupo.rotulo}</strong> — {grupo.descricao}
            </p>

            {/* 2.º passo — a secção */}
            <Tabs value={seccao.id} onValueChange={(v) => irPara(grupo.id, v)}>
              <div className="w-full overflow-x-auto -mx-1 px-1">
                <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
                  {grupo.seccoes.map((s) => (
                    <TabsTrigger
                      key={s.id}
                      value={s.id}
                      className="text-xs sm:text-sm whitespace-nowrap"
                      data-testid={`seccao-${s.id}`}
                    >
                      {s.rotulo}
                      {s.acesso === "consulta" && (
                        <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">(consulta)</span>
                      )}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </div>
              <TabsContent value={seccao.id} className="mt-4">
                {seccao.acesso === "consulta" && (
                  <p className="mb-3 text-xs text-muted-foreground" data-testid="aviso-so-consulta">
                    Só consulta: o seu perfil vê, mas não altera.
                  </p>
                )}
                <ConteudoDaSeccao id={seccao.id} soLeitura={seccao.acesso === "consulta"} contaMaster={contaMaster} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </DashboardLayout>
  );
};

export default SystemAdminPanel;
