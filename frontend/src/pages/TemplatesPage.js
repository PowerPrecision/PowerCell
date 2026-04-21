/**
 * TemplatesPage — Página de Destinatários e Templates de Email.
 *
 * Envolve o TemplatesPanel dentro do DashboardLayout para funcionar
 * como rota standalone acessível via sidebar.
 */
import React from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import TemplatesPanel from "../components/TemplatesPanel";

const TemplatesPage = () => {
  return (
    <DashboardLayout title="Destinatários">
      <TemplatesPanel />
    </DashboardLayout>
  );
};

export default TemplatesPage;
