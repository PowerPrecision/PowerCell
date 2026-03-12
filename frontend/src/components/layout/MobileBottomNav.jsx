/**
 * MobileBottomNav - Navegação inferior para mobile
 * Mostra apenas em ecrãs pequenos (< md breakpoint)
 */
import { Link, useLocation } from "react-router-dom";
import { LayoutGrid, Users, Calendar, User } from "lucide-react";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";

const MobileBottomNav = () => {
  const location = useLocation();
  const { user } = useAuth();
  
  // Determinar o dashboard correcto baseado no role
  const getDashboardPath = () => {
    if (!user) return "/dashboard";
    if (user.role === "admin" || user.role === "ceo" || user.role === "administrativo") {
      return "/admin";
    }
    return "/staff";
  };

  // Determinar o caminho correcto para clientes baseado no role
  // Consultores e intermediários vão para "Os Meus Clientes"
  // Admin e outros vão para a lista geral de clientes
  const getClientsPath = () => {
    if (!user) return "/clientes";
    if (["consultor", "intermediario", "mediador"].includes(user.role)) {
      return "/meus-clientes";
    }
    return "/clientes";
  };

  const navItems = [
    { path: getDashboardPath(), icon: LayoutGrid, label: "Kanban" },
    { path: getClientsPath(), icon: Users, label: "Clientes" },
    { path: "/leads", icon: Calendar, label: "Visitas" },
    { path: "/definicoes", icon: User, label: "Perfil" },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 md:hidden bg-background border-t safe-area-pb">
      <div className="flex items-center justify-around h-16">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path || 
                          location.pathname.startsWith(item.path + "/");
          
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "flex flex-col items-center justify-center w-full h-full",
                "transition-colors duration-200",
                "touch-manipulation",
                isActive 
                  ? "text-teal-600 dark:text-teal-400" 
                  : "text-muted-foreground hover:text-foreground"
              )}
              data-testid={`mobile-nav-${item.label.toLowerCase()}`}
            >
              <item.icon className={cn(
                "h-5 w-5 mb-1",
                isActive && "scale-110"
              )} />
              <span className="text-xs font-medium">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
};

export default MobileBottomNav;
