/**
 * LeadsPage — Página de gestão de leads/prospetos do CRM.
 *
 * PORQUÊ: Gestão do funil de entrada, permitindo acompanhar conversões, atribuir leads a
 * consultores, e acompanhar o pipeline comercial desde o primeiro contacto até à conversão.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import DashboardLayout from "../layouts/DashboardLayout";
import LeadsKanban from "../components/LeadsKanban";

export default function LeadsPage() {
  return (
    <DashboardLayout>
      <LeadsKanban />
    </DashboardLayout>
  );
}

