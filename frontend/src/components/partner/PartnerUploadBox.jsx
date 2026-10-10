/**
 * A zona de envio de ficheiros do Portal do Parceiro.
 *
 * Serve os dois casos: responder a um PEDIDO de documentos (`requestId`) ou
 * enviar um ficheiro solto para o caso. O botão e o arrasto aceitam o MESMO
 * conjunto de tipos (`TIPOS_ACEITES_NO_PARCEIRO`: uma constante por
 * superfície, senão o botão recusa e o arrasto deixa passar), e a parede
 * real é a quarentena de magic bytes do servidor.
 *
 * O ficheiro NÃO escolhe a pasta: o parceiro pede, o servidor decide (por
 * indexar → `Index` e fila da IA). Quando o servidor diz que o ficheiro foi
 * para a fila, o ecrã di-lo — um envio que "desaparece" para a Indexação
 * sem uma palavra lê-se como falha.
 */
import React, { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import Dropzone from "@/components/shared/Dropzone";
import { queryKeys } from "@/lib/queryClient";
import { enviarFicheiro } from "@/services/partnerApi";
import { TIPOS_ACEITES_NO_PARCEIRO, mensagemDeErro } from "@/utils/partnerPortal";
import {
  A_ENVIAR,
  ENVIADO,
  FALHOU,
  criarLote,
  marcar,
  resumirLote,
} from "@/utils/portalUploadStaging";

export default function PartnerUploadBox({
  caseId,
  requestId,
  rotulo = "Enviar ficheiros",
  className = "",
  // Uma categoria FIXA (ex.: o Comprovativo de Pagamento) ou, com `categorias`,
  // um seletor — as MESMAS categorias do Portal do Cliente.
  categoria,
  categorias,
  desactivado = false,
  testId,
}) {
  const queryClient = useQueryClient();
  const entrada = useRef(null);
  const [lote, setLote] = useState([]);
  const [recusa, setRecusa] = useState("");
  const [aviso, setAviso] = useState("");
  const [aEnviar, setAEnviar] = useState(false);
  const [escolhida, setEscolhida] = useState("");
  const comSeletor = Array.isArray(categorias) && categorias.length > 0 && !requestId && !categoria;
  const categoriaFinal = categoria || (comSeletor ? escolhida : "");

  const enviar = async (ficheiros) => {
    if (!ficheiros?.length || aEnviar || desactivado) return;
    setAEnviar(true);
    setRecusa("");
    setAviso("");
    let actual = criarLote(ficheiros);
    setLote(actual);
    let foiParaIndexacao = false;
    let leadSubmetida = false;

    for (let i = 0; i < ficheiros.length; i += 1) {
      actual = marcar(actual, i, A_ENVIAR);
      setLote(actual);
      try {
        const resposta = await enviarFicheiro(caseId, ficheiros[i], {
          requestId,
          ...(categoriaFinal ? { category: categoriaFinal } : {}),
        });
        if (resposta?.destino?.fila_ia) foiParaIndexacao = true;
        if (resposta?.lead_submetida) leadSubmetida = true;
        actual = marcar(actual, i, ENVIADO);
      } catch (erro) {
        actual = marcar(actual, i, FALHOU, mensagemDeErro(erro, "Não foi possível enviar."));
      }
      setLote(actual);
    }

    if (leadSubmetida) {
      setAviso("Comprovativo recebido. A lead seguiu para a nossa equipa e fica a aguardar a validação financeira.");
    } else if (foiParaIndexacao) {
      setAviso("Recebido. O ficheiro segue para a análise da nossa equipa antes de ficar arquivado.");
    }
    // O detalhe, a lista e o painel mudaram (pedido satisfeito, contagens).
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.partner.caso(caseId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.partner.casosAll() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.partner.painel() }),
    ]);
    setAEnviar(false);
  };

  const resumo = resumirLote(lote);

  return (
    <Dropzone
      onFicheiros={enviar}
      onRecusados={(_r, mensagem) => setRecusa(mensagem)}
      accept={TIPOS_ACEITES_NO_PARCEIRO}
      disabled={aEnviar || desactivado}
      className={`rounded-md border border-dashed border-border p-3 ${className}`}
      testId={testId || (requestId ? `dropzone-${requestId}` : "dropzone-solto")}
    >
      {comSeletor && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <label htmlFor={`tipo-${caseId}`} className="text-sm font-medium">Tipo de documento</label>
          <select
            id={`tipo-${caseId}`}
            value={escolhida}
            onChange={(e) => setEscolhida(e.target.value)}
            disabled={aEnviar || desactivado}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          >
            <option value="">Sem categoria (a nossa equipa classifica)</option>
            {categorias.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={entrada}
          type="file"
          multiple
          className="hidden"
          accept={TIPOS_ACEITES_NO_PARCEIRO}
          aria-label={rotulo}
          data-testid={testId ? `input-${testId}` : requestId ? `input-${requestId}` : "input-solto"}
          onChange={(e) => {
            const escolhidos = Array.from(e.target.files || []);
            e.target.value = "";
            enviar(escolhidos);
          }}
        />
        <Button type="button" size="sm" variant="outline" disabled={aEnviar || desactivado} onClick={() => entrada.current?.click()}>
          {aEnviar ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="mr-2 h-4 w-4" aria-hidden="true" />}
          {aEnviar ? "A enviar…" : rotulo}
        </Button>
        <span className="text-xs text-muted-foreground">ou arraste os ficheiros para aqui (PDF, imagens, Word)</span>
      </div>

      {lote.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm" aria-label="Estado dos envios">
          {lote.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-2">
              <span className="truncate">{item.nome}</span>
              <span className={item.estado === FALHOU ? "text-destructive" : "text-muted-foreground"}>
                {item.estado === ENVIADO ? "Enviado" : item.estado === FALHOU ? item.erro : item.estado === A_ENVIAR ? "A enviar…" : "À espera"}
              </span>
            </li>
          ))}
        </ul>
      )}

      {recusa && <p role="alert" className="mt-2 text-sm text-destructive">{recusa}</p>}
      {resumo && resumo.tipo !== "sucesso" && <p role="alert" className="mt-2 text-sm text-destructive">{resumo.texto}</p>}
      {aviso && <p className="mt-2 text-sm text-muted-foreground">{aviso}</p>}
    </Dropzone>
  );
}
