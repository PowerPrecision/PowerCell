/**
 * ====================================================================
 * PÁGINA DE GESTÃO DE ESTADOS DO WORKFLOW - POWERCELL
 * ====================================================================
 * Página dedicada para gerir os estados do workflow do sistema.
 * Acesso: Admin e CEO
 * ====================================================================
 */

import { useAuth } from "../contexts/AuthContext";
import { hasAnyRole } from "../utils/roleUtils";
import DashboardLayout from "../layouts/DashboardLayout";
import WorkflowEditor from "../components/WorkflowEditor";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Settings } from "lucide-react";

const WorkflowStatusesPage = () => {
  const { user } = useAuth();

  // Verificar permissões
  if (!hasAnyRole(user, ["admin", "ceo"])) {
    return (
      <DashboardLayout title="Acesso Negado">
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-8 text-center">
            <Settings className="h-12 w-12 mx-auto mb-4 text-red-500" />
            <h2 className="text-xl font-semibold mb-2">Acesso Negado</h2>
            <p className="text-muted-foreground">
              Não tem permissão para aceder a esta página.
            </p>
          </CardContent>
        </Card>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Estados do Workflow">
      <div className="space-y-4 md:space-y-6 p-4 md:p-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5 text-purple-500" />
              Gestão de Estados do Workflow
            </CardTitle>
            <CardDescription>
              Configure os estados do workflow que aparecem no Kanban e nos processos.
              Arraste para reordenar, clique para editar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <WorkflowEditor />
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default WorkflowStatusesPage;
