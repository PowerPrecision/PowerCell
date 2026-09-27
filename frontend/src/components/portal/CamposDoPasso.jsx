/**
 * CamposDoPasso — divulgação progressiva no formulário público (Ponto 9).
 *
 * PORQUÊ: cada passo mostrava todos os campos ao mesmo nível, com
 * asteriscos vermelhos e "(obrigatório)" repetidos dezenas de vezes.
 * O cliente lia uma parede de exigências e concluía que ia falhar a
 * submissão — quando, na verdade, o `form_config` só bloqueia 20 dos 64
 * campos, e o backend aceita um registo com quatro.
 *
 * O que fica à vista são os campos que BLOQUEIAM mesmo. O resto entra
 * num painel fechado, com um convite em vez de uma ameaça.
 *
 * Componente de APRESENTAÇÃO: recebe os campos já separados e a função
 * que sabe desenhar um campo. Não conhece o `formData` nem valida nada.
 */
import { useState } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { ChevronDown, Sparkles } from "lucide-react";
import { textoDoPainelSecundario } from "../../utils/formularioPublicoCampos";

/**
 * @param {object} props
 * @param {Array} props.primarios — campos que bloqueiam o avanço
 * @param {Array} props.secundarios — campos opcionais
 * @param {(campo: object) => React.ReactNode} props.renderCampo
 * @param {boolean} [props.abertoPorOmissao] — só quando o cliente já
 *   preencheu algum destes campos (ex.: retomou o formulário guardado)
 */
export default function CamposDoPasso({
  primarios,
  secundarios,
  renderCampo,
  abertoPorOmissao = false,
}) {
  const [aberto, setAberto] = useState(Boolean(abertoPorOmissao));
  const texto = textoDoPainelSecundario(secundarios?.length || 0);

  return (
    <div className="space-y-5">
      {primarios?.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {primarios.map((campo) => renderCampo(campo))}
        </div>
      )}

      {texto && (
        <Collapsible open={aberto} onOpenChange={setAberto}>
          <CollapsibleTrigger
            className="w-full flex items-center gap-3 rounded-lg border border-border
                       bg-muted/40 px-4 py-3 text-left transition-colors
                       hover:bg-muted/70 focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-ring"
            data-testid="abrir-campos-adicionais"
          >
            <Sparkles className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="flex-1 min-w-0">
              <span className="block text-sm font-medium text-foreground">
                {texto.titulo}
              </span>
              <span className="block text-xs text-muted-foreground">
                {texto.resumo}
              </span>
            </span>
            <ChevronDown
              className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform
                          ${aberto ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div className="pt-4 space-y-4">
              {/* O convite repete-se aqui dentro de propósito: quem abre
                  o painel e vê uma lista de campos precisa de saber, no
                  mesmo sítio, que pode fechá-lo e seguir. */}
              <p className="text-xs text-muted-foreground" data-testid="ajuda-campos-adicionais">
                {texto.ajuda}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {secundarios.map((campo) => renderCampo(campo))}
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
