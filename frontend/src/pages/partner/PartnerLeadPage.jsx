/**
 * Submeter uma lead: os dados do cliente e a confirmação de que o parceiro
 * tem autorização para os partilhar.
 *
 * O formulário só envia os campos que o servidor aceita
 * (`construirPayloadDaLead`). A rede, a empresa, o estado e o autor são do
 * servidor — enviá-los seria um 422. A lead cai na triagem da equipa; o
 * processo só nasce quando a equipa o decide, e é aí que o caso passa de
 * «lead» a processo no painel do parceiro.
 */
import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
import { submeterLead } from "@/services/partnerApi";
import {
  LEAD_VAZIA,
  TIPOS_DE_PROCESSO,
  caminhoDoCaso,
  construirPayloadDaLead,
  mensagemDeErro,
  redesActivas,
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
  const { partner } = usePartnerAuth();
  const queryClient = useQueryClient();
  const redes = redesActivas(partner);
  const [form, setForm] = useState(LEAD_VAZIA);
  const [rede, setRede] = useState("");
  const [erros, setErros] = useState({});
  const [erroGeral, setErroGeral] = useState("");
  const [aEnviar, setAEnviar] = useState(false);
  const [criada, setCriada] = useState(null);

  const mudar = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }));

  const submeter = async (e) => {
    e.preventDefault();
    if (aEnviar) return;
    const encontrados = validarLead(form);
    if (redes.length > 1 && !rede) encontrados.rede = "Escolha a rede a que esta lead se destina.";
    setErros(encontrados);
    setErroGeral("");
    if (Object.keys(encontrados).length > 0) return;

    setAEnviar(true);
    try {
      const resposta = await submeterLead(construirPayloadDaLead(form, redes.length > 1 ? rede : undefined));
      setCriada(resposta);
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
          <CardTitle>{criada.repetida ? "Esta lead já tinha sido submetida" : "Lead submetida"}</CardTitle>
          <CardDescription>
            {criada.repetida
              ? "Submeteu os mesmos dados há instantes — não criámos uma segunda."
              : "A nossa equipa vai analisar e entrar em contacto. Pode acompanhar o caso no painel."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button asChild><Link to={caminhoDoCaso(criada.id)}>Ver o caso e enviar documentos</Link></Button>
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

          {redes.length > 1 && (
            <Campo id="lead-rede" rotulo="Rede *" erro={erros.rede}>
              <select
                id="lead-rede" value={rede} onChange={(e) => setRede(e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">Escolha…</option>
                {redes.map((r) => <option key={r.network_id} value={r.network_id}>{r.company_name || r.network_id}</option>)}
              </select>
            </Campo>
          )}

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
          <Button type="submit" disabled={aEnviar}>{aEnviar ? "A submeter…" : "Submeter lead"}</Button>
        </form>
      </CardContent>
    </Card>
  );
}
