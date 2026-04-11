import { useState, useEffect, useRef } from "react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import {
  Phone,
  Mail,
  User,
  Calculator,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Building2,
  CreditCard,
} from "lucide-react";
import DSTICalculator from "./DSTICalculator";
import RiskCalculator from "./RiskCalculator";

/**
 * Header fixo que permanece visível durante o scroll
 * Mostra dados essenciais do cliente e botões de calculadoras
 */
const ProcessStickyHeader = ({
  process,
  personalData,
  financialData,
  statusInfo,
  collapsed: externalCollapsed,
  onToggleCollapse,
}) => {
  const [isSticky, setIsSticky] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const headerRef = useRef(null);

  // Usar estado interno se não for controlado externamente
  const collapsed = externalCollapsed !== undefined ? externalCollapsed : internalCollapsed;
  const setCollapsed = onToggleCollapse || setInternalCollapsed;

  // Detectar scroll para ativar sticky
  useEffect(() => {
    const handleScroll = () => {
      if (headerRef.current) {
        const rect = headerRef.current.getBoundingClientRect();
        // Ativar sticky quando o cabeçalho original sair do ecrã
        setIsSticky(window.scrollY > 200);
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Dados do cliente para pré-preenchimento das calculadoras
  const clientDataForCalculators = {
    rendimento_bruto: financialData?.rendimento_bruto,
    rendimento_mensal: financialData?.monthly_income || financialData?.salario_liquido,
    salario_liquido: financialData?.salario_liquido,
    renda_habitacao_atual: financialData?.renda_habitacao_atual,
    valor_imovel: financialData?.valor_imovel || process?.real_estate_data?.valor,
    valor_entrada: financialData?.valor_entrada || financialData?.capital_proprio,
    capital_proprio: financialData?.capital_proprio,
    idade: personalData?.idade,
    data_nascimento: personalData?.data_nascimento || personalData?.birth_date,
    rendimento_co_titular: financialData?.rendimento_co_titular,
  };

  // Status color mapping
  const statusColors = {
    yellow: "bg-yellow-100 text-yellow-800 border-yellow-200",
    blue: "bg-blue-100 text-blue-800 border-blue-200",
    orange: "bg-orange-100 text-orange-800 border-orange-200",
    green: "bg-emerald-100 text-emerald-800 border-emerald-200",
    red: "bg-red-100 text-red-800 border-red-200",
    purple: "bg-purple-100 text-purple-800 border-purple-200",
  };

  const currentStatusColor = statusColors[statusInfo?.color] || statusColors.blue;

  return (
    <>
      {/* Placeholder para evitar salto quando sticky ativa */}
      {isSticky && <div className="h-16 lg:h-20 flex-shrink-0" aria-hidden="true" />}

      {/* Header fixo */}
      <div
        ref={headerRef}
        className={`
          z-40 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700
          transition-all duration-200
          ${isSticky ? "fixed top-12 lg:top-16 left-0 right-0 lg:left-64 shadow-md" : ""}
        `}
      >
        <div className="px-4 py-2">
          {/* Linha principal - sempre visível */}
          <div className="flex items-center justify-between">
            {/* Info do cliente */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <User className="h-4 w-4 text-gray-500" />
                <span className="font-semibold text-sm truncate max-w-[200px]">
                  {process?.client_name}
                </span>
                {process?.process_number && (
                  <span className="text-xs text-gray-500 font-mono">
                    #{process.process_number}
                  </span>
                )}
              </div>

              {!collapsed && (
                <>
                  {/* Contactos */}
                  <div className="hidden md:flex items-center gap-3 text-xs text-gray-600 min-w-0">
                    {process?.client_phone && (
                      <a
                        href={`tel:${process.client_phone}`}
                        className="flex items-center gap-1 hover:text-blue-600 flex-shrink-0"
                      >
                        <Phone className="h-3 w-3" />
                        {process.client_phone}
                      </a>
                    )}
                    {process?.client_email && (
                      <a
                        href={`mailto:${process.client_email}`}
                        className="flex items-center gap-1 hover:text-blue-600 flex-shrink-0"
                        title={process.client_email}
                      >
                        <Mail className="h-3 w-3" />
                        <span className="truncate max-w-[180px]">
                          {process.client_email}
                        </span>
                      </a>
                    )}
                  </div>

                  {/* NIF e Rendimento */}
                  <div className="hidden lg:flex items-center gap-3 text-xs flex-shrink-0">
                    {personalData?.nif && (
                      <span className="bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                        NIF: {personalData.nif}
                      </span>
                    )}
                    {(financialData?.monthly_income || financialData?.salario_liquido) && (
                      <span className="bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 px-2 py-0.5 rounded">
                        Rendimento: {(financialData.monthly_income || financialData.salario_liquido).toLocaleString('pt-PT')}€
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* Status e Ações */}
            <div className="flex items-center gap-2">
              {/* Status badge */}
              <Badge className={`${currentStatusColor} border text-xs`}>
                {statusInfo?.label || process?.status}
              </Badge>

              {/* Calculadoras - sempre visíveis */}
              <div className="flex items-center gap-1">
                <DSTICalculator
                  trigger={
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs gap-1"
                      title="Calculadora DSTI"
                    >
                      <Calculator className="h-3 w-3" />
                      <span className="hidden sm:inline">DSTI</span>
                    </Button>
                  }
                  clientData={clientDataForCalculators}
                />
                <RiskCalculator
                  trigger={
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs gap-1"
                      title="Calculadora de Risco"
                    >
                      <TrendingUp className="h-3 w-3" />
                      <span className="hidden sm:inline">Risco</span>
                    </Button>
                  }
                  clientData={clientDataForCalculators}
                />
              </div>

              {/* Botão expandir/colapsar */}
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? "Expandir detalhes" : "Colapsar detalhes"}
                title={collapsed ? "Expandir detalhes" : "Colapsar detalhes"}
              >
                {collapsed ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronUp className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>

          {/* Linha expandida - detalhes adicionais */}
          {!collapsed && (
            <div className="mt-2 pt-2 border-t border-gray-100 dark:border-gray-800">
              <div className="flex flex-wrap items-center gap-4 text-xs">
                {/* Tipo de processo */}
                <div className="flex items-center gap-1 text-gray-600">
                  <Building2 className="h-3 w-3" />
                  <span>
                    {process?.process_type === 'credito' ? 'Crédito' :
                     process?.process_type === 'imobiliaria' ? 'Imobiliária' :
                     process?.process_type === 'ambos' ? 'Crédito + Imobiliária' : 'N/A'}
                  </span>
                </div>

                {/* Valor pretendido */}
                {(financialData?.valor_pretendido || financialData?.valor_financiado) && (
                  <div className="flex items-center gap-1 text-gray-600">
                    <CreditCard className="h-3 w-3" />
                    <span>Valor: {(financialData.valor_pretendido || financialData.valor_financiado).toLocaleString('pt-PT')}€</span>
                  </div>
                )}

                {/* Capital próprio */}
                {financialData?.capital_proprio && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Entrada:</span>
                    <span className="font-medium">{financialData.capital_proprio.toLocaleString('pt-PT')}€</span>
                  </div>
                )}

                {/* Emprego */}
                {financialData?.employment_type && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Emprego:</span>
                    <span className="font-medium capitalize">{financialData.employment_type.replace('_', ' ')}</span>
                  </div>
                )}

                {/* Consultor/Mediador */}
                {/* Consultores (suporte a múltiplos) */}
                {(process?.consultor_names?.length > 0 || process?.assigned_consultor_name) && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Consultores:</span>
                    <span className="font-medium">
                      {process.consultor_names?.join(", ") || process.assigned_consultor_name}
                    </span>
                  </div>
                )}
                {/* Mediadores (suporte a múltiplos) */}
                {(process?.mediador_names?.length > 0 || process?.assigned_mediador_name) && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Intermediários:</span>
                    <span className="font-medium">
                      {process.mediador_names?.join(", ") || process.assigned_mediador_name}
                    </span>
                  </div>
                )}

                {/* Indexação */}
                {process?.indexacao_name && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Indexação:</span>
                    <span className="font-medium text-indigo-600 dark:text-indigo-400">
                      {process.indexacao_name}
                    </span>
                  </div>
                )}
                
                {/* Parceiro (Utilizador Fantasma) */}
                {process?.parceiro_name && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Parceiro:</span>
                    <span className="font-medium text-violet-600 dark:text-violet-400">
                      {process.parceiro_name}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default ProcessStickyHeader;
