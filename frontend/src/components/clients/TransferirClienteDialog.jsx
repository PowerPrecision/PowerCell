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
import { getCompanies, transferClientCompany } from "../../services/api";
import { lerErroDeConfirmacao } from "../../utils/confirmarComPassword";

const TEXTOS_DE_ERRO = {
  naoEncontrado: "O cliente ou a empresa de destino já não existe.",
  recusado: "Não foi possível transferir o cliente para esta empresa.",
};

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

  useEffect(() => {
    if (!open) {
      setDestino("");
      return undefined;
    }
    let cancelado = false;
    setACarregar(true);
    setFalhaAoCarregar(false);
    getCompanies(undefined, { page: 1, size: 200 })
      .then((res) => {
        if (cancelado) return;
        const lista = res?.data?.empresas ?? res?.data?.companies ?? res?.data;
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
      lerErro={lerErro}
      onConfirmar={(password) => {
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
