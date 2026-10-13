/**
 * TransferirClienteDialog — «Alterar Empresa» de um cliente (só Master).
 *
 * Um cliente registado na empresa errada não tinha como ser movido. Esta acção muda o carimbo
 * (empresa e rede) do cliente e dos processos dele — e NÃO mexe no S3: os ficheiros ficam
 * onde estão, só muda quem os vê. O SERVIDOR exige a password actual e a conta Master; este
 * diálogo recolhe a empresa de destino e a password (`ConfirmarComPasswordDialog`).
 *
 * @param {boolean}  open
 * @param {function} onOpenChange
 * @param {string}   clientId
 * @param {string}   [empresaActual]   nome da empresa onde o cliente está (não é destino)
 * @param {function} [onSucesso]       chamada com a resposta do servidor
 */
import { useEffect, useState } from "react";
import { ArrowRightLeft } from "lucide-react";

import ConfirmarComPasswordDialog from "../admin/ConfirmarComPasswordDialog";
import { Label } from "../ui/label";
import { getAllCompanies, previewTransferClientCompany, transferClientCompany } from "../../services/api";
import { lerErroDeConfirmacao } from "../../utils/confirmarComPassword";

const TEXTOS_DE_ERRO = {
  naoEncontrado: "O cliente ou a empresa de destino já não existe.",
  recusado: "Não foi possível transferir o cliente para esta empresa.",
};

const MENSAGEM_BLOQUEADO =
  "O cliente é titular de processos activos noutra empresa. Resolva-os antes de o transferir.";

const lerErro = (err) => lerErroDeConfirmacao(err, TEXTOS_DE_ERRO);

export default function TransferirClienteDialog({
  open,
  onOpenChange,
  clientId,
  empresaActual,
  onSucesso,
}) {
  const [empresas, setEmpresas] = useState([]);
  const [destino, setDestino] = useState("");
  const [aCarregar, setACarregar] = useState(false);
  const [falhaAoCarregar, setFalhaAoCarregar] = useState(false);
  // O que a transferência faria para o destino escolhido (processos a mover / mantidos / que impedem).
  const [previa, setPrevia] = useState(null);
  const [aCalcularPrevia, setACalcularPrevia] = useState(false);

  useEffect(() => {
    if (!destino || !open) {
      setPrevia(null);
      return undefined;
    }
    let cancelado = false;
    setACalcularPrevia(true);
    previewTransferClientCompany(clientId, destino)
      .then((res) => {
        if (!cancelado) setPrevia(res?.data ?? null);
      })
      .catch(() => {
        // Sem prévia não se bloqueia aqui: o servidor recusa o que não puder fazer.
        if (!cancelado) setPrevia(null);
      })
      .finally(() => {
        if (!cancelado) setACalcularPrevia(false);
      });
    return () => {
      cancelado = true;
    };
  }, [destino, open, clientId]);

  useEffect(() => {
    if (!open) {
      setDestino("");
      return undefined;
    }
    let cancelado = false;
    setACarregar(true);
    setFalhaAoCarregar(false);
    // Todas as páginas: a API limita `size` a 100 e pedir 200 dava 422 (Lote 4).
    getAllCompanies()
      .then((lista) => {
        if (cancelado) return;
        setEmpresas(Array.isArray(lista) ? lista : []);
      })
      .catch(() => {
        if (!cancelado) setFalhaAoCarregar(true);
      })
      .finally(() => {
        if (!cancelado) setACarregar(false);
      });
    return () => {
      cancelado = true;
    };
  }, [open]);

  const possiveis = empresas.filter((e) => e?.id && e.name !== empresaActual);
  const idDoCampo = "transferir-cliente-empresa";

  return (
    <ConfirmarComPasswordDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo="Alterar a empresa do cliente"
      rotuloConfirmar="Transferir cliente"
      Icone={ArrowRightLeft}
      testIdBase="transferir-cliente"
      confirmarDesactivado={Boolean(previa?.bloqueado)}
      lerErro={lerErro}
      onConfirmar={(password) => {
        if (previa?.bloqueado) {
          return Promise.reject({ response: { status: 409, data: { detail: MENSAGEM_BLOQUEADO } } });
        }
        if (!destino) {
          return Promise.reject({ response: { status: 400, data: { detail: "Escolha a empresa de destino." } } });
        }
        return transferClientCompany(clientId, destino, password);
      }}
      onSucesso={onSucesso}
      descricao={
        <>
          <p>
            O cliente{empresaActual ? <> (hoje em <strong>{empresaActual}</strong>)</> : null} e os processos
            de que é titular passam a pertencer à empresa escolhida — e deixam de ser vistos pela
            empresa de origem.
          </p>
          <p>
            Os ficheiros <strong>não são movidos</strong> no armazenamento: ficam na mesma pasta.
          </p>
          <div className="space-y-1 pt-1">
            <Label htmlFor={idDoCampo}>Empresa de destino</Label>
            <select
              id={idDoCampo}
              data-testid="transferir-cliente-empresa"
              value={destino}
              onChange={(e) => setDestino(e.target.value)}
              disabled={aCarregar || falhaAoCarregar}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
            >
              <option value="">{aCarregar ? "A carregar empresas…" : "Escolha uma empresa"}</option>
              {possiveis.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
            {destino && aCalcularPrevia && (
              <p className="text-xs text-muted-foreground" data-testid="transferir-cliente-previa-a-carregar">
                A calcular o que será movido…
              </p>
            )}
            {previa && !aCalcularPrevia && <PreviaDaTransferencia previa={previa} />}
            {falhaAoCarregar && (
              <p role="alert" className="text-xs text-destructive">
                Não foi possível carregar as empresas. Feche e volte a abrir.
              </p>
            )}
          </div>
        </>
      }
    />
  );
}


function etiqueta(p) {
  const numero = p?.process_number ? `#${p.process_number}` : p?.id;
  return `${numero}${p?.company_name ? ` · ${p.company_name}` : ""}`;
}

/** O que vai acontecer aos processos do cliente — dito antes de pedir a password. */
function PreviaDaTransferencia({ previa }) {
  const impedem = previa.processos_que_impedem || [];
  const mantidos = previa.processos_mantidos || [];
  return (
    <div className="space-y-1 pt-1 text-xs" data-testid="transferir-cliente-previa">
      <p>
        <strong>{previa.processos_a_mover}</strong> processo(s) acompanham o cliente.
      </p>
      {mantidos.length > 0 && (
        <p className="text-muted-foreground" data-testid="transferir-cliente-previa-mantidos">
          Ficam na empresa onde estão (já terminados): {mantidos.map(etiqueta).join("; ")}.
        </p>
      )}
      {impedem.length > 0 && (
        <p role="alert" className="text-destructive" data-testid="transferir-cliente-previa-bloqueio">
          Não é possível transferir: o cliente é titular de processo(s) activo(s) noutra empresa —{" "}
          {impedem.map(etiqueta).join("; ")}. Resolva-os primeiro.
        </p>
      )}
    </div>
  );
}
