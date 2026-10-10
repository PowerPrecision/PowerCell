/**
 * «Arquivar no Processo» — diálogo do Webmail (Bloco 2, Lote 12).
 *
 * Componente de APRESENTAÇÃO: o contentor carrega as sugestões e faz o
 * pedido; aqui só se escolhe o processo e, quando o ficheiro não vai para
 * a pasta Index, a pasta final. A decisão do destino é do servidor — o
 * ecrã di-la (`avisoDoDestino`) antes de o utilizador confirmar, para que
 * ninguém conclua que o anexo «desapareceu» quando foi para a Index.
 *
 * Com mais do que um processo possível NÃO há pré-selecção (arquivar no
 * processo errado é um cruzamento de dados), e sem nenhum o diálogo diz o
 * que fazer a seguir em vez de ficar vazio.
 */
import { useEffect, useState } from "react";
import { Archive, Loader2 } from "lucide-react";

import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Label } from "../ui/label";
import { RadioGroup, RadioGroupItem } from "../ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Skeleton } from "../ui/skeleton";
import {
  avisoDoDestino,
  CATEGORIA_POR_OMISSAO,
  CATEGORIAS_DE_ARQUIVO,
  devePerguntarAPasta,
  processoEscolhido,
  processoPreSeleccionado,
  rotuloDoProcesso,
  sugestoesDe,
} from "../../utils/emailArchive";

/**
 * @param {object} props
 * @param {boolean} props.open
 * @param {(open: boolean) => void} props.onOpenChange
 * @param {string} [props.nomeDoAnexo]
 * @param {"a_carregar"|"pronto"|"erro"} props.estado
 * @param {object|null} [props.resposta] `GET /emails/{id}/archive-suggestions`.
 * @param {string} [props.erro]
 * @param {boolean} [props.arquivando]
 * @param {(escolha: {processId: string, category: string}) => void} props.onConfirmar
 * @param {() => void} [props.onTentarDeNovo]
 */
const ArquivarNoProcessoDialog = ({
  open,
  onOpenChange,
  nomeDoAnexo = "",
  estado,
  resposta = null,
  erro = "",
  arquivando = false,
  onConfirmar,
  onTentarDeNovo,
}) => {
  const sugestoes = sugestoesDe(resposta);
  const [processId, setProcessId] = useState(null);
  const [categoria, setCategoria] = useState(CATEGORIA_POR_OMISSAO);

  // Quando chegam sugestões novas, parte-se da pré-selecção do servidor.
  useEffect(() => {
    setProcessId(processoPreSeleccionado(resposta));
    setCategoria(CATEGORIA_POR_OMISSAO);
  }, [resposta]);

  const escolhido = processoEscolhido(resposta, processId);
  const perguntaAPasta = devePerguntarAPasta(escolhido);
  const aviso = avisoDoDestino(escolhido);
  const enderecos = Array.isArray(resposta?.enderecos) ? resposta.enderecos : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="arquivar-dialogo">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Archive className="h-4 w-4" aria-hidden="true" />
            Arquivar no Processo
          </DialogTitle>
          <DialogDescription>
            {nomeDoAnexo ? `Anexo: ${nomeDoAnexo}` : "Escolha o processo onde guardar o anexo."}
          </DialogDescription>
        </DialogHeader>

        {estado === "a_carregar" && (
          <div className="space-y-2" role="status" aria-label="A procurar o processo">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}

        {estado === "erro" && (
          <div className="space-y-3" role="alert">
            <p className="text-sm text-destructive">{erro || "Não foi possível obter as sugestões."}</p>
            {onTentarDeNovo && (
              <Button type="button" variant="outline" size="sm" onClick={onTentarDeNovo}>
                Tentar novamente
              </Button>
            )}
          </div>
        )}

        {estado === "pronto" && sugestoes.length === 0 && (
          <div className="space-y-2 text-sm" data-testid="arquivar-sem-processo">
            <p>
              Não há nenhum processo activo associado
              {enderecos.length > 0 ? ` a ${enderecos.join(", ")}` : " a este contacto"}.
            </p>
            <p className="text-muted-foreground">
              Ligue primeiro o email a um processo (botão «Ligar a processo») e volte a arquivar.
            </p>
          </div>
        )}

        {estado === "pronto" && sugestoes.length > 0 && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {resposta?.ambiguo
                ? "Este contacto tem mais do que um processo activo — escolha o correcto."
                : "Processo activo associado ao endereço da conversa."}
            </p>
            <RadioGroup
              value={processId || ""}
              onValueChange={setProcessId}
              aria-label="Processo onde arquivar"
            >
              {sugestoes.map((s) => (
                <Label
                  key={s.process_id}
                  htmlFor={`arquivar-${s.process_id}`}
                  className="flex cursor-pointer items-start gap-3 rounded-md border p-3 font-normal hover:bg-muted/40"
                >
                  <RadioGroupItem id={`arquivar-${s.process_id}`} value={s.process_id} className="mt-0.5" />
                  <span className="flex-1">
                    <span className="block text-sm font-medium">{rotuloDoProcesso(s)}</span>
                    <span className="block text-xs text-muted-foreground">
                      {[s.status_label, s.motivo].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </Label>
              ))}
            </RadioGroup>

            {aviso && (
              <p role="note" className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
                {aviso}
              </p>
            )}

            {perguntaAPasta && (
              <div className="space-y-1.5">
                <Label htmlFor="arquivar-pasta" className="text-xs">
                  Pasta
                </Label>
                <Select value={categoria} onValueChange={setCategoria}>
                  <SelectTrigger id="arquivar-pasta" aria-label="Pasta de destino">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIAS_DE_ARQUIVO.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={arquivando}>
            Cancelar
          </Button>
          <Button
            type="button"
            data-testid="arquivar-confirmar"
            disabled={estado !== "pronto" || !escolhido || arquivando}
            onClick={() =>
              onConfirmar({
                processId,
                category: perguntaAPasta ? categoria : CATEGORIA_POR_OMISSAO,
              })
            }
          >
            {arquivando ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Archive className="mr-2 h-4 w-4" aria-hidden="true" />
            )}
            Arquivar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ArquivarNoProcessoDialog;
