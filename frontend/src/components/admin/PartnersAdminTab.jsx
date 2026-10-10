/**
 * Separador Parceiros — convidar e gerir os parceiros de negócio da rede.
 *
 * Liga a GET /admin/partners, POST /admin/partners/invite, PATCH
 * /admin/partners/{id} e POST /admin/partners/{id}/resend-invite.
 *
 * O ONBOARDING É SÓ POR CONVITE: não há registo público. O link do convite
 * aparece UMA vez, a quem convida (o servidor só guarda o hash) — se o email
 * falhar, copia-se daqui. Admin e CEO só vêem e gerem os parceiros da SUA
 * rede; um parceiro de outra rede é «não existe» (a parede está no servidor).
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2, MailPlus, RefreshCw, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { getCompanies, getPartners, invitePartner, resendPartnerInvite, updatePartner } from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { normalizeCompaniesPayload } from "../../utils/organizationAdmin";
import {
  CONVITE_VAZIO,
  corpoDoConvite,
  estadoDoParceiro,
  linkDoConvite,
  nomesDasEmpresas,
  normalizarParceiros,
  podeSuspender,
  validarConvite,
} from "../../utils/partnersAdmin";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import EmptyState from "../ui/EmptyState";

function LinkDoConvite({ caminho }) {
  const link = linkDoConvite(caminho, typeof window !== "undefined" ? window.location.origin : "");
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(link);
      toast.success("Link copiado");
    } catch {
      toast.error("Não foi possível copiar — seleccione o link e copie à mão.");
    }
  };
  return (
    <div className="space-y-2 rounded-md border border-border bg-secondary p-3" data-testid="link-do-convite">
      <p className="text-sm font-medium">Link do convite (uso único, válido 7 dias)</p>
      <div className="flex items-center gap-2">
        <Input readOnly value={link} aria-label="Link do convite" onFocus={(e) => e.target.select()} />
        <Button type="button" size="sm" variant="outline" onClick={copiar}>
          <Copy className="mr-1 h-4 w-4" aria-hidden="true" />Copiar
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">Foi enviado por email. Este link só aparece agora — gere um novo se o perder.</p>
    </div>
  );
}

export default function PartnersAdminTab() {
  const queryClient = useQueryClient();
  const [aConvidar, setAConvidar] = useState(false);
  const [form, setForm] = useState(CONVITE_VAZIO);
  const [erros, setErros] = useState({});
  const [erroGeral, setErroGeral] = useState("");
  const [ultimoConvite, setUltimoConvite] = useState(null);

  const parceiros = useQuery({
    queryKey: queryKeys.orgAdmin.partners(),
    queryFn: async () => normalizarParceiros((await getPartners()).data),
  });

  const empresas = useQuery({
    // A MESMA chave e a mesma forma do selector do separador Utilizadores.
    queryKey: queryKeys.orgAdmin.companiesSelector(),
    queryFn: async () => normalizeCompaniesPayload((await getCompanies()).data),
    enabled: aConvidar,
  });

  const recarregar = () => queryClient.invalidateQueries({ queryKey: queryKeys.orgAdmin.partners() });

  const convidar = useMutation({
    mutationFn: async (corpo) => (await invitePartner(corpo)).data,
    onSuccess: (dados) => {
      setUltimoConvite({ caminho: dados.invite_path, nome: dados.partner?.name });
      setForm(CONVITE_VAZIO);
      setErroGeral("");
      toast.success("Convite criado");
      recarregar();
    },
    onError: (e) => setErroGeral(extractErrorMessage(e?.response?.data?.detail, "Não foi possível criar o convite")),
  });

  const reenviar = useMutation({
    mutationFn: async (id) => (await resendPartnerInvite(id)).data,
    onSuccess: (dados, id) => {
      const p = (parceiros.data || []).find((x) => x.id === id);
      setUltimoConvite({ caminho: dados.invite_path, nome: p?.name });
      toast.success("Novo convite criado");
      recarregar();
    },
    onError: (e) => toast.error(extractErrorMessage(e?.response?.data?.detail, "Não foi possível reenviar o convite")),
  });

  const suspender = useMutation({
    mutationFn: async ({ id, suspended }) => (await updatePartner(id, { suspended })).data,
    onSuccess: (_d, { suspended }) => {
      toast.success(suspended ? "Parceiro suspenso" : "Parceiro reactivado");
      recarregar();
    },
    onError: (e) => toast.error(extractErrorMessage(e?.response?.data?.detail, "Não foi possível actualizar o parceiro")),
  });

  const abrir = () => {
    setForm(CONVITE_VAZIO);
    setErros({});
    setErroGeral("");
    setUltimoConvite(null);
    setAConvidar(true);
  };

  const submeter = (e) => {
    e.preventDefault();
    const encontrados = validarConvite(form);
    setErros(encontrados);
    if (Object.keys(encontrados).length > 0) return;
    convidar.mutate(corpoDoConvite(form));
  };

  const lista = parceiros.data || [];

  return (
    <div className="space-y-4" data-testid="partners-admin-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Os parceiros entram só por convite. Cada um vê apenas os processos que lhe forem atribuídos.
        </p>
        <Button type="button" onClick={abrir}><UserPlus className="mr-2 h-4 w-4" aria-hidden="true" />Convidar parceiro</Button>
      </div>

      {ultimoConvite && !aConvidar && (
        <div className="space-y-1">
          {ultimoConvite.nome && <p className="text-sm">Convite para <strong>{ultimoConvite.nome}</strong>:</p>}
          <LinkDoConvite caminho={ultimoConvite.caminho} />
        </div>
      )}

      {parceiros.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A carregar…
        </p>
      ) : parceiros.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {extractErrorMessage(parceiros.error?.response?.data?.detail, "Não foi possível carregar os parceiros")}
        </p>
      ) : lista.length === 0 ? (
        <EmptyState icon={MailPlus} title="Ainda não há parceiros" description="Convide o primeiro parceiro para começar." />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Empresa</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="text-right">Acções</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lista.map((p) => {
              const estado = estadoDoParceiro(p);
              const activo = podeSuspender(p);
              return (
                <TableRow key={p.id} data-testid={`parceiro-${p.id}`}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell>{p.email}</TableCell>
                  <TableCell>{nomesDasEmpresas(p)}</TableCell>
                  <TableCell><Badge variant={estado.variant}>{estado.rotulo}</Badge></TableCell>
                  <TableCell className="space-x-1 text-right">
                    <Button
                      type="button" size="sm" variant="ghost" disabled={reenviar.isPending}
                      onClick={() => reenviar.mutate(p.id)} aria-label={`Novo convite para ${p.name}`}
                    >
                      <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button
                      type="button" size="sm" variant="outline" disabled={suspender.isPending}
                      onClick={() => suspender.mutate({ id: p.id, suspended: activo })}
                    >
                      {activo ? "Suspender" : "Reactivar"}
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      <Dialog open={aConvidar} onOpenChange={setAConvidar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Convidar parceiro</DialogTitle>
            <DialogDescription>
              O parceiro recebe um link por email para definir a palavra-passe. Fica ligado à empresa que escolher.
            </DialogDescription>
          </DialogHeader>

          {ultimoConvite ? (
            <LinkDoConvite caminho={ultimoConvite.caminho} />
          ) : (
            <form id="form-convidar-parceiro" onSubmit={submeter} className="space-y-3" noValidate>
              <div className="space-y-1">
                <Label htmlFor="parceiro-nome">Nome *</Label>
                <Input id="parceiro-nome" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
                {erros.name && <p role="alert" className="text-xs text-destructive">{erros.name}</p>}
              </div>
              <div className="space-y-1">
                <Label htmlFor="parceiro-email">Email *</Label>
                <Input id="parceiro-email" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
                {erros.email && <p role="alert" className="text-xs text-destructive">{erros.email}</p>}
              </div>
              <div className="space-y-1">
                <Label htmlFor="parceiro-telefone">Telefone</Label>
                <Input id="parceiro-telefone" type="tel" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="parceiro-empresa">Empresa *</Label>
                <select
                  id="parceiro-empresa" value={form.company_id}
                  onChange={(e) => setForm((f) => ({ ...f, company_id: e.target.value }))}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="">Escolha…</option>
                  {(empresas.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {erros.company_id && <p role="alert" className="text-xs text-destructive">{erros.company_id}</p>}
              </div>
              {erroGeral && <p role="alert" className="text-sm text-destructive">{erroGeral}</p>}
            </form>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAConvidar(false)}>{ultimoConvite ? "Fechar" : "Cancelar"}</Button>
            {!ultimoConvite && (
              <Button type="submit" form="form-convidar-parceiro" disabled={convidar.isPending}>
                {convidar.isPending ? "A criar…" : "Criar convite"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
