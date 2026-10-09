/**
 * Selector da empresa cuja configuração se edita (Bloco 1, ponto 3).
 *
 * Apresentação pura: diz o que foi escolhido, o contentor decide o que
 * isso implica. É um `<select>` nativo de propósito — acessível, testável
 * por papel e nome, e sem a dependência de captura de ponteiro do Radix.
 */
import { Building2 } from "lucide-react";

import { EMPRESA_GLOBAL } from "../../utils/empresaDeConfiguracao";

export default function EmpresaConfigSelector({ empresas, valor, onChange }) {
  return (
    <div className="flex items-center gap-2" data-testid="config-empresa-selector">
      <Building2 className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />
      <label htmlFor="config-empresa" className="text-sm text-muted-foreground whitespace-nowrap">
        Empresa
      </label>
      <select
        id="config-empresa"
        value={valor}
        onChange={(evento) => onChange(evento.target.value)}
        className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {empresas.map((empresa) => (
          <option key={empresa.company_id} value={empresa.company_id}>
            {empresa.company_id === EMPRESA_GLOBAL
              ? "Global (todas as empresas)"
              : empresa.company_name}
          </option>
        ))}
      </select>
    </div>
  );
}
