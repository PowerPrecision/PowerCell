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

const WorkflowStatusesPage = ({ embedded = false }) => {
  const { user } = useAuth();
  const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;

  // Verificar permissões
  if (!hasAnyRole(user, ["admin", "ceo"])) {
    return wrapLayout(
      <Card className="border-red-200 bg-red-50">
        <CardContent className="p-8 text-center">
          <Settings className="h-12 w-12 mx-auto mb-4 text-red-500" />
          <h2 className="text-xl font-semibold mb-2">Acesso Negado</h2>
          <p className="text-muted-foreground">
            Não tem permissão para aceder a esta página.
          </p>
        </CardContent>
      </Card>
    );
  }

  return wrapLayout(
    <div className="space-y-4 md:space-y-6">
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
  );
};

export default WorkflowStatusesPage;
