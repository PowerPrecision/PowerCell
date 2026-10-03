/**
 * Religamento manual de pastas S3 — a válvula humana (Lote 6, ponto 2).
 *
 * PORQUE É QUE ISTO EXISTE
 * ========================
 * A identidade da pasta documental passou a derivar do ID, e o automatismo
 * deixou de adivinhar: quando não sabe, RECUSA (o auto-mapeamento reporta a
 * pasta como ambígua em vez de escolher uma ficha à sorte). Isso está certo e
 * deixa em aberto o que só uma pessoa resolve:
 *
 *   * o mapeamento aponta para a pasta legada ERRADA — a colisão que deu
 *     origem a este lote;
 *   * duas fichas partilham a mesma pasta e é preciso separar uma (D-19);
 *   * um `rename` antigo deixou a ligação partida;
 *   * uma pasta nova aparece como uuid e quer-se consolidá-la numa pasta
 *     existente que já tem histórico.
 *
 * O QUE ESTE ECRÃ FAZ DE DIFERENTE DO BLOCO ACIMA
 * ===============================================
 * O bloco "Mapeamento Clientes/Processos" só conhece PROCESSOS. Este cobre
 * também os CLIENTES — e um cliente da Pool que nunca teve processo é
 * exactamente quem vive sozinho na raiz documental.
 *
 * TRÊS DECISÕES DE ECRÃ
 * =====================
 * 1. **Carrega a pedido.** A listagem varre duas colecções e o bucket; abrir a
 *    página de Manutenção não tem de pagar isso.
 * 2. **O `<select>` é NATIVO**, como o do bloco acima: a lista de pastas pode
 *    ter milhares de entradas e um combobox com portal não é melhor nisso.
 * 3. **O aviso de partilha aparece como `toast.warning` e fica na linha.**
 *    Consolidar duas fichas na mesma pasta é legítimo; quem o faz tem de ver
 *    que vai partilhar, e não só no instante do clique.
 */
import React, { useCallback, useState } from "react";
import { AlertTriangle, FolderSearch, Loader2, RefreshCw, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { extractErrorMessage } from "@/utils/extractErrorMessage";
import { getS3Relink, setS3Relink } from "@/services/api";
import { nomeVisivel, temColisao } from "@/utils/pastaS3";

const ROTULO_DO_TIPO = { processo: "Processo", cliente: "Cliente" };

const SEM_MAPEAMENTO = "__sem_mapeamento__";

const S3RelinkPanel = () => {
  const [dados, setDados] = useState(null);
  const [aCarregar, setACarregar] = useState(false);
  const [aGravar, setAGravar] = useState(null);
  const [escolhas, setEscolhas] = useState({});
  const [avisos, setAvisos] = useState({});
  const [pesquisa, setPesquisa] = useState("");
  const [tipo, setTipo] = useState("");
  const [apenasPorResolver, setApenasPorResolver] = useState(false);

  const carregar = useCallback(async () => {
    setACarregar(true);
    try {
      const { data } = await getS3Relink({
        search: pesquisa || undefined,
        tipo: tipo || undefined,
        apenas_por_resolver: apenasPorResolver,
        limit: 100,
      });
      setDados(data);
      setEscolhas({});
    } catch (erro) {
      toast.error(
        extractErrorMessage(
          erro?.response?.data?.detail,
          "Erro ao carregar o religamento"
        )
      );
    } finally {
      setACarregar(false);
    }
  }, [pesquisa, tipo, apenasPorResolver]);

  const chave = (entidade) => `${entidade.tipo}:${entidade.id}`;

  const gravar = async (entidade) => {
    const k = chave(entidade);
    const escolhida = escolhas[k];
    const nova = escolhida === SEM_MAPEAMENTO ? "" : escolhida;
    setAGravar(k);
    try {
      const { data } = await setS3Relink({
        tipo: entidade.tipo,
        entityId: entidade.id,
        s3Folder: nova,
      });
      toast.success(
        nova
          ? `Pasta religada para ${data.nome || entidade.id}`
          : `Mapeamento removido de ${data.nome || entidade.id}`
      );
      if (data.aviso) {
        toast.warning(data.aviso);
        setAvisos((a) => ({ ...a, [k]: data.aviso }));
      } else {
        setAvisos((a) => ({ ...a, [k]: "" }));
      }
      await carregar();
    } catch (erro) {
      toast.error(
        extractErrorMessage(
          erro?.response?.data?.detail,
          "Erro ao religar a pasta"
        )
      );
    } finally {
      setAGravar(null);
    }
  };

  const entidades = dados?.entidades || [];
  const pastas = dados?.pastas || [];

  return (
    <div
      className="border rounded-lg p-4 border-border bg-muted/30"
      data-testid="painel-religamento"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h4 className="font-medium flex items-center gap-2">
            <FolderSearch className="h-4 w-4 text-muted-foreground" />
            Religamento manual (clientes e processos)
          </h4>
          <p className="text-sm text-muted-foreground">
            Aponta a pasta de documentos de uma ficha para outra pasta. Cobre
            também clientes sem processo — e é aqui que se resolvem as pastas
            partilhadas por duas fichas.
          </p>
        </div>
        <Button variant="outline" onClick={carregar} disabled={aCarregar}>
          {aCarregar ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          {dados ? "Actualizar" : "Carregar"}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Input
          className="max-w-xs"
          placeholder="Pesquisar por nome…"
          value={pesquisa}
          onChange={(e) => setPesquisa(e.target.value)}
          aria-label="Pesquisar por nome"
        />
        <select
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
          aria-label="Tipo de ficha"
        >
          <option value="">Clientes e processos</option>
          <option value="cliente">Só clientes</option>
          <option value="processo">Só processos</option>
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={apenasPorResolver}
            onChange={(e) => setApenasPorResolver(e.target.checked)}
          />
          Apenas sem pasta
        </label>
      </div>

      {dados && (
        <>
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground mb-3">
            <span>{dados.stats?.total ?? 0} fichas</span>
            <span>{dados.stats?.sem_pasta ?? 0} sem pasta</span>
            <span>{dados.stats?.por_id ?? 0} em pasta por id</span>
            <span>{pastas.length} pastas no bucket</span>
          </div>

          {entidades.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma ficha corresponde a estes filtros.
            </p>
          ) : (
            <div className="space-y-2 max-h-[28rem] overflow-y-auto">
              {entidades.map((entidade) => {
                const k = chave(entidade);
                const escolhida = escolhas[k];
                const alterou =
                  escolhida !== undefined &&
                  (escolhida === SEM_MAPEAMENTO
                    ? Boolean(entidade.s3_folder)
                    : escolhida !== entidade.s3_folder);
                return (
                  <div
                    key={k}
                    className="flex flex-wrap items-center gap-2 border-b pb-2"
                    data-testid={`linha-${k}`}
                  >
                    <Badge variant="outline" className="text-[10px]">
                      {ROTULO_DO_TIPO[entidade.tipo] || entidade.tipo}
                    </Badge>
                    <span className="text-sm font-medium min-w-[12rem]">
                      {entidade.nome || `(sem nome) ${entidade.id}`}
                    </span>
                    <span
                      className="text-xs text-muted-foreground font-mono truncate max-w-[18rem]"
                      title={entidade.s3_folder || "sem pasta"}
                    >
                      {entidade.s3_folder || "— sem pasta —"}
                    </span>
                    {entidade.pasta_por_id && (
                      <Badge variant="secondary" className="text-[10px]">
                        pasta por id
                      </Badge>
                    )}
                    <select
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm flex-1 min-w-[14rem]"
                      value={escolhida ?? entidade.s3_folder ?? SEM_MAPEAMENTO}
                      onChange={(e) =>
                        setEscolhas((c) => ({ ...c, [k]: e.target.value }))
                      }
                      aria-label={`Pasta de ${entidade.nome || entidade.id}`}
                    >
                      <option value={SEM_MAPEAMENTO}>— remover mapeamento —</option>
                      {pastas.map((pasta) => (
                        <option key={pasta.path} value={pasta.path}>
                          {nomeVisivel(pasta)}
                          {temColisao(pasta)
                            ? ` (${pasta.nomes_dos_clientes.length} fichas)`
                            : ""}
                          {pasta.orfa ? " (órfã)" : ""}
                        </option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      onClick={() => gravar(entidade)}
                      disabled={!alterou || aGravar === k}
                    >
                      {aGravar === k ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4" />
                      )}
                      <span className="sr-only">
                        Guardar pasta de {entidade.nome || entidade.id}
                      </span>
                    </Button>
                    {avisos[k] && (
                      <p className="w-full text-xs text-amber-600 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {avisos[k]}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default S3RelinkPanel;
