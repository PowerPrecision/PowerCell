/**
 * PrevisualizadorDeFicheiro — o CORPO de uma pré-visualização (imagem ou PDF) dentro do ecrã.
 *
 * Serve a gaveta da lead e o «Ver documento» da pesquisa do Index: de onde vêm os bytes é problema de
 * quem o usa (`carregar`); como se desenham e como se falha é daqui, uma vez.
 *
 * Os bytes chegam por Axios (sessão e cabeçalhos de empresa) e viram um URL `blob:` local — nunca um URL
 * pré-assinado do bucket: o CSP só deixa `<iframe>` em `self` e `blob:`, e assim a chave S3 nem chega ao
 * browser. O URL é libertado ao fechar ou trocar de ficheiro (um `createObjectURL` esquecido segura o
 * ficheiro inteiro em memória). O tipo é o que o SERVIDOR declarou; só sem ele vale a extensão do nome.
 *
 * LIMITES: a área tem altura máxima e rola; um PDF de 40 páginas ou uma imagem de 4000 px não alargam
 * nem alongam o contentor. O servidor recusa acima de 15 MB.
 */
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { readBlobErrorBody } from "../../services/api";
import { safeString } from "../../utils/safeString";
import {
  mensagemDaFalhaDePrevisualizacao,
  tipoDaPrevisualizacao,
  tipoDaResposta,
} from "../../utils/previsualizacao";

/**
 * @param {Object} props
 * @param {string} props.chave — identifica o ficheiro: muda → recarrega (e liberta o anterior)
 * @param {() => Promise<{data: Blob, headers?: Object}>} props.carregar — o pedido (Axios, `responseType: blob`)
 * @param {string} props.nome — o que se mostra (e, sem tipo declarado, de onde se deduz o tipo)
 * @param {string} [props.alturaDoPdf="h-[60vh]"]
 * @param {string} [props.alturaMaxima="max-h-[60vh]"]
 */
export default function PrevisualizadorDeFicheiro({
  chave,
  carregar,
  nome,
  alturaDoPdf = "h-[60vh]",
  alturaMaxima = "max-h-[60vh]",
}) {
  const [url, setUrl] = useState("");
  const [tipo, setTipo] = useState(null);
  const [erro, setErro] = useState("");
  const [aCarregar, setACarregar] = useState(true);
  const rotulo = safeString(nome) || "ficheiro";

  useEffect(() => {
    if (!chave || typeof carregar !== "function") return undefined;
    let activo = true;
    let criado = "";
    setUrl("");
    setTipo(null);
    setErro("");
    setACarregar(true);
    carregar()
      .then((resposta) => {
        if (!activo) return;
        const doTipo = tipoDaResposta(resposta?.headers?.["content-type"]) || tipoDaPrevisualizacao(nome);
        if (!doTipo) {
          setErro(mensagemDaFalhaDePrevisualizacao(415));
          return;
        }
        // O tipo do Blob é o NOSSO: um blob sem o tipo certo faria o `<iframe>` descarregar em vez de mostrar.
        criado = URL.createObjectURL(new Blob([resposta.data], { type: doTipo.mime }));
        setTipo(doTipo);
        setUrl(criado);
      })
      .catch(async (e) => {
        if (!activo) return;
        const corpo = await readBlobErrorBody(e);
        if (activo) setErro(mensagemDaFalhaDePrevisualizacao(e?.response?.status, corpo?.detail));
      })
      .finally(() => {
        if (activo) setACarregar(false);
      });
    return () => {
      activo = false;
      if (criado) URL.revokeObjectURL(criado);
    };
    // `carregar` e `nome` acompanham a `chave`: quem chama não precisa de os memoizar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);

  return (
    <div className={`${alturaMaxima} max-w-full overflow-auto`} data-testid="previsualizacao-area">
      {aCarregar && (
        <p className="flex items-center gap-2 p-4 text-sm text-muted-foreground" role="status">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A carregar…
        </p>
      )}
      {erro && (
        <p role="alert" className="p-4 text-sm text-destructive" data-testid="previsualizacao-erro">
          {erro}
        </p>
      )}
      {url && tipo?.forma === "imagem" && (
        <img src={url} alt={`Pré-visualização de ${rotulo}`} className="mx-auto block h-auto max-w-full" data-testid="previsualizacao-imagem" />
      )}
      {url && tipo?.forma === "pdf" && (
        <iframe src={url} title={`Pré-visualização de ${rotulo}`} className={`block ${alturaDoPdf} w-full border-0`} data-testid="previsualizacao-pdf" />
      )}
    </div>
  );
}
