"""
====================================================================
SERVIÇO DE GERAÇÃO DE MINUTAS/TEMPLATES
====================================================================
Gera documentos preenchidos automaticamente com dados do processo.
Suporta:
- CPCV (Contrato Promessa Compra e Venda)
- Email de Apelação de Avaliação
- Outros templates configuráveis

O utilizador faz download e copia para o corpo do email no webmail.
====================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from database import db

logger = logging.getLogger(__name__)


# ====================================================================
# URLS DOS WEBMAILS
# ====================================================================
WEBMAIL_URLS = {
    "precision": "http://webmail.precisioncredito.pt/",
    "power": "https://webmail2.hcpro.pt/Mondo/lang/sys/login.aspx"
}


# ====================================================================
# TEMPLATES DE MINUTAS
# ====================================================================

def generate_cpcv_template(process: Dict[str, Any]) -> str:
    """
    Gera o texto do CPCV (Contrato Promessa Compra e Venda) preenchido.
    
    Args:
        process: Dados do processo
        
    Returns:
        Texto formatado do CPCV
    """
    # Dados do cliente
    client_name = process.get("client_name", "[NOME DO CLIENTE]")
    second_client = process.get("second_client_name") or process.get("titular2_data", {}).get("nome", "")
    
    personal_data = process.get("personal_data", {})
    nif = personal_data.get("nif", "[NIF]")
    cc = personal_data.get("cc", "[Nº CC]")
    morada = personal_data.get("morada", "[MORADA]")
    
    # Dados do imóvel
    property_data = process.get("property_data", {})
    property_address = property_data.get("morada", "[MORADA DO IMÓVEL]")
    property_freguesia = property_data.get("freguesia", "[FREGUESIA]")
    property_concelho = property_data.get("concelho", "[CONCELHO]")
    property_matriz = property_data.get("artigo_matricial", "[ARTIGO MATRICIAL]")
    property_fracao = property_data.get("fracao", "")
    
    # Dados financeiros
    financial_data = process.get("financial_data", {})
    valor_compra = financial_data.get("valor_pretendido") or property_data.get("valor_imovel", 0)
    valor_formatado = f"{valor_compra:,.2f}".replace(",", " ").replace(".", ",") if valor_compra else "[VALOR]"
    
    # Sinal
    sinal = financial_data.get("sinal", 0)
    sinal_formatado = f"{sinal:,.2f}".replace(",", " ").replace(".", ",") if sinal else "[SINAL]"
    
    # Data
    data_atual = datetime.now().strftime("%d de %B de %Y")
    
    # Vendedor (se disponível)
    vendedor = property_data.get("proprietario_nome", "[NOME DO VENDEDOR]")
    vendedor_nif = property_data.get("proprietario_nif", "[NIF DO VENDEDOR]")
    
    # Segundo comprador
    segundo_comprador_texto = ""
    if second_client:
        titular2 = process.get("titular2_data", {})
        segundo_comprador_texto = f"""
e

{second_client}, contribuinte fiscal nº {titular2.get('nif', '[NIF]')}, portador do Cartão de Cidadão nº {titular2.get('cc', '[CC]')}, residente em {titular2.get('morada', '[MORADA]')},
"""

    template = f"""
CONTRATO PROMESSA DE COMPRA E VENDA

Entre:

PRIMEIRO OUTORGANTE (PROMITENTE VENDEDOR):
{vendedor}, contribuinte fiscal nº {vendedor_nif},
doravante designado por "Promitente Vendedor"

e

SEGUNDO OUTORGANTE (PROMITENTE COMPRADOR):
{client_name}, contribuinte fiscal nº {nif}, portador do Cartão de Cidadão nº {cc}, residente em {morada},
{segundo_comprador_texto}
doravante designado(s) por "Promitente(s) Comprador(es)"

É celebrado o presente Contrato Promessa de Compra e Venda, que se rege pelas seguintes cláusulas:

CLÁUSULA PRIMEIRA
(Objeto)

O Promitente Vendedor é dono e legítimo possuidor do seguinte imóvel:
- Fração autónoma designada pela letra "{property_fracao}", correspondente ao {property_fracao} andar, do prédio urbano sito em {property_address}, freguesia de {property_freguesia}, concelho de {property_concelho}, inscrito na matriz predial urbana sob o artigo {property_matriz}.

CLÁUSULA SEGUNDA
(Preço)

O preço da compra e venda é de €{valor_formatado} (euros), a ser pago da seguinte forma:
a) A título de sinal e princípio de pagamento, a quantia de €{sinal_formatado} (euros), nesta data;
b) O remanescente, no montante de €[REMANESCENTE] (euros), será pago na data da celebração da escritura pública de compra e venda.

CLÁUSULA TERCEIRA
(Prazo)

A escritura pública de compra e venda será celebrada no prazo máximo de [PRAZO] dias a contar da presente data, em Cartório Notarial a designar pelo Promitente Comprador, ficando este obrigado a comunicar ao Promitente Vendedor a data, hora e local da escritura com a antecedência mínima de 10 (dez) dias úteis.

CLÁUSULA QUARTA
(Sinal)

O sinal ora entregue ficará sujeito ao regime legal previsto no artigo 442º do Código Civil.

CLÁUSULA QUINTA
(Encargos)

O Promitente Vendedor declara que o imóvel se encontra livre de quaisquer ónus ou encargos, designadamente hipotecas, penhoras ou quaisquer outras limitações ao direito de propriedade, obrigando-se a mantê-lo nessa situação até à data da escritura.

CLÁUSULA SEXTA
(Documentação)

O Promitente Vendedor obriga-se a entregar ao Promitente Comprador, no prazo de [PRAZO DOCS] dias, toda a documentação necessária à celebração da escritura pública.

CLÁUSULA SÉTIMA
(Posse)

A posse do imóvel será entregue ao Promitente Comprador na data da celebração da escritura pública de compra e venda.

CLÁUSULA OITAVA
(Despesas)

As despesas com a celebração da escritura pública, incluindo os respetivos impostos, serão suportadas pelo Promitente Comprador.

CLÁUSULA NONA
(Foro)

Para resolução de quaisquer litígios emergentes do presente contrato, as partes elegem o foro da comarca de {property_concelho}, com expressa renúncia a qualquer outro.

Feito em duplicado, ficando cada uma das partes com um exemplar.

{property_concelho}, {data_atual}

O Promitente Vendedor:
_______________________________
{vendedor}

O(s) Promitente(s) Comprador(es):
_______________________________
{client_name}
{"_______________________________" if second_client else ""}
{second_client if second_client else ""}
"""
    
    return template.strip()


def generate_valuation_appeal_template(process: Dict[str, Any]) -> str:
    """
    Gera o texto de email para apelação/contestação de avaliação bancária.
    "Botão de Pânico" - usado quando avaliação < valor de compra.
    
    Args:
        process: Dados do processo
        
    Returns:
        Texto formatado do email de apelação
    """
    client_name = process.get("client_name", "[NOME DO CLIENTE]")
    
    # Dados do imóvel
    property_data = process.get("property_data", {})
    property_address = property_data.get("morada", "[MORADA DO IMÓVEL]")
    property_concelho = property_data.get("concelho", "[CONCELHO]")
    
    # Dados de crédito e avaliação
    credit_data = process.get("credit_data", {})
    valuation_value = credit_data.get("valuation_value", 0)
    valuation_bank = credit_data.get("valuation_bank", "[BANCO]")
    valuation_date = credit_data.get("valuation_date", "[DATA]")
    
    # Valor de compra
    financial_data = process.get("financial_data", {})
    purchase_value = financial_data.get("valor_pretendido") or property_data.get("valor_imovel", 0)
    
    # Calcular diferença
    difference = purchase_value - valuation_value if purchase_value and valuation_value else 0
    percentage = (difference / purchase_value * 100) if purchase_value else 0
    
    # Formatação
    valuation_fmt = f"{valuation_value:,.2f}".replace(",", " ").replace(".", ",") if valuation_value else "[VALOR AVALIAÇÃO]"
    purchase_fmt = f"{purchase_value:,.2f}".replace(",", " ").replace(".", ",") if purchase_value else "[VALOR COMPRA]"
    difference_fmt = f"{difference:,.2f}".replace(",", " ").replace(".", ",") if difference else "[DIFERENÇA]"
    
    template = f"""
Assunto: Pedido de Reavaliação - Processo de Crédito Habitação - {client_name}

Exmos. Senhores,

Venho por este meio solicitar a reavaliação do imóvel referente ao processo de crédito habitação do(a) cliente {client_name}.

DADOS DO IMÓVEL:
- Localização: {property_address}, {property_concelho}
- Valor de Aquisição Acordado: €{purchase_fmt}

AVALIAÇÃO ATUAL:
- Banco Avaliador: {valuation_bank}
- Data da Avaliação: {valuation_date}
- Valor Atribuído: €{valuation_fmt}

FUNDAMENTAÇÃO DO PEDIDO:

A avaliação realizada apresenta uma diferença de €{difference_fmt} ({percentage:.1f}%) face ao valor de aquisição acordado entre as partes, o que consideramos não refletir adequadamente o valor de mercado do imóvel pelos seguintes motivos:

1. COMPARÁVEIS DE MERCADO:
   [Incluir 2-3 imóveis semelhantes vendidos recentemente na zona com valores superiores]
   - Imóvel 1: [Descrição e valor]
   - Imóvel 2: [Descrição e valor]
   - Imóvel 3: [Descrição e valor]

2. CARACTERÍSTICAS DIFERENCIADORAS:
   [Listar características que valorizam o imóvel]
   - [Característica 1]
   - [Característica 2]
   - [Característica 3]

3. MELHORAMENTOS RECENTES:
   [Se aplicável, listar obras/renovações realizadas]
   - [Melhoramento 1]
   - [Melhoramento 2]

4. LOCALIZAÇÃO PRIVILEGIADA:
   [Destacar vantagens da localização]
   - Proximidade a [transportes/escolas/serviços]
   - [Outras vantagens]

Solicitamos, assim, que seja efetuada nova avaliação ao imóvel, preferencialmente por outro perito, tendo em consideração os elementos acima indicados.

Encontramo-nos disponíveis para fornecer documentação adicional que suporte este pedido, nomeadamente:
- Fotografias atualizadas do imóvel
- Documentação de obras/melhoramentos
- Estudos de mercado da zona

Agradecemos a vossa melhor atenção para este assunto e aguardamos resposta com a maior brevidade possível.

Com os melhores cumprimentos,

[ASSINATURA]
[EMPRESA]
[CONTACTOS]

---
Processo interno: {process.get('id', '[ID]')}
Cliente: {client_name}
"""
    
    return template.strip()


def generate_document_request_template(process: Dict[str, Any], missing_docs: list) -> str:
    """
    Gera email para solicitar documentos em falta ao cliente.
    
    Args:
        process: Dados do processo
        missing_docs: Lista de documentos em falta
        
    Returns:
        Texto formatado do email
    """
    client_name = process.get("client_name", "[NOME DO CLIENTE]")
    
    docs_list = "\n".join([f"   • {doc}" for doc in missing_docs]) if missing_docs else "   • [DOCUMENTOS]"
    
    template = f"""
Assunto: Documentação Necessária - Processo de Crédito Habitação

Caro(a) {client_name},

Esperamos que esteja bem.

No seguimento do seu processo de crédito habitação, vimos por este meio solicitar o envio da seguinte documentação, necessária para dar continuidade à análise:

DOCUMENTOS EM FALTA:
{docs_list}

Pedimos que envie os documentos em formato digital (PDF ou imagem) para este email, ou que os carregue diretamente na plataforma através do link do seu processo.

Caso tenha alguma dúvida sobre os documentos solicitados, não hesite em contactar-nos.

Agradecemos a sua colaboração e rapidez no envio, de forma a agilizar o processo.

Com os melhores cumprimentos,

[ASSINATURA]
[EMPRESA]
[CONTACTOS]
"""
    
    return template.strip()


def generate_deed_reminder_template(process: Dict[str, Any]) -> str:
    """
    Gera email de lembrete para escritura.
    
    Args:
        process: Dados do processo
        
    Returns:
        Texto formatado do email
    """
    client_name = process.get("client_name", "[NOME DO CLIENTE]")
    
    property_data = process.get("property_data", {})
    property_address = property_data.get("morada", "[MORADA DO IMÓVEL]")
    
    credit_data = process.get("credit_data", {})
    bank_name = credit_data.get("bank_name", "[BANCO]")
    
    # Data da escritura (se disponível)
    deed_date = process.get("deed_date", "[DATA A DEFINIR]")
    deed_location = process.get("deed_location", "[LOCAL A DEFINIR]")
    
    template = f"""
Assunto: Lembrete - Escritura de Compra e Venda

Caro(a) {client_name},

Esperamos que esteja bem.

Vimos por este meio relembrar que a escritura de compra e venda do imóvel sito em:
{property_address}

está agendada para:
- Data: {deed_date}
- Local: {deed_location}

DOCUMENTOS A LEVAR:
   • Cartão de Cidadão (original)
   • Comprovativo de IBAN
   • Comprovativo de morada atualizado
   • [Outros documentos específicos]

INFORMAÇÃO IMPORTANTE:
   • O financiamento será disponibilizado pelo {bank_name}
   • Deverá comparecer 15 minutos antes da hora marcada
   • Em caso de impossibilidade, contacte-nos com a maior antecedência possível

Caso tenha alguma dúvida, não hesite em contactar-nos.

Com os melhores cumprimentos,

[ASSINATURA]
[EMPRESA]
[CONTACTOS]
"""
    
    return template.strip()


async def get_template_for_process(
    process_id: str,
    template_type: str,
    extra_data: dict = None,
    validate_fields: bool = True
) -> Dict[str, Any]:
    """
    Obtém um template preenchido para um processo.
    
    Args:
        process_id: ID do processo
        template_type: Tipo de template (cpcv, valuation_appeal, document_request, deed_reminder)
        extra_data: Dados adicionais (ex: lista de documentos em falta)
        validate_fields: Se deve validar campos obrigatórios (default: True)
        
    Returns:
        Dict com o template e metadata
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        return {"error": "Processo não encontrado", "template": None}
    
    # Validar campos obrigatórios antes de gerar
    if validate_fields:
        validation = validate_template_requirements(process, template_type)
        if not validation["is_valid"]:
            return {
                "error": "Dados insuficientes para gerar a minuta",
                "validation_error": True,
                "missing_fields": validation["missing_fields"],
                "missing_fields_message": validation["message"],
                "template": None
            }
    
    templates = {
        "cpcv": generate_cpcv_template,
        "valuation_appeal": generate_valuation_appeal_template,
        "deed_reminder": generate_deed_reminder_template,
        "contrato_mediacao": generate_contrato_mediacao_template,
        "ficha_visita": generate_ficha_visita_template,
    }
    
    if template_type == "document_request":
        missing_docs = extra_data.get("missing_docs", []) if extra_data else []
        template_text = generate_document_request_template(process, missing_docs)
    elif template_type in templates:
        template_text = templates[template_type](process)
    else:
        return {"error": f"Tipo de template desconhecido: {template_type}", "template": None}
    
    return {
        "template_type": template_type,
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "template": template_text,
        "webmail_urls": WEBMAIL_URLS,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


# ====================================================================
# VALIDAÇÃO DE CAMPOS OBRIGATÓRIOS POR TIPO DE TEMPLATE
# ====================================================================

# Definição de campos obrigatórios por tipo de template
TEMPLATE_REQUIRED_FIELDS = {
    "cpcv": {
        "fields": [
            ("client_name", "Nome do Comprador"),
            ("personal_data.nif", "NIF do Comprador"),
            ("property_data.morada", "Morada do Imóvel"),
            ("property_data.artigo_matricial", "Artigo Matricial do Imóvel"),
        ],
        "recommended": [
            ("personal_data.cc", "Cartão de Cidadão do Comprador"),
            ("personal_data.morada", "Morada do Comprador"),
            ("property_data.proprietario_nome", "Nome do Vendedor"),
            ("property_data.proprietario_nif", "NIF do Vendedor"),
            ("financial_data.valor_pretendido", "Valor de Compra"),
        ]
    },
    "valuation_appeal": {
        "fields": [
            ("client_name", "Nome do Cliente"),
            ("property_data.morada", "Morada do Imóvel"),
        ],
        "recommended": [
            ("credit_data.valuation_value", "Valor da Avaliação"),
            ("credit_data.valuation_bank", "Banco Avaliador"),
            ("financial_data.valor_pretendido", "Valor de Compra"),
        ]
    },
    "deed_reminder": {
        "fields": [
            ("client_name", "Nome do Cliente"),
        ],
        "recommended": [
            ("property_data.morada", "Morada do Imóvel"),
            ("credit_data.bank_name", "Nome do Banco"),
        ]
    },
    "document_request": {
        "fields": [
            ("client_name", "Nome do Cliente"),
        ],
        "recommended": []
    }
}


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """
    Obtém um valor aninhado de um dicionário usando notação de ponto.
    Ex: get_nested_value(data, "personal_data.nif")
    """
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def validate_template_requirements(
    process: Dict[str, Any], 
    template_type: str
) -> Dict[str, Any]:
    """
    Valida se o processo tem todos os campos obrigatórios para gerar um template.
    
    Args:
        process: Dados do processo
        template_type: Tipo de template a gerar
        
    Returns:
        Dict com resultado da validação
    """
    config = TEMPLATE_REQUIRED_FIELDS.get(template_type, {"fields": [], "recommended": []})
    
    missing_required = []
    missing_recommended = []
    
    # Verificar campos obrigatórios
    for field_path, field_name in config["fields"]:
        value = get_nested_value(process, field_path)
        if not value or (isinstance(value, str) and not value.strip()):
            missing_required.append(field_name)
    
    # Verificar campos recomendados
    for field_path, field_name in config["recommended"]:
        value = get_nested_value(process, field_path)
        if not value or (isinstance(value, str) and not value.strip()):
            missing_recommended.append(field_name)
    
    is_valid = len(missing_required) == 0
    
    # Construir mensagem
    messages = []
    if missing_required:
        messages.append(f"Campos obrigatórios em falta: {', '.join(missing_required)}")
    if missing_recommended:
        messages.append(f"Campos recomendados em falta: {', '.join(missing_recommended)}")
    
    return {
        "is_valid": is_valid,
        "missing_fields": missing_required,
        "missing_recommended": missing_recommended,
        "message": " | ".join(messages) if messages else "Todos os campos preenchidos"
    }


# ====================================================================
# NOVOS TEMPLATES: CONTRATO MEDIAÇÃO E FICHA VISITA
# ====================================================================

def generate_contrato_mediacao_template(process: Dict[str, Any]) -> str:
    """
    Gera o texto do Contrato de Mediação Imobiliária.
    """
    client_name = process.get("client_name", "[NOME DO CLIENTE]")
    personal_data = process.get("personal_data", {})
    
    nif = personal_data.get("nif", "[NIF]")
    morada = personal_data.get("morada", "[MORADA]")
    telefone = personal_data.get("telefone", "[TELEFONE]")
    email = personal_data.get("email", "")
    
    property_data = process.get("property_data", {}) or process.get("real_estate_data", {})
    property_address = property_data.get("morada") or property_data.get("address", "[MORADA DO IMÓVEL]")
    property_typology = property_data.get("tipologia") or property_data.get("typology", "[TIPOLOGIA]")
    
    financial_data = process.get("financial_data", {})
    property_price = financial_data.get("valor_pretendido") or property_data.get("price", "")
    
    data_atual = datetime.now().strftime("%d de %B de %Y")
    
    template = f"""
CONTRATO DE MEDIAÇÃO IMOBILIÁRIA

Celebrado em {data_atual}

Entre:

PRIMEIRA OUTORGANTE (MEDIADORA):
Power Real Estate & Precision Crédito, Unipessoal Lda.
Sociedade de Mediação Imobiliária
Licença AMI n.º [A PREENCHER]
NIPC: [A PREENCHER]
Sede: [MORADA DA SEDE]

e

SEGUNDO OUTORGANTE (CLIENTE):
{client_name}
NIF: {nif}
Morada: {morada}
Telefone: {telefone}
{f'Email: {email}' if email else ''}

É celebrado o presente Contrato de Mediação Imobiliária, ao abrigo da Lei n.º 15/2013, de 8 de Fevereiro.

PRIMEIRA (Objeto)
O presente contrato tem por objeto a prestação de serviços de mediação imobiliária relativamente ao seguinte imóvel:
Morada: {property_address}
Tipologia: {property_typology}
{f'Preço Pretendido: {property_price}€' if property_price else ''}

SEGUNDA (Tipo de Negócio)
A mediação destina-se a:
[ ] Compra do imóvel
[ ] Venda do imóvel
[ ] Arrendamento

TERCEIRA (Regime)
Este contrato é celebrado em regime de:
[ ] Exclusividade
[ ] Não Exclusividade

QUARTA (Prazo)
O presente contrato tem a duração de [6] meses, renovando-se automaticamente por iguais períodos, salvo denúncia por qualquer das partes com antecedência mínima de 15 dias.

QUINTA (Remuneração)
Pela prestação dos serviços de mediação, a Mediadora terá direito a uma comissão de [___]% sobre o preço de venda/arrendamento, acrescida de IVA à taxa legal em vigor.
A comissão é devida aquando da celebração do contrato que vise o negócio objeto da mediação.

SEXTA (Obrigações da Mediadora)
A Mediadora obriga-se a:
a) Diligenciar no sentido de conseguir interessado para o negócio;
b) Dar publicidade ao imóvel através dos meios adequados;
c) Acompanhar o processo até à celebração do negócio;
d) Prestar toda a informação e esclarecimentos solicitados.

SÉTIMA (Obrigações do Cliente)
O Cliente obriga-se a:
a) Fornecer à Mediadora toda a documentação necessária;
b) Comunicar à Mediadora todos os factos relevantes;
c) Pagar a remuneração acordada.

Feito em duplicado, ficando um exemplar para cada parte.

Local: ___________________ Data: {data_atual}

Pela Mediadora: ___________________________

O Cliente: ___________________________

---
Documento gerado automaticamente pelo sistema PowerCell CRM
Processo: {process.get('id', '[ID]')}
"""
    return template.strip()


def generate_ficha_visita_template(process: Dict[str, Any]) -> str:
    """
    Gera o texto da Ficha de Visita ao Imóvel.
    """
    client_name = process.get("client_name", "[NOME DO CLIENTE]")
    personal_data = process.get("personal_data", {})
    
    telefone = personal_data.get("telefone", "[TELEFONE]")
    email = personal_data.get("email", "")
    
    property_data = process.get("property_data", {}) or process.get("real_estate_data", {})
    property_address = property_data.get("morada") or property_data.get("address", "[MORADA DO IMÓVEL]")
    owner_name = property_data.get("proprietario_nome") or property_data.get("owner_name", "")
    
    financial_data = process.get("financial_data", {})
    property_price = financial_data.get("valor_pretendido") or property_data.get("price", "")
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    hora_atual = datetime.now().strftime("%H:%M")
    
    template = f"""
FICHA DE VISITA AO IMÓVEL

═══════════════════════════════════════════════════════════════════
Data: {data_atual}                              Hora: {hora_atual}
═══════════════════════════════════════════════════════════════════

DADOS DO CLIENTE VISITANTE
───────────────────────────────────────────────────────────────────
Nome: {client_name}
Telefone: {telefone}
{f'Email: {email}' if email else ''}


DADOS DO IMÓVEL VISITADO
───────────────────────────────────────────────────────────────────
Morada: {property_address}
{f'Proprietário: {owner_name}' if owner_name else ''}
{f'Preço: {property_price}€' if property_price else ''}


OBSERVAÇÕES DA VISITA
───────────────────────────────────────────────────────────────────

Estado geral do imóvel:
[ ] Excelente    [ ] Bom    [ ] Razoável    [ ] Necessita obras

Exposição solar:
[ ] Norte    [ ] Sul    [ ] Este    [ ] Oeste    [ ] Nascente/Poente

Ruído ambiente:
[ ] Muito silencioso    [ ] Silencioso    [ ] Normal    [ ] Ruidoso

Pontos positivos observados:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

Pontos a melhorar:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________


FEEDBACK DO CLIENTE
───────────────────────────────────────────────────────────────────

Comentários/Observações do cliente:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

Nível de interesse:
[ ] Muito interessado - Pretende avançar com proposta
[ ] Interessado - Quer pensar / Ver mais imóveis
[ ] Pouco interessado - Não corresponde ao pretendido
[ ] Sem interesse - Descartado

Proposta/Próximos passos:
_________________________________________________________________
_________________________________________________________________


ASSINATURAS
───────────────────────────────────────────────────────────────────

Cliente: _________________________________ Data: ___/___/______

Consultor: _______________________________ Data: ___/___/______

═══════════════════════════════════════════════════════════════════
Documento gerado pelo sistema PowerCell CRM
Processo: {process.get('id', '[ID]')} | Ref: #{process.get('process_number', '')}
═══════════════════════════════════════════════════════════════════
"""
    return template.strip()


# Adicionar novos templates às configurações
TEMPLATE_REQUIRED_FIELDS["contrato_mediacao"] = {
    "fields": [
        ("client_name", "Nome do Cliente"),
        ("personal_data.nif", "NIF do Cliente"),
        ("personal_data.morada", "Morada do Cliente"),
    ],
    "recommended": [
        ("personal_data.telefone", "Telefone do Cliente"),
        ("property_data.morada", "Morada do Imóvel"),
    ]
}

TEMPLATE_REQUIRED_FIELDS["ficha_visita"] = {
    "fields": [
        ("client_name", "Nome do Cliente"),
        ("personal_data.telefone", "Telefone do Cliente"),
    ],
    "recommended": [
        ("property_data.morada", "Morada do Imóvel"),
    ]
}


# Lista de todos os templates disponíveis
AVAILABLE_TEMPLATES = [
    {
        "type": "cpcv",
        "name": "CPCV - Contrato Promessa Compra e Venda",
        "description": "Documento de promessa de compra e venda de imóvel"
    },
    {
        "type": "contrato_mediacao",
        "name": "Contrato de Mediação Imobiliária",
        "description": "Contrato entre a mediadora e o cliente"
    },
    {
        "type": "ficha_visita",
        "name": "Ficha de Visita ao Imóvel",
        "description": "Registo de visita ao imóvel"
    },
    {
        "type": "valuation_appeal",
        "name": "Apelação de Avaliação",
        "description": "Email para contestar avaliação bancária"
    },
    {
        "type": "document_request",
        "name": "Pedido de Documentos",
        "description": "Email para solicitar documentos ao cliente"
    },
    {
        "type": "deed_reminder",
        "name": "Lembrete de Escritura",
        "description": "Email de lembrete para escritura"
    }
]


def get_available_templates_list():
    """Retorna lista de templates disponíveis."""
    return AVAILABLE_TEMPLATES
