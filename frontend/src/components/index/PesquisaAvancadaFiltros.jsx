/**
 * PesquisaAvancadaFiltros — o formulário da pesquisa avançada (apresentação pura).
 *
 * Só desenha os campos que existem no tipo escolhido (`camposDoTipo`): um filtro que o servidor
 * recusaria (um banco num recibo) nem aparece. Diz o que aconteceu (`onMudar(campo, valor)`,
 * `onPesquisar`, `onLimpar`); o estado é da página.
 */
import { Search, X } from "lucide-react";

import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { CONTRATOS, TIPOS_DE_DOCUMENTO, camposDoTipo } from "../../utils/pesquisaIndex";

const CAMPOS_DE_TEXTO = {
  employer_name: { rotulo: "Entidade patronal", placeholder: "Nome" },
  employer_nif: { rotulo: "NIF da entidade", placeholder: "Começa por…", inputMode: "numeric" },
  employer_location: { rotulo: "Localidade / região", placeholder: "Ex.: Lisboa, Setúbal" },
  job_title: { rotulo: "Cargo", placeholder: "Ex.: Técnico" },
  bank: { rotulo: "Banco", placeholder: "Ex.: CGD, Santander, ActivoBank" },
  min_salary: { rotulo: "Líquido mínimo (€)", placeholder: "Ex.: 1200", inputMode: "decimal" },
  max_salary: { rotulo: "Líquido máximo (€)", placeholder: "Ex.: 1200", inputMode: "decimal" },
  period_from: { rotulo: "Período desde", placeholder: "AAAA-MM" },
  period_to: { rotulo: "Período até", placeholder: "AAAA-MM" },
};

const ORDEM = [
  "employer_name", "employer_nif", "employer_location", "job_title", "bank",
  "min_salary", "max_salary", "period_from", "period_to",
];

export function PesquisaAvancadaFiltros({ valores, erros = {}, aPesquisar = false, onMudar, onPesquisar, onLimpar }) {
  const visiveis = new Set(camposDoTipo(valores.document_type));
  const alternaContrato = (valor) => {
    const actuais = valores.contract_type;
    onMudar("contract_type", actuais.includes(valor) ? actuais.filter((c) => c !== valor) : [...actuais, valor]);
  };

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onPesquisar();
      }}
      aria-label="Pesquisa avançada"
      data-testid="pesquisa-formulario"
    >
      <div className="max-w-sm space-y-1.5">
        <Label htmlFor="ps-tipo">O que procurar</Label>
        <select
          id="ps-tipo"
          value={valores.document_type}
          onChange={(e) => onMudar("document_type", e.target.value)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {TIPOS_DE_DOCUMENTO.map((t) => (
            <option key={t.valor || "emprego"} value={t.valor}>{t.rotulo}</option>
          ))}
        </select>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ORDEM.filter((campo) => visiveis.has(campo)).map((campo) => {
          const def = CAMPOS_DE_TEXTO[campo];
          const id = `ps-${campo}`;
          return (
            <div key={campo} className="space-y-1.5">
              <Label htmlFor={id}>{def.rotulo}</Label>
              <Input
                id={id}
                value={valores[campo]}
                inputMode={def.inputMode}
                placeholder={def.placeholder}
                onChange={(e) => onMudar(campo, e.target.value)}
                aria-invalid={Boolean(erros[campo])}
                aria-describedby={erros[campo] ? `${id}-erro` : undefined}
              />
              {erros[campo] && (
                <p id={`${id}-erro`} role="alert" className="text-xs text-destructive">{erros[campo]}</p>
              )}
            </div>
          );
        })}
      </div>

      {visiveis.has("contract_type") && (
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium">Tipo de contrato</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {CONTRATOS.map((c) => (
              <label key={c.valor} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={valores.contract_type.includes(c.valor)}
                  onChange={() => alternaContrato(c.valor)}
                  className="h-4 w-4 rounded border-input"
                />
                {c.rotulo}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" disabled={aPesquisar} className="gap-2">
          <Search className="h-4 w-4" aria-hidden="true" />Pesquisar
        </Button>
        <Button type="button" variant="ghost" onClick={onLimpar} className="gap-2">
          <X className="h-4 w-4" aria-hidden="true" />Limpar
        </Button>
      </div>
    </form>
  );
}

export default PesquisaAvancadaFiltros;
