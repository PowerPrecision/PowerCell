/**
 * PortalProfileFields — os campos do perfil, vindos do formulário interno.
 *
 * O QUE MUDOU
 *   Os campos do Portal eram uma lista escrita à mão, paralela à do
 *   formulário interno (`form_config`). As duas divergiram: faltavam
 *   campos, não havia sinalização de obrigatórios, e o backend descartava
 *   em silêncio o que não reconhecia. Agora o backend envia o esquema
 *   (`form_schema`) derivado do MESMO `form_config`, e este componente
 *   limita-se a desenhá-lo.
 *
 * DIVULGAÇÃO PROGRESSIVA
 *   Os campos obrigatórios (`is_primary`) ficam à vista. Os restantes
 *   vivem atrás de "Preencher mais detalhes", fechado por omissão: quem
 *   só quer despachar o essencial vê um formulário curto, e quem quer
 *   completar a ficha abre a secção.
 *
 * COMPONENTE DE APRESENTAÇÃO. Não guarda estado nem sabe gravar: diz o
 * que mudou (`onChange(campo, valor)`) e o contentor decide.
 *
 * O NIF NÃO APARECE AQUI de propósito — nunca é editável pelo cliente.
 * O backend não o inclui no esquema; este componente não o trata como
 * caso especial, o que é a forma certa de a regra não se perder.
 */
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

/**
 * @typedef {Object} CampoDoEsquema
 * @property {string} field_key
 * @property {string} label
 * @property {string} field_type - text | email | tel | date | select | number
 * @property {boolean} is_required
 * @property {boolean} is_primary - À vista (true) ou atrás do expansor.
 * @property {Array} [options] - Para `select`.
 * @property {string} [hint]
 */

/** Normaliza as opções: o `form_config` aceita strings ou objectos. */
export function normalizarOpcoes(options) {
  return (options || []).map((opcao) =>
    typeof opcao === "string"
      ? { value: opcao, label: opcao }
      : { value: opcao?.value ?? "", label: opcao?.label ?? opcao?.value ?? "" },
  );
}

/**
 * Separa o esquema nos dois grupos da divulgação progressiva.
 *
 * @param {CampoDoEsquema[]} schema
 * @returns {{principais: CampoDoEsquema[], adicionais: CampoDoEsquema[]}}
 */
export function separarPorVisibilidade(schema) {
  const campos = Array.isArray(schema) ? schema : [];
  return {
    principais: campos.filter((c) => c?.is_primary),
    adicionais: campos.filter((c) => c && !c.is_primary),
  };
}

function Campo({ campo, valor, onChange, disabled }) {
  const opcoes = normalizarOpcoes(campo.options);
  const id = `perfil-${campo.field_key}`;
  const classe = `w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition-colors ${
    disabled
      ? "bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed"
      : "border-gray-200 bg-white"
  }`;

  return (
    <div>
      <label htmlFor={id} className="text-xs font-medium text-gray-600 mb-1 block">
        {campo.label}
        {campo.is_required && (
          // O asterisco sozinho não diz nada a um leitor de ecrã.
          <>
            <span aria-hidden="true" className="text-red-500 ml-0.5">*</span>
            <span className="sr-only"> (obrigatório)</span>
          </>
        )}
      </label>

      {opcoes.length > 0 ? (
        <select
          id={id}
          value={valor ?? ""}
          onChange={(evento) => onChange(campo.field_key, evento.target.value)}
          disabled={disabled}
          required={campo.is_required}
          className={classe}
        >
          <option value="">—</option>
          {opcoes.map((opcao) => (
            <option key={opcao.value} value={opcao.value}>
              {opcao.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={campo.field_type === "select" ? "text" : campo.field_type || "text"}
          value={valor ?? ""}
          onChange={(evento) => onChange(campo.field_key, evento.target.value)}
          disabled={disabled}
          required={campo.is_required}
          className={classe}
        />
      )}

      {campo.hint && (
        <p className="text-[10px] text-gray-400 mt-0.5">{campo.hint}</p>
      )}
    </div>
  );
}

/**
 * @param {Object} props
 * @param {CampoDoEsquema[]} props.schema - Vem do backend (`form_schema`).
 * @param {Object} props.values - Valores actuais, por `field_key`.
 * @param {(campo: string, valor: any) => void} props.onChange
 * @param {boolean} [props.disabled] - Perfil trancado (processo em análise).
 */
export default function PortalProfileFields({
  schema,
  values = {},
  onChange,
  disabled = false,
}) {
  const [maisAberto, setMaisAberto] = useState(false);
  const { principais, adicionais } = separarPorVisibilidade(schema);

  if (principais.length === 0 && adicionais.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {principais.map((campo) => (
          <Campo
            key={campo.field_key}
            campo={campo}
            valor={values[campo.field_key]}
            onChange={onChange}
            disabled={disabled}
          />
        ))}
      </div>

      {adicionais.length > 0 && (
        <div className="border-t border-gray-100 pt-4">
          <button
            type="button"
            onClick={() => setMaisAberto((aberto) => !aberto)}
            aria-expanded={maisAberto}
            aria-controls="perfil-campos-adicionais"
            className="flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            {maisAberto ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
            Preencher mais detalhes ({adicionais.length})
          </button>

          {maisAberto && (
            <div
              id="perfil-campos-adicionais"
              className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4"
            >
              {adicionais.map((campo) => (
                <Campo
                  key={campo.field_key}
                  campo={campo}
                  valor={values[campo.field_key]}
                  onChange={onChange}
                  disabled={disabled}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
