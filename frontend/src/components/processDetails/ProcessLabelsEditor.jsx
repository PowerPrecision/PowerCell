/**
 * ProcessLabelsEditor — as etiquetas de um processo, no cabeçalho.
 *
 * Ponto 15 (Lote 5, Secção B). O `labels` já existia no modelo e os
 * crachás já eram renderizados; o que não existia era a forma de os
 * pôr e tirar. Este é o Dialog que o comentário do PACOTE DD prometia
 * e que nunca foi construído.
 *
 * PROGRESSIVE DISCLOSURE (FRONTEND_GUIDELINES § 2)
 *   Em repouso vêem-se só os crachás — que é o que interessa a quem
 *   está a ler o processo. Editar é um gesto deliberado atrás de um
 *   botão, num `Dialog`, como todos os formulários secundários.
 *
 * APRESENTAÇÃO, NÃO DECISÃO
 *   Não grava: diz o que aconteceu (`onChange`) e o contentor decide o
 *   que isso implica. O `ProcessDetails` é que sabe que isto passa pelo
 *   `handleSaveOrganization` com `allowEmptyArrays: ["labels"]`.
 */
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Tag, Plus, X, Loader2 } from "lucide-react";
import {
  MAX_ETIQUETAS,
  corDaEtiqueta,
  normalizarEtiquetas,
  podeAcrescentar,
} from "../../utils/processLabels";

/** Id do datalist — partilhado pelo input e pelo atributo `list`. */
const SUGESTOES_ID = "sugestoes-etiquetas-processo";

export default function ProcessLabelsEditor({
  labels,
  sugestoes = [],
  onChange,
  disabled = false,
  saving = false,
}) {
  const actuais = useMemo(() => normalizarEtiquetas(labels), [labels]);
  const [aberto, setAberto] = useState(false);
  const [rascunho, setRascunho] = useState(actuais);
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState("");

  // Reabrir o diálogo parte sempre do que está gravado: um rascunho
  // abandonado não pode reaparecer como se tivesse sido aceite.
  useEffect(() => {
    if (aberto) {
      setRascunho(actuais);
      setTexto("");
      setErro("");
    }
  }, [aberto, actuais]);

  const acrescentar = () => {
    const resultado = podeAcrescentar(rascunho, texto);
    if (!resultado.ok) {
      setErro(resultado.motivo);
      return;
    }
    setRascunho([...rascunho, resultado.etiqueta]);
    setTexto("");
    setErro("");
  };

  const remover = (etiqueta) =>
    setRascunho(rascunho.filter((e) => e !== etiqueta));

  const confirmar = async () => {
    await onChange?.(normalizarEtiquetas(rascunho));
    setAberto(false);
  };

  // Só as sugestões que ainda não estão no rascunho — propor o que já lá
  // está é oferecer um clique que dá erro.
  const disponiveis = normalizarEtiquetas(sugestoes).filter(
    (s) => !rascunho.some((e) => e.toLowerCase() === s.toLowerCase()),
  );

  return (
    <>
      {actuais.map((etiqueta) => (
        <Badge
          key={etiqueta}
          variant="outline"
          data-testid="etiqueta-processo"
          className={`text-xs ${corDaEtiqueta(etiqueta)}`}
        >
          {etiqueta}
        </Badge>
      ))}

      {!disabled && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-1.5 text-xs gap-1 text-muted-foreground hover:text-foreground"
          onClick={() => setAberto(true)}
          data-testid="abrir-etiquetas"
        >
          <Tag className="h-3 w-3" aria-hidden="true" />
          {actuais.length === 0 ? "Etiquetas" : "Gerir"}
        </Button>
      )}

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Tag className="h-4 w-4" aria-hidden="true" />
              Etiquetas do processo
            </DialogTitle>
            <DialogDescription>
              Marcadores para segmentar este processo — por exemplo "Sub 35",
              "VIP" ou "Urgente". Máximo de {MAX_ETIQUETAS}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex flex-wrap gap-1.5 min-h-[28px]">
              {rascunho.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Ainda sem etiquetas.
                </p>
              ) : (
                rascunho.map((etiqueta) => (
                  <Badge
                    key={etiqueta}
                    variant="outline"
                    className={`text-xs gap-1 pr-1 ${corDaEtiqueta(etiqueta)}`}
                  >
                    {etiqueta}
                    <button
                      type="button"
                      onClick={() => remover(etiqueta)}
                      aria-label={`Remover etiqueta ${etiqueta}`}
                      className="rounded-sm hover:bg-background/50 p-0.5"
                    >
                      <X className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </Badge>
                ))
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="nova-etiqueta">Nova etiqueta</Label>
              <div className="flex gap-2">
                <Input
                  id="nova-etiqueta"
                  value={texto}
                  list={SUGESTOES_ID}
                  placeholder="Sub 35"
                  onChange={(e) => {
                    setTexto(e.target.value);
                    if (erro) setErro("");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      acrescentar();
                    }
                  }}
                />
                {/* `datalist` nativo: sugere o que já existe (evita "VIP"
                    e "V.I.P." a viverem lado a lado) sem impedir criar
                    uma etiqueta nova. Mesmo padrão do CompanyNetworkField. */}
                <datalist id={SUGESTOES_ID}>
                  {disponiveis.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
                <Button type="button" variant="outline" onClick={acrescentar} className="gap-1">
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  Adicionar
                </Button>
              </div>
              {erro && (
                <p className="text-xs text-destructive" role="alert">
                  {erro}
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAberto(false)}>
              Cancelar
            </Button>
            <Button type="button" onClick={confirmar} disabled={saving} className="gap-1.5">
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
