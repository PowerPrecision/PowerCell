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

const ContextSwitcher = () => {
  const {
    user, effectiveRole, switchActiveRole,
    switchActiveCompany, effectiveCompanyId,
  } = useAuth();

  const companies = user?.companies || [];
  const additionalRoles = user?.additional_roles || [];

  // ── Construir lista de perfis para o dropdown de Role ──
  // ESTRATÉGIA: Cada combinação empresa+role é um perfil DISTINTO.
  // Não fazemos dedup por role — o mesmo role em empresas diferentes
  // representa contextos diferentes (dados, assinatura, etc.).
  // Além disso, adicionamos additional_roles que NÃO estejam cobertos
  // por nenhuma empresa (ex: "admin" como role adicional sem empresa).
  // Encontrar o nome da empresa ativa (necessário antes de construir profileItems)
  const activeCompanyName = companies.find(c => c.company_id === effectiveCompanyId)?.company_name
    || user?.company
    || "";

  let profileItems = [];

  if (companies.length > 0) {
    // Fonte principal: companies (objetos com company_id, role, company_name)
    // SEM dedup — cada empresa é um perfil distinto
    profileItems = [...companies];

    // Adicionar additional_roles não cobertos por nenhuma empresa
    // Atribuir a empresa ativa para que a troca de perfil funcione
    const companyRoles = new Set(companies.map(c => c.role));
    for (const role of additionalRoles) {
      if (!companyRoles.has(role)) {
        profileItems.push({
          role,
          company_id: effectiveCompanyId,
          company_name: activeCompanyName || null,
          // PACOTE DF — additional_roles não vêm de UCR real, não são is_default
          is_default: false,
        });
      }
    }

    // Incluir o role primário se não estiver coberto por companies nem additional_roles
    if (!companyRoles.has(user.role) && !additionalRoles.includes(user.role)) {
      profileItems.unshift({
        role: user.role,
        company_id: effectiveCompanyId,
        company_name: activeCompanyName || null,
        // PACOTE DF — role primário sem UCR real; não marca como is_default
        is_default: false,
      });
    }
  } else {
    // Fallback: additional_roles (strings) — sem company_id disponível
    const allRoles = [user.role, ...additionalRoles.filter(r => r !== user.role)];
    profileItems = allRoles.map(role => ({
      role,
      company_id: null,
      company_name: null,
      // PACOTE DF — fallback sem UCR real
      is_default: false,
    }));
  }

  // Filtrar entradas sem role válido (defensivo)
  profileItems = profileItems.filter(p => p.role);

  // Visibilidade: mostrar selector de Role se tem múltiplos perfis
  const hasMultipleRoles = profileItems.length > 1;
  const hasMultipleCompanies = companies.length > 1;

  if (!hasMultipleRoles && !hasMultipleCompanies) return null;

  const currentLabel = ROLE_LABELS[effectiveRole] || effectiveRole;

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
