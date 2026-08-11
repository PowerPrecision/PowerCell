/**
 * TemplatesPage — Página de Destinatários e Templates de Email.
 *
 * Envolve o TemplatesPanel dentro do DashboardLayout para funcionar
 * como rota standalone acessível via sidebar.
 */
import DashboardLayout from "../layouts/DashboardLayout";
import TemplatesPanel from "../components/TemplatesPanel";

const TemplatesPage = ({ embedded = false }) => {
  const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;
  return wrapLayout(
    <TemplatesPanel />
  );
};

export default TemplatesPage;
