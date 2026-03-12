import DashboardLayout from "../layouts/DashboardLayout";
import LeadsKanban from "../components/LeadsKanban";

export default function LeadsPage() {
  return (
    <DashboardLayout>
      <LeadsKanban />
    </DashboardLayout>
  );
}
