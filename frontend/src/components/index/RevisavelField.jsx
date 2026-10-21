/**
 * RevisavelField — um campo extraído por IA com o estado da sua fiabilidade.
 *
 * Mostra «A rever» (a IA não sabe ou duvida) ou «Editado» (uma pessoa dispôs). O texto vive em
 * ESTADO DE TEXTO (um número num `<input>` faz reaparecer o `0` a cada tecla); a página converte
 * ao guardar. O rótulo está associado ao CAMPO (`htmlFor`), para o teste e o leitor de ecrã o
 * encontrarem pelo nome.
 */
import { Badge } from "../ui/badge";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { TIPOS_DE_CONTRATO, campoPrecisaDeRevisao } from "../../utils/indexRevisao";

export function RevisavelField({ id, rotulo, tipo, campo, valor, onChange, disabled = false }) {
  const aRever = campoPrecisaDeRevisao(campo);
  const editado = campo?.edited_by_human === true;

  return (
    <div className="space-y-1.5" data-testid={`campo-${id}`}>
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{rotulo}</Label>
        {aRever ? (
          <Badge variant="secondary">A rever</Badge>
        ) : editado ? (
          <Badge variant="outline">Editado</Badge>
        ) : null}
      </div>
      {tipo === "contrato" ? (
        <select
          id={id}
          value={valor}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Sem valor</option>
          {TIPOS_DE_CONTRATO.map((t) => (
            <option key={t.valor} value={t.valor}>
              {t.rotulo}
            </option>
          ))}
        </select>
      ) : (
        <Input
          id={id}
          value={valor}
          disabled={disabled}
          inputMode={tipo === "dinheiro" || tipo === "nif" ? "decimal" : undefined}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={aRever || undefined}
        />
      )}
    </div>
  );
}

export default RevisavelField;
