/**
 * OrganizationAdminPage — Painel de Administração base (Pacote DW).
 *
 * Gestão de Empresas, contas de utilizadores, acessos UCR (User-Company-Role) e parceiros.
 * Visível e acessível apenas quando o perfil activo é admin ou ceo.
 *
 * @route /admin/organizacao
 *
 * Nota: `/admin` permanece o dashboard operacional (KPIs/funil). Esta página
 * é a Área de Administração (Empresas + Utilizadores/UCR), visível na Sidebar
 * só quando o perfil activo é admin ou ceo.
 */
import { Navigate, useSearchParams } from "react-router-dom";
import { Building2, Handshake, Users } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import PageHeader from "../components/shared/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useAuth } from "../contexts/AuthContext";
import { canAccessOrgAdmin } from "../utils/roleUtils";
import CompaniesAdminTab from "../components/admin/CompaniesAdminTab";
import UsersAccessAdminTab from "../components/admin/UsersAccessAdminTab";
import PartnersAdminTab from "../components/admin/PartnersAdminTab";

export default function OrganizationAdminPage() {
  const { effectiveRole } = useAuth();
  const [searchParams] = useSearchParams();
  const separador = searchParams.get("tab");
  const defaultTab = separador === "utilizadores" ? "acessos" : separador === "parceiros" ? "parceiros" : "empresas";

  if (!canAccessOrgAdmin(effectiveRole)) {
    return <Navigate to="/staff" replace />;
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="organization-admin-page">
        <PageHeader
          icon={Building2}
          title="Administração"
          description="Gestão de empresas do grupo, contas de utilizadores e acessos multi-perfil (UCR)."
        />

        <Tabs defaultValue={defaultTab} className="w-full">
          <TabsList data-testid="org-admin-tabs">
            <TabsTrigger value="empresas" className="gap-1.5" data-testid="tab-empresas">
              <Building2 className="h-4 w-4" />
              Empresas
            </TabsTrigger>
            <TabsTrigger value="acessos" className="gap-1.5" data-testid="tab-acessos">
              <Users className="h-4 w-4" />
              Utilizadores
            </TabsTrigger>
            <TabsTrigger value="parceiros" className="gap-1.5" data-testid="tab-parceiros">
              <Handshake className="h-4 w-4" />
              Parceiros
            </TabsTrigger>
          </TabsList>
          <TabsContent value="empresas" className="mt-4">
            <CompaniesAdminTab isMaster={effectiveRole === "master"} />
          </TabsContent>
          <TabsContent value="acessos" className="mt-4">
            <UsersAccessAdminTab isMaster={effectiveRole === "master"} />
          </TabsContent>
          <TabsContent value="parceiros" className="mt-4">
            <PartnersAdminTab />
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
