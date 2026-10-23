/**
 * Diálogos das acções de gestão de um parceiro (menu «⋯» do separador Parceiros).
 *
 *  - Editar: nome e telefone (Admin/CEO/Master) e email (só Master — é a identidade de login).
 *  - Mudar de empresa: só Master.
 *  - Gerar nova palavra-passe: só Master; o servidor envia-a por email e só então a grava.
 *
 * (Eliminar usa o `ConfirmarComPasswordDialog` genérico, no separador.)
 *
 * O erro do servidor diz-se DENTRO do diálogo e o diálogo não fecha com ele; os dados escritos mantêm-se.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, Loader2 } from "lucide-react";

import { changePartnerCompany, getCompanies, resetPartnerPassword, updatePartner } from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { normalizeCompaniesPayload } from "../../utils/organizationAdmin";
import { corpoDaEdicao, formularioDeEdicao, nomesDasEmpresas, validarEdicao } from "../../utils/partnersAdmin";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

const mensagemDe = (e, recuo) => extractErrorMessage(e?.response?.data?.detail, recuo);

/** Estado comum: `a enviar`, erro do servidor, e uma função que corre o pedido e fecha só com sucesso. */
function useAccao(aoSucesso, aoFechar) {
  const [aEnviar, setAEnviar] = useState(false);
  const [erro, setErro] = useState("");
  const correr = async (pedido, recuo) => {
    if (aEnviar) return;
    setAEnviar(true);
    setErro("");
    try {
      const resposta = await pedido();
      aoSucesso?.(resposta?.data ?? resposta);
      aoFechar(false);
    } catch (e) {
      setErro(mensagemDe(e, recuo));
    } finally {
      setAEnviar(false);
    }
  };
  return { aEnviar, erro, setErro, correr };
}

export function EditarParceiroDialog({ parceiro, podeMudarEmail, onOpenChange, onSucesso }) {
  const [form, setForm] = useState(formularioDeEdicao(parceiro));
  const [erros, setErros] = useState({});
  const { aEnviar, erro, setErro, correr } = useAccao(onSucesso, onOpenChange);

  useEffect(() => {
    setForm(formularioDeEdicao(parceiro));
    setErros({});
    setErro("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parceiro?.id]);

  const submeter = (e) => {
    e.preventDefault();
    const encontrados = validarEdicao(form, { podeMudarEmail });
    setErros(encontrados);
    if (Object.keys(encontrados).length) return;
    const corpo = corpoDaEdicao(parceiro, form, { podeMudarEmail });
    if (!corpo) {
      onOpenChange(false);
      return;
    }
    correr(() => updatePartner(parceiro.id, corpo), "Não foi possível guardar as alterações");
  };

  const campo = (chave) => (e) => setForm((f) => ({ ...f, [chave]: e.target.value }));

  return (
    <Dialog open={Boolean(parceiro)} onOpenChange={(aberto) => !aEnviar && onOpenChange(aberto)}>
      <DialogContent data-testid="editar-parceiro-dialog">
        <form onSubmit={submeter} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>Editar parceiro</DialogTitle>
            <DialogDescription>
              {podeMudarEmail
                ? "Mudar o email muda o login do parceiro: as sessões abertas terminam e um convite pendente passa para o novo endereço."
                : "O email só pode ser alterado pelo perfil Master."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="editar-parceiro-nome">Nome *</Label>
            <Input id="editar-parceiro-nome" value={form.name} onChange={campo("name")} disabled={aEnviar} />
            {erros.name && <p role="alert" className="text-xs text-destructive">{erros.name}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="editar-parceiro-email">Email</Label>
            <Input
              id="editar-parceiro-email" type="email" value={form.email} onChange={campo("email")}
              disabled={!podeMudarEmail || aEnviar} readOnly={!podeMudarEmail}
            />
            {erros.email && <p role="alert" className="text-xs text-destructive">{erros.email}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="editar-parceiro-telefone">Telefone</Label>
            <Input id="editar-parceiro-telefone" type="tel" value={form.phone} onChange={campo("phone")} disabled={aEnviar} />
          </div>
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="editar-parceiro-erro">{erro}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={aEnviar}>Cancelar</Button>
            <Button type="submit" disabled={aEnviar}>{aEnviar ? "A guardar…" : "Guardar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function MudarEmpresaDialog({ parceiro, onOpenChange, onSucesso }) {
  const [empresa, setEmpresa] = useState("");
  const { aEnviar, erro, setErro, correr } = useAccao(onSucesso, onOpenChange);

  const empresas = useQuery({
    queryKey: queryKeys.orgAdmin.companiesSelector(),
    queryFn: async () => normalizeCompaniesPayload((await getCompanies()).data),
    enabled: Boolean(parceiro),
  });

  useEffect(() => {
    setEmpresa("");
    setErro("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parceiro?.id]);

  return (
    <Dialog open={Boolean(parceiro)} onOpenChange={(aberto) => !aEnviar && onOpenChange(aberto)}>
      <DialogContent data-testid="mudar-empresa-parceiro-dialog">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (empresa) correr(() => changePartnerCompany(parceiro.id, empresa), "Não foi possível mudar a empresa");
          }}
        >
          <DialogHeader>
            <DialogTitle>Mudar empresa</DialogTitle>
            <DialogDescription>
              {parceiro?.name} está em <strong>{nomesDasEmpresas(parceiro || {})}</strong>. A ligação de gestão passa
              para a empresa escolhida (as redes que o próprio parceiro escolheu como destino mantêm-se). A equipa
              da empresa anterior deixa de o gerir e de ver os casos dele.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="mudar-empresa-parceiro">Nova empresa</Label>
            <select
              id="mudar-empresa-parceiro" value={empresa} onChange={(e) => setEmpresa(e.target.value)} disabled={aEnviar}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Escolha a empresa…</option>
              {(empresas.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {empresas.isError && (
              <p role="alert" className="text-xs text-destructive">Não foi possível carregar as empresas.</p>
            )}
          </div>
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="mudar-empresa-erro">{erro}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={aEnviar}>Cancelar</Button>
            <Button type="submit" disabled={!empresa || aEnviar}>
              {aEnviar ? "A mudar…" : "Mudar empresa"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function NovaPasswordDialog({ parceiro, onOpenChange, onSucesso }) {
  const { aEnviar, erro, setErro, correr } = useAccao(onSucesso, onOpenChange);

  useEffect(() => {
    setErro("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parceiro?.id]);

  return (
    <Dialog open={Boolean(parceiro)} onOpenChange={(aberto) => !aEnviar && onOpenChange(aberto)}>
      <DialogContent data-testid="nova-password-parceiro-dialog">
        <DialogHeader>
          <DialogTitle>Gerar nova palavra-passe</DialogTitle>
          <DialogDescription>
            É gerada uma palavra-passe aleatória e enviada por email para <strong>{parceiro?.email}</strong>. A
            actual deixa de funcionar e as sessões abertas terminam. Só é gravada se o email sair.
          </DialogDescription>
        </DialogHeader>
        {erro && <p role="alert" className="text-sm text-destructive" data-testid="nova-password-erro">{erro}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={aEnviar}>Cancelar</Button>
          <Button
            type="button" disabled={aEnviar}
            onClick={() => correr(() => resetPartnerPassword(parceiro.id), "Não foi possível gerar a palavra-passe")}
          >
            {aEnviar
              ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
              : <KeyRound className="mr-2 h-4 w-4" aria-hidden="true" />}
            Gerar e enviar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
