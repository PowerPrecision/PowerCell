/**
 * ContextSwitcher — Selector de perfil activo para utilizadores com múltiplos papéis (Context Switcher de Perfis).
 *
 * PORQUÊ: Utilizadores com additional_roles (ex: um consultor que é também mediador) precisam de alternar
 * entre perfis sem fazer re-login. Este componente exibe os papéis disponíveis e permite o switch,
 * actualizando o activeRole em AuthContext e sessionStorage. Renderiza null silenciosamente se o
 * utilizador não tiver papéis adicionais.
 *
 * @context {AuthContext} — Consome user, effectiveRole, switchActiveRole
 *
 * @example
 * // No header da aplicação
 * <ContextSwitcher />
 * // Mostra dropdown apenas se user.additional_roles.length > 0
 */
import React from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "../ui/dropdown-menu";
import { ChevronDown, Shield } from "lucide-react";

const roleLabels = {
  consultor: "Consultor",
  mediador: "Mediador",
  intermediario: "Intermediário",
  consultor_intermediario: "Consultor/Intermediário",
  indexacao: "Indexação",
  administrativo: "Administrativo",
  diretor: "Diretor",
  ceo: "CEO",
  admin: "Administrador",
};

const roleIcons = {
  consultor: "💼",
  mediador: "🤝",
  intermediario: "🤝",
  consultor_intermediario: "💼🤝",
  indexacao: "📋",
  administrativo: "📁",
  diretor: "👔",
  ceo: "⭐",
  admin: "🛡️",
};

const ContextSwitcher = () => {
  const { user, effectiveRole, switchActiveRole } = useAuth();

  // Only show if user has additional roles
  const additionalRoles = user?.additional_roles || [];
  if (!additionalRoles.length) return null;

  // Build list of all available roles (primary + additional, no duplicates)
  const allRoles = [user.role, ...additionalRoles.filter(r => r !== user.role)];

  const currentLabel = roleLabels[effectiveRole] || effectiveRole;
  const currentIcon = roleIcons[effectiveRole] || "👤";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 h-8 text-xs font-medium border-primary/30 hover:bg-primary/5 transition-colors"
          title={`Modo atual: ${currentLabel}. Clique para trocar.`}
        >
          <Shield className="h-3.5 w-3.5 text-primary" />
          <span className="hidden sm:inline">{currentLabel}</span>
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="text-xs font-semibold text-muted-foreground">
          Modo de Operação
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {allRoles.map((role) => {
          const isActive = role === effectiveRole;
          const label = roleLabels[role] || role;
          const icon = roleIcons[role] || "👤";
          return (
            <DropdownMenuItem
              key={role}
              onClick={() => switchActiveRole(role)}
              className={`gap-2 cursor-pointer ${isActive ? "bg-primary/10 font-semibold" : ""}`}
            >
              <span className="text-base">{icon}</span>
              <span className="flex-1">{label}</span>
              {isActive && (
                <span className="text-[10px] px-1.5 py-0.5 bg-primary text-primary-foreground rounded-full font-bold">
                  ATIVO
                </span>
              )}
              {role === user.role && role !== effectiveRole && (
                <span className="text-[10px] text-muted-foreground">Principal</span>
              )}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default ContextSwitcher;
