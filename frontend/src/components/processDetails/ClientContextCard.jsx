/**
 * ClientContextCard — Card de contexto fixo (coluna direita) com os dados
 * essenciais do titular do processo: nome, NIF e contactos rápidos.
 *
 * PORQUÊ: Parte do redesign "Progressive Disclosure" da página de detalhes
 * do processo — o consultor precisa de ligar/escrever ao cliente ou
 * confirmar o NIF em qualquer separador (Resumo/Documentos/Histórico) sem
 * ter de navegar até ao formulário de dados pessoais.
 *
 * PACOTE 11 (Eixo 3): quando `clientId` é passado, o nome do titular é um
 * Link para a ficha do cliente (/cliente/:id) — antes era texto morto.
 */
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { User, Hash, Mail, Phone, MapPin } from "lucide-react";
import { safeString } from "../../utils/safeString";

function ContactLine({ icon: Icon, label, value, href, internalLink = false, title }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <Icon className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-muted-foreground leading-none mb-0.5">{label}</p>
        {href ? (
          internalLink ? (
            <Link
              to={href}
              title={title}
              className="text-sm font-medium text-primary hover:underline underline-offset-2 break-all"
            >
              {value}
            </Link>
          ) : (
            <a href={href} title={title} className="text-sm font-medium text-primary hover:underline break-all">
              {value}
            </a>
          )
        ) : (
          <p className="text-sm font-medium break-words">{value}</p>
        )}
      </div>
    </div>
  );
}

export default function ClientContextCard({ process, personalData, clientData, clientId = null }) {
  const nome =
    safeString(process?.client_name) ||
    safeString(personalData?.nome_completo) ||
    safeString(clientData?.nome) ||
    "Cliente";
  const nif = safeString(personalData?.nif) || safeString(clientData?.dados_pessoais?.nif);
  const email = safeString(process?.client_email) || safeString(clientData?.contacto?.email);
  const telefone =
    safeString(process?.client_phone) ||
    safeString(personalData?.telefone) ||
    safeString(clientData?.contacto?.telefone);
  const morada = safeString(personalData?.morada_fiscal);
  const fichaClienteHref = clientId ? `/cliente/${clientId}` : null;

  return (
    <Card className="border-border" data-testid="client-context-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <User className="h-4 w-4 text-primary" />
          Cliente
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 divide-y divide-border">
        <ContactLine
          icon={User}
          label="Titular"
          value={nome}
          href={fichaClienteHref}
          internalLink
          title={fichaClienteHref ? "Abrir ficha do cliente" : undefined}
        />
        <ContactLine icon={Hash} label="NIF" value={nif} />
        <ContactLine icon={Mail} label="Email" value={email} href={email ? `mailto:${email}` : undefined} />
        <ContactLine icon={Phone} label="Telefone" value={telefone} href={telefone ? `tel:${telefone}` : undefined} />
        <ContactLine icon={MapPin} label="Morada Fiscal" value={morada} />
      </CardContent>
    </Card>
  );
}
