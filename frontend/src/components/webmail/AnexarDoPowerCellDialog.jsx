/**
 * «Anexar do PowerCell» — escolher, no compositor de email, ficheiros que já
 * estão nos documentos de um processo (e na pasta do cliente).
 *
 * Quando o email já está ligado a um processo, abre logo nos documentos dele;
 * senão, primeiro pesquisa-se o processo. O servidor é a parede: lista só o
 * que o utilizador pode ver (rede, pré-indexação, pasta Index) e volta a
 * validar cada caminho ao anexar — o ecrã não decide nada de segurança.
 *
 * Ao confirmar, o servidor COPIA os ficheiros para anexos temporários e
 * devolve-os no mesmo formato do upload; `onAnexados` junta-os à lista do
 * compositor e o envio segue pelo caminho de sempre (`attachment_ids`).
 */
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, FolderOpen, Loader2, Paperclip, Search } from "lucide-react";
import { toast } from "sonner";

import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import {
  attachDocumentsToEmail,
  getProcesses,
  listDocumentsForEmailAttachment,
} from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import useDebounce from "../../hooks/useDebounce";
import { formatFileSize, getAttachmentIcon } from "./webmailFormatters";

export const MAX_FICHEIROS = 10;

/** Agrupa a lista plana do servidor por pasta, mantendo a ordem dele. */
export function agruparPorPasta(ficheiros = []) {
  const grupos = new Map();
  for (const f of ficheiros) {
    const pasta = f.category || "Outros";
    if (!grupos.has(pasta)) grupos.set(pasta, []);
    grupos.get(pasta).push(f);
  }
  return Array.from(grupos.entries());
}

const rotulo = (p) =>
  [p?.client_name, p?.process_number ? `#${p.process_number}` : null]
    .filter(Boolean)
    .join(" · ") || "Processo";

/**
 * @param {object} props
 * @param {boolean} props.open
 * @param {(open: boolean) => void} props.onOpenChange
 * @param {string|null} [props.processId] Processo do email, quando já está ligado.
 * @param {(anexos: Array) => void} props.onAnexados
 */
const AnexarDoPowerCellDialog = ({ open, onOpenChange, processId = null, onAnexados }) => {
  const [processo, setProcesso] = useState(null); // { id, label }
  const [pesquisa, setPesquisa] = useState("");
  const [resultados, setResultados] = useState([]);
  const [aPesquisar, setAPesquisar] = useState(false);
  const [listagem, setListagem] = useState(null);
  const [estado, setEstado] = useState("parado"); // parado | a_carregar | pronto | erro
  const [erro, setErro] = useState("");
  const [seleccionados, setSeleccionados] = useState(() => new Set());
  const [anexando, setAnexando] = useState(false);
  const termo = useDebounce(pesquisa.trim(), 300);

  // Ao abrir: começa no processo do email (se houver); ao fechar, limpa tudo.
  useEffect(() => {
    if (open) {
      setProcesso(processId ? { id: processId, label: "" } : null);
    } else {
      setProcesso(null);
      setPesquisa("");
      setResultados([]);
      setListagem(null);
      setEstado("parado");
      setErro("");
      setSeleccionados(new Set());
    }
  }, [open, processId]);

  // Pesquisa de processos (só enquanto não há processo escolhido).
  useEffect(() => {
    if (!open || processo || termo.length < 2) {
      setResultados([]);
      return undefined;
    }
    let cancelado = false;
    setAPesquisar(true);
    getProcesses({ search: termo, size: 10 })
      .then(({ data }) => {
        if (cancelado) return;
        const itens = data?.items || data || [];
        setResultados(Array.isArray(itens) ? itens : []);
      })
      .catch(() => {
        if (!cancelado) setResultados([]);
      })
      .finally(() => {
        if (!cancelado) setAPesquisar(false);
      });
    return () => {
      cancelado = true;
    };
  }, [open, processo, termo]);

  // Ficheiros do processo escolhido.
  useEffect(() => {
    if (!open || !processo?.id) return undefined;
    let cancelado = false;
    setEstado("a_carregar");
    setErro("");
    setSeleccionados(new Set());
    listDocumentsForEmailAttachment(processo.id)
      .then(({ data }) => {
        if (cancelado) return;
        setListagem(data);
        setEstado("pronto");
      })
      .catch((e) => {
        if (cancelado) return;
        setErro(extractErrorMessage(e?.response?.data?.detail, "Não foi possível ler os documentos deste processo."));
        setEstado("erro");
      });
    return () => {
      cancelado = true;
    };
  }, [open, processo?.id]);

  const ficheiros = useMemo(() => listagem?.files || [], [listagem]);
  const grupos = useMemo(() => agruparPorPasta(ficheiros), [ficheiros]);
  const nomeDoProcesso = processo?.label || (listagem ? rotulo(listagem) : "");

  const alternar = (caminho) => {
    setSeleccionados((anterior) => {
      const novo = new Set(anterior);
      if (novo.has(caminho)) {
        novo.delete(caminho);
      } else if (novo.size < MAX_FICHEIROS) {
        novo.add(caminho);
      } else {
        toast.info(`Pode anexar até ${MAX_FICHEIROS} ficheiros de cada vez.`);
      }
      return novo;
    });
  };

  const confirmar = async () => {
    if (!processo?.id || seleccionados.size === 0) return;
    setAnexando(true);
    try {
      const { data } = await attachDocumentsToEmail(processo.id, Array.from(seleccionados));
      const anexos = data?.attachments || [];
      onAnexados(anexos);
      if (data?.errors?.length) {
        toast.warning(`Alguns ficheiros não foram anexados: ${data.errors.join("; ")}`);
      } else {
        toast.success(
          anexos.length === 1 ? "Ficheiro anexado" : `${anexos.length} ficheiros anexados`,
        );
      }
      onOpenChange(false);
    } catch (e) {
      toast.error(extractErrorMessage(e?.response?.data?.detail, "Não foi possível anexar os ficheiros."));
    } finally {
      setAnexando(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Anexar do PowerCell</DialogTitle>
          <DialogDescription>
            {processo
              ? "Escolha os documentos do processo a anexar ao email."
              : "Pesquise o processo de onde quer anexar documentos."}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-3">
          {!processo && (
            <>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  autoFocus
                  aria-label="Pesquisar processo"
                  placeholder="Nome do cliente, NIF ou nº de processo"
                  value={pesquisa}
                  onChange={(e) => setPesquisa(e.target.value)}
                  className="pl-8"
                />
              </div>
              {aPesquisar && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> A pesquisar...
                </div>
              )}
              {!aPesquisar && termo.length >= 2 && resultados.length === 0 && (
                <p className="text-sm text-muted-foreground">Nenhum processo encontrado.</p>
              )}
              <div className="space-y-1">
                {resultados.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setProcesso({ id: p.id, label: rotulo(p) })}
                    className="w-full text-left rounded-md border px-3 py-2 hover:bg-accent transition-colors"
                  >
                    <div className="text-sm font-medium">{p.client_name || "Sem nome"}</div>
                    <div className="text-xs text-muted-foreground">
                      {[p.process_number ? `#${p.process_number}` : null, p.client_email]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}

          {processo && (
            <>
              <div className="flex items-center gap-2">
                <FolderOpen className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-sm font-medium truncate flex-1">{nomeDoProcesso}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setProcesso(null);
                    setListagem(null);
                    setEstado("parado");
                  }}
                >
                  <ArrowLeft className="h-3.5 w-3.5 mr-1" />
                  Outro processo
                </Button>
              </div>

              {estado === "a_carregar" && (
                <div className="space-y-2" aria-label="A carregar documentos">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-3/4" />
                </div>
              )}

              {estado === "erro" && <p className="text-sm text-destructive">{erro}</p>}

              {estado === "pronto" && ficheiros.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  Este processo ainda não tem documentos que possa anexar.
                  {listagem?.em_indexacao
                    ? ` ${listagem.em_indexacao} ficheiro(s) a aguardar a Indexação.`
                    : ""}
                </p>
              )}

              {estado === "pronto" &&
                grupos.map(([pasta, lista]) => (
                  <div key={pasta} className="space-y-1">
                    <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {pasta}
                    </div>
                    {lista.map((f) => {
                      const Icone = getAttachmentIcon(f.name);
                      const marcado = seleccionados.has(f.path);
                      return (
                        <label
                          key={f.path}
                          className="flex items-center gap-2 rounded-md border px-2 py-1.5 cursor-pointer hover:bg-accent/50 transition-colors"
                        >
                          <Checkbox
                            checked={marcado}
                            onCheckedChange={() => alternar(f.path)}
                            aria-label={`Anexar ${f.name}`}
                          />
                          <Icone className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="flex-1 text-sm truncate" title={f.name}>
                            {f.name}
                          </span>
                          {f.size ? (
                            <span className="text-xs text-muted-foreground shrink-0">
                              {formatFileSize(f.size)}
                            </span>
                          ) : null}
                        </label>
                      );
                    })}
                  </div>
                ))}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={anexando}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={!processo || seleccionados.size === 0 || anexando}>
            {anexando ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Paperclip className="h-4 w-4 mr-2" />
            )}
            {seleccionados.size > 0 ? `Anexar (${seleccionados.size})` : "Anexar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default AnexarDoPowerCellDialog;
