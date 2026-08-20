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
import {
  buildUserProfileItems,
  getUserCompanyRecords,
  normalizeCompanyRecord,
} from "../../utils/userProfiles";

const ContextSwitcher = () => {
  const {
    user, effectiveRole, switchActiveRole,
    switchActiveCompany, effectiveCompanyId,
  } = useAuth();

  const companies = getUserCompanyRecords(user)
    .map((c) => normalizeCompanyRecord(c))
    .filter(Boolean);
  const profileItems = buildUserProfileItems(user, { effectiveCompanyId });

  // Encontrar o nome da empresa ativa
  const activeCompanyName = companies.find(c => c.company_id === effectiveCompanyId)?.company_name
    || user?.company
    || "";

  // Visibilidade: mostrar selector de Role se tem múltiplos perfis
  const hasMultipleRoles = profileItems.length > 1;
  const hasMultipleCompanies = companies.length > 1;
  // PACOTE DM: o contexto da empresa já vem do perfil no Header.
  // A dropbox extra de empresa (típica no Diretor com vários UCRs) é redundante.
  const showCompanySwitcher = hasMultipleCompanies && !hasMultipleRoles
    && effectiveRole !== "diretor";

  if (!hasMultipleRoles && !showCompanySwitcher) return null;

  const currentLabel = ROLE_LABELS[effectiveRole] || effectiveRole;

  return (
    <div className="flex items-center gap-1.5">
      {/* ── Selector de Empresa ── */}
      {showCompanySwitcher && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-8 text-xs font-medium border-primary/30 hover:bg-primary/5 transition-colors"
              title={`Empresa ativa: ${activeCompanyName}. Clique para trocar.`}
              aria-label={`Empresa ativa: ${activeCompanyName}. Clique para trocar.`}
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
              aria-label={`Modo atual: ${currentLabel}. Clique para trocar.`}
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
            {profileItems.map((profile) => {
              const selectedRole = profile.role;
              const selectedCompanyId = profile.company_id;
              const isActive = selectedRole === effectiveRole && (!selectedCompanyId || selectedCompanyId === effectiveCompanyId);
              const label = ROLE_LABELS[selectedRole] || selectedRole;
              const icon = ROLE_ICONS[selectedRole] || "👤";
              return (
                <DropdownMenuItem
                  key={`${selectedRole}-${selectedCompanyId}`}
                  onClick={() => {
                    // ── Mapeamento exacto: role + company_id do mesmo objeto ──
                    // Antes: iterava allRoles (strings) e fazia find() — falhava
                    // se companies=[] ou role duplicado. Agora: o company_id vem
                    // directamente do mesmo objeto, garantido.
                    switchActiveRole(selectedRole, selectedCompanyId);
                  }}
                  className={`gap-2 cursor-pointer ${isActive ? "bg-primary/10 font-semibold" : ""}`}
                >
                  <span className="text-base">{icon}</span>
                  <div className="flex-1 min-w-0">
                    <span>{label}</span>
                    {companies.length > 1 && profile.company_name && (
                      <span className="text-[10px] text-muted-foreground ml-1">({profile.company_name})</span>
                    )}
                  </div>
                  {isActive && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-primary text-primary-foreground rounded-full font-bold">
                      ATIVO
                    </span>
                  )}
                  {/* PACOTE DF — remove "Principal" label sintético.
                      Não há "conta principal" — há UCR is_default (definido
                      no backend). Só mostrar "Padrão" se este UCR está
                      marcado como is_default e não é o activo. */}
                  {!isActive && profile.is_default && (
                    <span className="text-[10px] text-muted-foreground">Padrão</span>
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
