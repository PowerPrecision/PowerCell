/**
 * ContextSwitcher — Selector de perfil activo e empresa activa.
 *
 * PORQUÊ: Utilizadores com additional_roles ou múltiplas empresas precisam de
 * alternar entre contextos sem fazer re-login. Este componente mostra:
 *   1. Selector de Empresa (se associado a múltiplas empresas)
 *   2. Selector de Perfil/Role (se tem additional_roles)
 *
 * A alternância de empresa atualiza:
 *   - O header X-Company-Id enviado em todos os pedidos API
 *   - O brand theme (visual) da aplicação
 *   - O backend marca a empresa como is_default
 *
 * A alternância de role atualiza:
 *   - O header X-Active-Role enviado em todos os pedidos API
 *   - A filtragem de dados no backend
 *
 * @context {AuthContext} — Consome user, effectiveRole, switchActiveRole,
 *          activeCompanyId, switchActiveCompany, effectiveCompanyId
 *
 * @example
 * <ContextSwitcher />
 * // Mostra dropdown de empresa + role se aplicável
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
import { ChevronDown, Shield, Building2 } from "lucide-react";
import { ROLE_LABELS, ROLE_ICONS } from "../../utils/roleUtils";

const ContextSwitcher = () => {
  const {
    user, effectiveRole, switchActiveRole,
    activeCompanyId, switchActiveCompany, effectiveCompanyId,
  } = useAuth();

  const additionalRoles = user?.additional_roles || [];
  const companies = user?.companies || [];

  // Só mostrar se tem additional_roles OU múltiplas empresas
  const hasMultipleRoles = additionalRoles.length > 0;
  const hasMultipleCompanies = companies.length > 1;

  if (!hasMultipleRoles && !hasMultipleCompanies) return null;

  // Build list of all available roles (primary + additional, no duplicates)
  const allRoles = [user.role, ...additionalRoles.filter(r => r !== user.role)];

  const currentLabel = ROLE_LABELS[effectiveRole] || effectiveRole;
  const currentIcon = ROLE_ICONS[effectiveRole] || "👤";

  // Encontrar o nome da empresa ativa
  const activeCompanyName = companies.find(c => c.company_id === effectiveCompanyId)?.company_name
    || user?.company
    || "";

  return (
    <div className="flex items-center gap-1.5">
      {/* ── Selector de Empresa ── */}
      {hasMultipleCompanies && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-8 text-xs font-medium border-primary/30 hover:bg-primary/5 transition-colors"
              title={`Empresa ativa: ${activeCompanyName}. Clique para trocar.`}
            >
              <Building2 className="h-3.5 w-3.5 text-primary" />
              <span className="hidden sm:inline max-w-[120px] truncate">{activeCompanyName}</span>
              <ChevronDown className="h-3 w-3 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel className="text-xs font-semibold text-muted-foreground">
              Empresa Activa
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {companies.map((company) => {
              const isActive = company.company_id === effectiveCompanyId;
              const roleInCompany = company.role;
              const roleLabel = ROLE_LABELS[roleInCompany] || roleInCompany;
              return (
                <DropdownMenuItem
                  key={company.company_id}
                  onClick={() => {
                    console.log("[ContextSwitcher] Company click:", company.company_id, company.company_name, "role:", company.role);
                    switchActiveCompany(company.company_id);
                  }}
                  className={`gap-2 cursor-pointer ${isActive ? "bg-primary/10 font-semibold" : ""}`}
                >
                  <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-sm">{company.company_name}</div>
                    <div className="text-[10px] text-muted-foreground">{roleLabel}</div>
                  </div>
                  {isActive && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-primary text-primary-foreground rounded-full font-bold">
                      ATIVO
                    </span>
                  )}
                  {company.is_default && !isActive && (
                    <span className="text-[10px] text-muted-foreground">Padrão</span>
                  )}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {/* ── Selector de Perfil/Role ── */}
      {hasMultipleRoles && (
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
              const label = ROLE_LABELS[role] || role;
              const icon = ROLE_ICONS[role] || "👤";
              return (
                <DropdownMenuItem
                  key={role}
                  onClick={() => {
                    // Encontrar a empresa associada a este role
                    const matchingCompany = companies.find(c => c.role === role);
                    console.log("[ContextSwitcher] Role click:", role, "→ Empresa:", matchingCompany?.company_id, "companies:", companies.map(c => ({ id: c.company_id, role: c.role, name: c.company_name })));
                    switchActiveRole(role, matchingCompany?.company_id);
                  }}
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
      )}
    </div>
  );
};

export default ContextSwitcher;
