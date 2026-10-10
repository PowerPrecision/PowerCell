/**
 * «Incluir análise de IA» — a opção, desligada por omissão, que acompanha o
 * botão «Gerar PDF». Só quando está marcada é que o servidor chama o modelo
 * e acrescenta ao PDF um parágrafo de avaliação e comparação da equipa.
 *
 * COMPONENTE DE APRESENTAÇÃO: não sabe o que é um relatório.
 */
import { Sparkles } from "lucide-react";

import { Checkbox } from "../ui/checkbox";
import { Label } from "../ui/label";

/**
 * @param {Object} props
 * @param {boolean} props.marcada
 * @param {(marcada: boolean) => void} props.onChange
 * @param {boolean} [props.desactivada]
 * @param {string} [props.id]
 */
export default function OpcaoAnaliseIA({ marcada, onChange, desactivada = false, id = "incluir-analise-ia" }) {
  return (
    <div className="flex items-center gap-2" data-testid="opcao-analise-ia">
      <Checkbox
        id={id}
        checked={marcada}
        disabled={desactivada}
        onCheckedChange={(valor) => onChange(valor === true)}
      />
      <Label htmlFor={id} className="text-xs cursor-pointer flex items-center gap-1 text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        Incluir análise de IA
      </Label>
    </div>
  );
}
