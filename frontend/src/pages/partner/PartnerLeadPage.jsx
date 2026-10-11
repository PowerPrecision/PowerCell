/**
 * Submeter uma lead: os dados do cliente e a confirmação de que o parceiro
 * tem autorização para os partilhar.
 *
 * MARKETPLACE B2B: o parceiro é um agente livre. A primeira coisa que faz é
 * escolher a EMPRESA DE DESTINO entre as que têm Index (`obterDestinos`); sem
 * isso o resto do formulário está bloqueado e a lead não existe. Só depois de a
 * lead existir (já dirigida a essa empresa) se pede o Comprovativo de Pagamento,
 * que a envia para a fila dessa rede.
 *
 * O formulário só envia os campos que o servidor aceita
 * (`construirPayloadDaLead`). A rede, o estado e o autor são do servidor —
 * enviá-los seria um 422. A lead cai na triagem da equipa de destino; o
 * processo só nasce quando essa equipa o decide, e é aí que o caso passa de
 * «lead» a processo no painel do parceiro.
 */
import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePartnerAuth } from "@/contexts/PartnerAuthContext";
import { queryKeys } from "@/lib/queryClient";
import { obterDestinos, submeterLead } from "@/services/partnerApi";
import {
  LEAD_VAZIA,
  TIPOS_DE_PROCESSO,
  caminhoDoCaso,
  construirPayloadDaLead,
  mensagemDeErro,
  validarLead,
} from "@/utils/partnerPortal";

function Campo({ id, rotulo, erro, children }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{rotulo}</Label>
      {children}
      {erro && <p id={`${id}-erro`} role="alert" className="text-xs text-destructive">{erro}</p>}
    </div>
  );
}

export default function PartnerLeadPage() {
  usePartnerAuth();
  const queryClient = useQueryClient();
  const destinos = useQuery({ queryKey: queryKeys.partner.destinos(), queryFn: obterDestinos });
  const empresas = Array.isArray(destinos.data?.destinos) ? destinos.data.destinos : [];
  const [form, setForm] = useState(LEAD_VAZIA);
  const [erros, setErros] = useState({});
  const [erroGeral, setErroGeral] = useState("");
  const [aEnviar, setAEnviar] = useState(false);
  const [criada, setCriada] = useState(null);

  const mudar = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }));

  const submeter = async (e) => {
    e.preventDefault();
    if (aEnviar) return;
    const encontrados = validarLead(form);
    setErros(encontrados);
    setErroGeral("");
    if (Object.keys(encontrados).length > 0) return;

    setAEnviar(true);
    try {
      const resposta = await submeterLead(construirPayloadDaLead(form));
      setCriada({ ...resposta, empresa: empresas.find((e) => e.company_id === form.empresa_id)?.company_name || "" });
      setForm(LEAD_VAZIA);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.casosAll() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.painel() }),
      ]);
    } catch (falha) {
      setErroGeral(mensagemDeErro(falha, "Não foi possível submeter a lead."));
    } finally {
      setAEnviar(false);
    }
  };

  if (criada) {
    return (
      <Card className="mx-auto max-w-xl">
        <CardHeader>
          <CardTitle>{criada.repetida ? "Esta lead já tinha sido submetida" : "Lead criada — falta o comprovativo"}</CardTitle>
          <CardDescription data-testid="lead-criada-aviso">
            {criada.repetida
              ? "Submeteu os mesmos dados há instantes — não criámos uma segunda."
              : `Envie agora o Comprovativo de Pagamento: é ele que a faz seguir para a fila${criada.empresa ? ` de ${criada.empresa}` : " da empresa de destino"}. Até lá, a lead fica retida do seu lado.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button asChild><Link to={caminhoDoCaso(criada.id)}>Enviar o comprovativo</Link></Button>
          <Button type="button" variant="outline" onClick={() => setCriada(null)}>Submeter outra</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mx-auto max-w-xl">
      <CardHeader>
        <CardTitle>Novo lead</CardTitle>
        <CardDescription>Os dados do cliente que quer acompanhar connosco.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submeter} className="space-y-4" noValidate>
          <Campo id="lead-empresa" rotulo="1. Empresa de destino *" erro={erros.empresa_id}>
            <select
              id="lead-empresa" value={form.empresa_id}
              onChange={(e) => setForm((f) => ({ ...f, empresa_id: e.target.value }))}
              disabled={destinos.isPending}
              aria-invalid={Boolean(erros.empresa_id)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">{destinos.isPending ? "A carregar…" : "Escolha a empresa…"}</option>
              {empresas.map((e) => <option key={e.company_id} value={e.company_id}>{e.company_name}</option>)}
            </select>
            {destinos.isError && (
              <p role="alert" className="text-xs text-destructive" data-testid="destinos-erro">
                {mensagemDeErro(destinos.error, "Não foi possível carregar as empresas de destino.")}
              </p>
            )}
            {destinos.isSuccess && empresas.length === 0 && (
              <p className="text-xs text-muted-foreground" data-testid="sem-destinos">
                Não há empresas disponíveis para receber leads neste momento.
              </p>
            )}
            {!form.empresa_id && empresas.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Escolha primeiro a empresa que vai tratar do cliente: só depois pode preencher os dados e enviar o comprovativo.
              </p>
            )}
          </Campo>
          <fieldset disabled={!form.empresa_id} className="space-y-4 disabled:opacity-60" data-testid="dados-da-lead">
          <Campo id="lead-nome" rotulo="Nome do cliente *" erro={erros.name}>
            <Input id="lead-nome" value={form.name} onChange={mudar("name")} autoComplete="off" aria-invalid={Boolean(erros.name)} />
          </Campo>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo id="lead-email" rotulo="Email *" erro={erros.email}>
              <Input id="lead-email" type="email" value={form.email} onChange={mudar("email")} autoComplete="off" aria-invalid={Boolean(erros.email)} />
            </Campo>
            <Campo id="lead-telefone" rotulo="Telefone" erro={erros.phone}>
              <Input id="lead-telefone" type="tel" value={form.phone} onChange={mudar("phone")} autoComplete="off" />
            </Campo>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo id="lead-nif" rotulo="NIF" erro={erros.nif}>
              <Input id="lead-nif" inputMode="numeric" value={form.nif} onChange={mudar("nif")} autoComplete="off" aria-invalid={Boolean(erros.nif)} />
            </Campo>
            <Campo id="lead-tipo" rotulo="Tipo de processo">
              <select
                id="lead-tipo" value={form.process_type} onChange={mudar("process_type")}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                {TIPOS_DE_PROCESSO.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </Campo>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox id="lead-imovel" checked={form.has_property} onCheckedChange={(v) => setForm((f) => ({ ...f, has_property: v === true }))} />
            <Label htmlFor="lead-imovel" className="font-normal">O cliente já tem imóvel</Label>
          </div>

          <Campo id="lead-notas" rotulo="Notas para a equipa">
            <Textarea id="lead-notas" rows={3} maxLength={1000} value={form.notes} onChange={mudar("notes")} />
          </Campo>

          <div className="space-y-1">
            <div className="flex items-start gap-2">
              <Checkbox id="lead-consentimento" checked={form.consent_confirmed} onCheckedChange={(v) => setForm((f) => ({ ...f, consent_confirmed: v === true }))} />
              <Label htmlFor="lead-consentimento" className="text-sm font-normal leading-snug">
                Confirmo que tenho autorização do cliente para partilhar estes dados pessoais.
              </Label>
            </div>
            {erros.consent_confirmed && <p role="alert" className="text-xs text-destructive">{erros.consent_confirmed}</p>}
          </div>

          {erroGeral && (
            <Alert variant="destructive" role="alert"><AlertDescription>{erroGeral}</AlertDescription></Alert>
          )}
          <Button type="submit" disabled={aEnviar || !form.empresa_id}>{aEnviar ? "A submeter…" : "Submeter lead"}</Button>
          </fieldset>
        </form>
      </CardContent>
    </Card>
  );
}
