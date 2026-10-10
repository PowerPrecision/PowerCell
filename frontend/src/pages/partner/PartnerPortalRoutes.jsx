/**
 * A árvore de rotas do Portal do Parceiro (`/parceiro/*`).
 *
 * UM chunk lazy: o código do parceiro não vai no pacote principal do CRM, e
 * o do CRM não é carregado por um parceiro que abre o link do convite.
 * (Um ponto de entrada Vite SEPARADO — e um subdomínio — seria o passo
 * seguinte: nem os nomes das páginas de administração chegariam ao
 * browser de um utilizador externo.)
 *
 * As rotas são relativas a `/parceiro`. A área reservada vive debaixo do
 * `PartnerShell`, que guarda a porta; o login e o convite ficam de fora.
 */
import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { PartnerAuthProvider } from "@/contexts/PartnerAuthContext";
import PartnerAccountPage from "@/pages/partner/PartnerAccountPage";
import PartnerCasePage from "@/pages/partner/PartnerCasePage";
import PartnerDashboardPage from "@/pages/partner/PartnerDashboardPage";
import PartnerInvitePage from "@/pages/partner/PartnerInvitePage";
import PartnerLeadPage from "@/pages/partner/PartnerLeadPage";
import PartnerLoginPage from "@/pages/partner/PartnerLoginPage";
import PartnerShell from "@/pages/partner/PartnerShell";

export default function PartnerPortalRoutes() {
  return (
    <PartnerAuthProvider>
      <Routes>
        <Route path="entrar" element={<PartnerLoginPage />} />
        <Route path="convite/:token" element={<PartnerInvitePage />} />
        <Route element={<PartnerShell />}>
          <Route index element={<PartnerDashboardPage />} />
          <Route path="novo-lead" element={<PartnerLeadPage />} />
          <Route path="casos/:caseId" element={<PartnerCasePage />} />
          <Route path="conta" element={<PartnerAccountPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/parceiro" replace />} />
      </Routes>
    </PartnerAuthProvider>
  );
}
