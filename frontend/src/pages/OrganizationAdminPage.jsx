/**
 * OrganizationAdminPage — Painel de Administração base (Pacote DW).
 *
 * Gestão de Empresas e de acessos UCR (User-Company-Role).
 * Visível e acessível apenas quando o perfil activo é admin ou ceo.
 *
 * @route /admin/organizacao
 */
import { Navigate } from "react-router-dom";
import { Building2, Users } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import PageHeader from "../components/shared/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useAuth } from "../contexts/AuthContext";
import { canAccessOrgAdmin } from "../utils/roleUtils";
import CompaniesAdminTab from "../components/admin/CompaniesAdminTab";
import UsersAccessAdminTab from "../components/admin/UsersAccessAdminTab";

export default function OrganizationAdminPage() {
  const { effectiveRole } = useAuth();

  if (!canAccessOrgAdmin(effectiveRole)) {
    return <Navigate to="/staff" replace />;
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="organization-admin-page">
        <PageHeader
          icon={Building2}
          title="Administração"
          description="Gestão de empresas do grupo e acessos multi-perfil (UCR)."
        />

        <Tabs defaultValue="empresas" className="w-full">
          <TabsList data-testid="org-admin-tabs">
            <TabsTrigger value="empresas" className="gap-1.5" data-testid="tab-empresas">
              <Building2 className="h-4 w-4" />
              Empresas
            </TabsTrigger>
            <TabsTrigger value="utilizadores" className="gap-1.5" data-testid="tab-utilizadores">
              <Users className="h-4 w-4" />
              Utilizadores
            </TabsTrigger>
          </TabsList>
          <TabsContent value="empresas" className="mt-4">
            <CompaniesAdminTab />
          </TabsContent>
          <TabsContent value="utilizadores" className="mt-4">
            <UsersAccessAdminTab />
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
