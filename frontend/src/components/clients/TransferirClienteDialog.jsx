/**
 * TransferirClienteDialog — «Alterar Empresa» (só Master), a mover PROCESSOS do cliente.
 *
 * Reescrito no Lote 6. A regra de negócio: um cliente pode pertencer a várias empresas, e o que
 * transita de uma rede para a outra quando a triagem se enganou é o PROCESSO. O diálogo lista os
 * processos do cliente, deixa escolher quais mover e para que empresa; a ficha do cliente NÃO muda
 * e os ficheiros NÃO são movidos no armazenamento. O SERVIDOR exige a password actual e a conta
 * Master; este diálogo recolhe processos, destino e password (`ConfirmarComPasswordDialog`).
 *
 * @param {boolean}  open
 * @param {function} onOpenChange
 * @param {string}   clientId
 * @param {string}   [empresaActual]   nome da empresa da ficha do cliente (só informativo)
 * @param {function} [onSucesso]       chamada com a resposta do servidor
 */
import { useEffect, useState } from "react";
import { ArrowRightLeft } from "lucide-react";

import ConfirmarComPasswordDialog from "../admin/ConfirmarComPasswordDialog";
import { Label } from "../ui/label";
import { getAllCompanies, previewTransferClientCompany, transferClientCompany } from "../../services/api";
import { lerErroDeConfirmacao } from "../../utils/confirmarComPassword";

const TEXTOS_DE_ERRO = {
  naoEncontrado: "O cliente, o processo ou a empresa de destino já não existe.",
  recusado: "Não foi possível transferir os processos para esta empresa.",
};

const lerErro = (err) => lerErroDeConfirmacao(err, TEXTOS_DE_ERRO);

const rejeitar = (detail) => Promise.reject({ response: { status: 400, data: { detail } } });

function etiqueta(p) {
  const numero = p?.process_number ? `#${p.process_number}` : p?.id;
  const partes = [numero];
  if (p?.company_name) partes.push(p.company_name);
  if (p?.status) partes.push(p.status);
  return partes.join(" · ");
}

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
  // Os processos do cliente (com, dado um destino, quais já lá estão).
  const [processos, setProcessos] = useState([]);
  const [escolhidos, setEscolhidos] = useState([]);
  const [aCarregarProcessos, setACarregarProcessos] = useState(false);
  const [falhaNosProcessos, setFalhaNosProcessos] = useState(false);

  useEffect(() => {
    if (!open) {
      setDestino("");
      setProcessos([]);
      setEscolhidos([]);
      setFalhaNosProcessos(false);
      return undefined;
    }
    let cancelado = false;
    setACarregarProcessos(true);
    setFalhaNosProcessos(false);
    previewTransferClientCompany(clientId, destino || undefined)
      .then((res) => {
        if (cancelado) return;
        const lista = Array.isArray(res?.data?.processos) ? res.data.processos : [];
        setProcessos(lista);
        // Só sobrevive à escolha o que ainda se pode mover (o que já está no destino sai).
        setEscolhidos((actuais) => {
          const movíveis = new Set(lista.filter((p) => !p.ja_no_destino).map((p) => p.id));
          const mantidos = actuais.filter((id) => movíveis.has(id));
          // Um só processo: já vem escolhido (não há mais nada a decidir).
          return mantidos.length === 0 && lista.length === 1 && !lista[0].ja_no_destino
            ? [lista[0].id]
            : mantidos;
        });
      })
      .catch(() => {
        // Sem a lista não há o que escolher: diz-se, em vez de um diálogo que parece vazio.
        if (!cancelado) {
          setProcessos([]);
          setFalhaNosProcessos(true);
        }
      })
      .finally(() => {
        if (!cancelado) setACarregarProcessos(false);
      });
    return () => {
      cancelado = true;
    };
  }, [open, clientId, destino]);

  useEffect(() => {
    if (!open) return undefined;
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

  const alternar = (id) =>
    setEscolhidos((actuais) => (actuais.includes(id) ? actuais.filter((x) => x !== id) : [...actuais, id]));

  const possiveis = empresas.filter((e) => e?.id);
  const idDoCampo = "transferir-cliente-empresa";

  return (
    <ConfirmarComPasswordDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo="Alterar a empresa de processos do cliente"
      rotuloConfirmar="Transferir processos"
      Icone={ArrowRightLeft}
      testIdBase="transferir-cliente"
      confirmarDesactivado={escolhidos.length === 0}
      lerErro={lerErro}
      onConfirmar={(password) => {
        if (!destino) return rejeitar("Escolha a empresa de destino.");
        if (escolhidos.length === 0) return rejeitar("Escolha pelo menos um processo a transferir.");
        return transferClientCompany(clientId, destino, escolhidos, password);
      }}
      onSucesso={onSucesso}
      descricao={
        <>
          <p>
            Escolha os <strong>processos</strong> que passam para outra empresa (por exemplo, quando a
            triagem se enganou). O cliente{empresaActual ? <> (hoje em <strong>{empresaActual}</strong>)</> : null}{" "}
            <strong>não muda</strong>: pode ter processos em várias empresas.
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
          <ListaDeProcessos
            processos={processos}
            escolhidos={escolhidos}
            onAlternar={alternar}
            aCarregar={aCarregarProcessos}
            falhou={falhaNosProcessos}
          />
        </>
      }
    />
  );
}

/** Os processos do cliente, um a um, com a escolha de quais mover. */
function ListaDeProcessos({ processos, escolhidos, onAlternar, aCarregar, falhou }) {
  if (falhou) {
    return (
      <p role="alert" className="pt-2 text-xs text-destructive" data-testid="transferir-cliente-processos-falhou">
        Não foi possível carregar os processos do cliente. Feche e volte a abrir.
      </p>
    );
  }
  if (aCarregar && processos.length === 0) {
    return (
      <p className="pt-2 text-xs text-muted-foreground" data-testid="transferir-cliente-processos-a-carregar">
        A carregar os processos…
      </p>
    );
  }
  if (processos.length === 0) {
    return (
      <p className="pt-2 text-xs text-muted-foreground" data-testid="transferir-cliente-sem-processos">
        Este cliente não tem processos para transferir.
      </p>
    );
  }
  return (
    <fieldset className="space-y-1 pt-2" data-testid="transferir-cliente-processos">
      <legend className="text-sm font-medium">Processos a transferir</legend>
      {processos.map((p) => {
        const idDoProcesso = `transferir-processo-${p.id}`;
        return (
          <div key={p.id} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              id={idDoProcesso}
              className="mt-1"
              checked={escolhidos.includes(p.id)}
              disabled={Boolean(p.ja_no_destino)}
              onChange={() => onAlternar(p.id)}
            />
            <label htmlFor={idDoProcesso} className={p.ja_no_destino ? "text-muted-foreground" : undefined}>
              {etiqueta(p)}
              {p.terminado ? <span className="text-xs text-muted-foreground"> (terminado)</span> : null}
              {p.ja_no_destino ? (
                <span className="text-xs" data-testid={`transferir-processo-ja-no-destino-${p.id}`}>
                  {" "}
                  — já pertence à empresa escolhida
                </span>
              ) : null}
            </label>
          </div>
        );
      })}
    </fieldset>
  );
}
