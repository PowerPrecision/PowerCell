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
 * O NIF (e tudo o que a equipa gere) APARECE SÓ PARA LER: o backend marca a entrada
 * `read_only` e envia o valor já mascarado em `somenteLeitura`. Este componente não
 * trata o NIF como caso especial — desenha um campo desactivado com o texto que lhe
 * dão, o que é a forma certa de a regra não se perder (e de o valor em claro nunca
 * chegar aqui).
 *
 * TIPOS (o registo tem mais do que texto): caixa simples (booleano), grupo de
 * opções (lista), área de texto, número, data e escolha.
 */
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { textoDoPainelSecundario } from "../../utils/formularioPublicoCampos";

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

function RotuloDoCampo({ campo, id }) {
  return (
    <label htmlFor={id} className="text-xs font-medium text-gray-600 mb-1 block">
      {campo.label}
      {campo.is_required && !campo.read_only && (
        // O asterisco sozinho não diz nada a um leitor de ecrã.
        <>
          <span aria-hidden="true" className="text-red-500 ml-0.5">*</span>
          <span className="sr-only"> (obrigatório)</span>
        </>
      )}
    </label>
  );
}

function Campo({ campo, valor, onChange, disabled, textoSoLeitura }) {
  const opcoes = normalizarOpcoes(campo.options);
  const id = `perfil-${campo.field_key}`;

  if (campo.read_only) {
    return (
      <div>
        <RotuloDoCampo campo={campo} id={id} />
        <input
          id={id}
          type="text"
          value={textoSoLeitura ?? ""}
          readOnly
          disabled
          className="w-full px-3 py-2 text-sm border border-gray-100 rounded-lg bg-gray-50 text-gray-500 cursor-not-allowed"
        />
        <p className="text-[10px] text-gray-400 mt-0.5">
          Gerido pela nossa equipa — contacte o seu consultor para alterar.
        </p>
      </div>
    );
  }

  if (campo.field_type === "checkbox" && opcoes.length > 0) {
    // Grupo de opções: o valor é a lista das escolhidas.
    const escolhidas = Array.isArray(valor) ? valor : [];
    const alternar = (opcao) =>
      onChange(
        campo.field_key,
        escolhidas.includes(opcao)
          ? escolhidas.filter((v) => v !== opcao)
          : [...escolhidas, opcao],
      );
    return (
      <fieldset className="sm:col-span-2">
        <legend className="text-xs font-medium text-gray-600 mb-1">{campo.label}</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {opcoes.map((opcao) => (
            <label key={opcao.value} className="flex items-center gap-1.5 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={escolhidas.includes(opcao.value)}
                onChange={() => alternar(opcao.value)}
                disabled={disabled}
                className="rounded border-gray-300"
              />
              {opcao.label}
            </label>
          ))}
        </div>
        {campo.hint && <p className="text-[10px] text-gray-400 mt-0.5">{campo.hint}</p>}
      </fieldset>
    );
  }

  if (campo.field_type === "checkbox") {
    return (
      <div className="flex items-center gap-2 sm:col-span-2">
        <input
          id={id}
          type="checkbox"
          checked={valor === true}
          onChange={(evento) => onChange(campo.field_key, evento.target.checked)}
          disabled={disabled}
          className="rounded border-gray-300"
        />
        <label htmlFor={id} className="text-sm text-gray-700">{campo.label}</label>
      </div>
    );
  }

  const classe = `w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition-colors ${
    disabled
      ? "bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed"
      : "border-gray-200 bg-white"
  }`;

  return (
    <div className={campo.field_type === "textarea" ? "sm:col-span-2" : undefined}>
      <RotuloDoCampo campo={campo} id={id} />

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
      ) : campo.field_type === "textarea" ? (
        <textarea
          id={id}
          rows={3}
          value={valor ?? ""}
          onChange={(evento) => onChange(campo.field_key, evento.target.value)}
          disabled={disabled}
          required={campo.is_required}
          className={classe}
        />
      ) : (
        <input
          id={id}
          type={["select", "radio", "checkbox"].includes(campo.field_type) ? "text" : campo.field_type || "text"}
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
 * @param {Object} [props.somenteLeitura] - Texto dos campos `read_only`, por `field_key`
 *   (o NIF já vem mascarado do servidor).
 */
export default function PortalProfileFields({
  schema,
  values = {},
  onChange,
  disabled = false,
  somenteLeitura = {},
}) {
  const [maisAberto, setMaisAberto] = useState(false);
  const { principais, adicionais } = separarPorVisibilidade(schema);
  // Vários cartões na mesma página: o id do painel tem de ser único por secção.
  const idAdicionais = `perfil-campos-adicionais-${(Array.isArray(schema) && schema[0]?.section) || "titular"}`;
  const textoDoPainel = textoDoPainelSecundario(adicionais.length);

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
            textoSoLeitura={somenteLeitura[campo.field_key]}
          />
        ))}
      </div>

      {adicionais.length > 0 && (
        <div className="border-t border-gray-100 pt-4">
          <button
            type="button"
            onClick={() => setMaisAberto((aberto) => !aberto)}
            aria-expanded={maisAberto}
            aria-controls={idAdicionais}
            className="flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            {maisAberto ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
            {textoDoPainel?.titulo || "Informação adicional importante"} (
            {adicionais.length})
          </button>
          {/* Ponto 9 — o convite diz o que o cliente ganha e deixa claro
              que pode seguir sem isto. O mesmo texto do formulário
              público, para as duas superfícies falarem igual. */}
          <p className="text-xs text-gray-500 mt-1">
            {textoDoPainel?.ajuda}
          </p>

          {maisAberto && (
            <div
              id={idAdicionais}
              className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4"
            >
              {adicionais.map((campo) => (
                <Campo
                  key={campo.field_key}
                  campo={campo}
                  valor={values[campo.field_key]}
                  onChange={onChange}
                  disabled={disabled}
                  textoSoLeitura={somenteLeitura[campo.field_key]}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
