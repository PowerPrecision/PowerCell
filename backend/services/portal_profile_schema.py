"""
====================================================================
Perfil do Portal derivado do formulário interno (Lote 3, ponto 7)
====================================================================
Uma única fonte de verdade: o `form_config` que o admin configura.

PORQUÊ
------
O formulário interno é configurável — o admin liga campos, define
obrigatoriedade, acrescenta campos personalizados. O do Portal era uma
lista escrita à mão no `ClientPortal.jsx`, com um allowlist igualmente
escrito à mão no `portal_profile.py`. As duas listas divergiram: faltavam
campos (`codigo_postal`, `niss`), não havia sinalização de obrigatórios, e
o allowlist descartava em SILÊNCIO tudo o que não conhecia — o cliente
preenchia, gravava, lia "Perfil atualizado com sucesso!" e o valor não
existia.

Derivando as duas coisas do mesmo sítio, não podem voltar a divergir: o
que o Portal mostra é exactamente o que o backend aceita gravar, e há um
teste a afirmá-lo.

REGRA DE NEGÓCIO
----------------
O NIF **nunca** é editável pelo cliente. É o campo que o identifica
fiscalmente e é usado em comparações e deduplicação; deixá-lo editável no
Portal é uma decisão de risco, não de interface. Fora do esquema EDITÁVEL e
fora da escrita; desde Out 2026 aparece no ecrã como campo SÓ DE LEITURA e
MASCARADO (últimos 3 dígitos) — o cliente vê que o dado existe, a equipa é
que o altera.

ÂMBITO (Out 2026): «O Meu Perfil» espelha TODO o formulário de registo —
titular (passo 1), segundo titular (2), imóvel pretendido (3) e situação
financeira (4–5) —, não só o passo 1. Cada entrada leva `section` (o cartão onde
se desenha) e `read_only` (visível mas não gravável: identidade e listas de
bancos, que não têm editor no Portal). O consentimento (passo 6) é um acto legal
e fica fora.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Passo do formulário que corresponde ao perfil do titular.
PORTAL_PROFILE_STEP = 1

#: Passo do formulário → cartão do perfil em que se desenha. O passo 6
#: (consentimentos) NÃO está aqui de propósito: é um acto legal assinado no registo.
SECCAO_POR_PASSO = {
    1: "titular",
    2: "segundo_titular",
    3: "imovel",
    4: "financeiro",
    5: "financeiro",
}

#: Ordem e título dos cartões.
SECCOES_DO_PERFIL = (
    ("titular", "Dados Pessoais"),
    ("segundo_titular", "Segundo Titular"),
    ("imovel", "Imóvel Pretendido"),
    ("financeiro", "Situação Financeira"),
)

#: Grupos da ficha do cliente que NÃO são `contacto`/`dados_pessoais`. O nome do
#: grupo no pedido é o do formulário; onde vive no cliente vê-se em
#: `portal_profile_sections.CAMPO_DO_CLIENTE`.
GRUPOS_DAS_SECCOES = frozenset({"titular2_data", "real_estate_data", "financial_data"})

# Campos que o cliente NUNCA pode editar pelo Portal, mesmo que o admin os
# ligue no formulário interno. Não é uma preferência de UI: são dados de
# identidade e de deduplicação que só a equipa altera.
PORTAL_LOCKED_FIELDS = frozenset(
    {
        "nif",          # identifica fiscalmente — regra de negócio confirmada
        "name",         # o nome da ficha é gerido pela equipa
        "nome",
        "nome_pai",
        "nome_mae",
        "altura",
        "menor_35_anos",   # campo de negócio, não do perfil
        "compra_tipo",
    }
)

#: Campos VISÍVEIS mas nunca gravados pelo Portal. Duas razões, uma só consequência:
#:   · identidade (NIF, nome do 2.º titular) — regra de negócio, só a equipa altera;
#:   · listas de bancos (`bancos_creditos`…) — dados estruturados sem editor no Portal;
#:     deixá-los editáveis como texto livre estragava o formato que o CRM lê.
PORTAL_READ_ONLY_FIELDS = frozenset(
    {
        "nif",
        "titular2_nif",
        "titular2_name",
        "bancos_creditos",
        "tem_creditos_activos",
        "bancos_simulacoes",
    }
)

#: Nomes na ficha do 2.º titular que o cliente não pode alterar (rede de segurança
#: do allowlist, independente de `PORTAL_READ_ONLY_FIELDS`).
TITULAR2_TRANCADOS = frozenset({"name", "nif"})

# Contactos que o Portal já oferecia e que não existem no formulário
# interno. Continuam a funcionar — esta mudança não pode tirar nada ao
# cliente.
PORTAL_EXTRA_CONTACT_FIELDS = frozenset({"email_secundario", "telefone_secundario"})

# `data_path` do formulário → grupo na ficha do cliente.
_GRUPO_POR_DATA_PATH = {
    "root": "contacto",
    "personal_data": "dados_pessoais",
    "titular2_data": "titular2_data",
    "real_estate_data": "real_estate_data",
    "financial_data": "financial_data",
}

#: O formulário prefixa os campos do 2.º titular (`titular2_nif`); na ficha
#: (`titular2_data`) guardam-se sem prefixo (`nif`) — é o que o registo grava.
_PREFIXO_DO_TITULAR2 = "titular2_"

# Campos cujo nome no formulário difere do nome na ficha. Sem isto, o
# Portal gravaria `contacto.phone` (campo novo, invisível ao CRM) em vez
# de `contacto.telefone`.
_RENOMEACOES = {
    "phone": "telefone",
    "telemovel": "telefone",
    # O CRM lê `data_nascimento` primeiro (ver `PersonalInfoTab`); o
    # formulário interno chama-lhe `birth_date`.
    "birth_date": "data_nascimento",
}

# Do passo 1, só estes campos de `data_path: root` são contactos do
# titular. Os restantes campos de raiz (ex.: `name`) não pertencem aqui.
_CONTACTOS_DE_RAIZ = frozenset({"email", "phone", "telemovel"})


def destino_do_campo(campo: dict) -> Optional[tuple]:
    """`(grupo, nome)` onde um campo do formulário é gravado na ficha.

    Args:
        campo: entrada do `form_config` (`field_key` + `data_path`).

    Returns:
        `("contacto" | "dados_pessoais", nome_na_ficha)`, ou ``None``
        quando o campo não pertence ao perfil do cliente (2.º titular,
        imóvel, crédito).
    """
    chave = str(campo.get("field_key") or "").strip()
    if not chave:
        return None

    grupo = _GRUPO_POR_DATA_PATH.get(campo.get("data_path"))
    if not grupo:
        return None

    if grupo == "contacto" and chave not in _CONTACTOS_DE_RAIZ:
        return None

    if grupo == "titular2_data":
        nome = chave[len(_PREFIXO_DO_TITULAR2):] if chave.startswith(_PREFIXO_DO_TITULAR2) else chave
        return grupo, nome

    if grupo in GRUPOS_DAS_SECCOES:
        return grupo, chave

    return grupo, _RENOMEACOES.get(chave, chave)


def build_portal_profile_schema(campos: list[dict]) -> list[dict]:
    """Campos que o Portal deve mostrar, a partir do formulário interno.

    Args:
        campos: `all_fields` do `form_config` (já com os defaults fundidos).

    Returns:
        Lista ordenada de entradas com tudo o que a UI precisa:
        `field_key`, `label`, `field_type`, `is_required`, `options`,
        `hint`, `destino` e `is_primary`.

        `is_primary` marca os campos a mostrar de imediato; os restantes
        vivem atrás da secção expansível (divulgação progressiva). A regra
        é "obrigatório = principal", com uma excepção adiante.
    """
    schema: list[dict] = []

    for campo in campos or []:
        if not campo.get("is_visible"):
            continue
        passo = int(campo.get("step") or 0)
        seccao = SECCAO_POR_PASSO.get(passo)
        if not seccao:
            continue

        chave = str(campo.get("field_key") or "").strip()
        so_de_leitura = chave in PORTAL_READ_ONLY_FIELDS
        # Trancados por regra de negócio e SEM interesse para o cliente (o nome
        # completo já vem à parte; `compra_tipo` e `menor_35_anos` são do negócio):
        # continuam fora do ecrã. O NIF e afins não — esses vêm como só de leitura.
        if passo == PORTAL_PROFILE_STEP and chave in PORTAL_LOCKED_FIELDS and not so_de_leitura:
            continue

        destino = destino_do_campo(campo)
        if not destino:
            continue

        schema.append(
            {
                "field_key": chave,
                "label": campo.get("label") or chave,
                "field_type": campo.get("field_type") or "text",
                "is_required": bool(campo.get("is_required")) and not so_de_leitura,
                "options": campo.get("options") or [],
                "hint": campo.get("hint") or "",
                "order": campo.get("order_index", campo.get("order", 0)),
                "destino": destino,
                "section": seccao,
                "step": passo,
                "read_only": so_de_leitura,
                "is_primary": bool(campo.get("is_required")) or so_de_leitura,
            }
        )

    # Contactos que o Portal já oferecia e que o formulário interno não
    # tem. Entram como secundários — tirá-los seria uma regressão para o
    # cliente, e deixá-los só no allowlist (sem esquema) deixaria a UI sem
    # os desenhar.
    ja_presentes = {c["field_key"] for c in schema}
    for chave, rotulo, tipo in (
        ("email_secundario", "Email Secundário", "email"),
        ("telefone_secundario", "Telefone Secundário", "tel"),
    ):
        if chave in ja_presentes:
            continue
        schema.append(
            {
                "field_key": chave,
                "label": rotulo,
                "field_type": tipo,
                "is_required": False,
                "options": [],
                "hint": "",
                "order": 900,
                "destino": ("contacto", chave),
                "section": "titular",
                "step": PORTAL_PROFILE_STEP,
                "read_only": False,
                "is_primary": False,
            }
        )

    ordem_das_seccoes = {nome: i for i, (nome, _) in enumerate(SECCOES_DO_PERFIL)}
    schema.sort(
        key=lambda c: (ordem_das_seccoes.get(c["section"], 99), c["step"], c["order"], c["field_key"])
    )

    # Um formulário inteiro escondido atrás de um acordeão seria pior do
    # que não ter divulgação progressiva nenhuma. Se o admin não marcou
    # nada como obrigatório numa SECÇÃO, os primeiros campos dela ficam à vista.
    for nome, _titulo in SECCOES_DO_PERFIL:
        da_seccao = [c for c in schema if c["section"] == nome]
        if da_seccao and not any(c["is_primary"] and not c["read_only"] for c in da_seccao):
            for entrada in da_seccao[:4]:
                entrada["is_primary"] = True

    return schema


def portal_updatable_fields(schema: list[dict]) -> dict:
    """Campos que o Portal pode GRAVAR, derivados do mesmo esquema.

    É o ponto central desta mudança: o allowlist deixa de ser uma lista
    paralela escrita à mão e passa a sair do que o Portal mostra. O que se
    vê é o que se grava.

    Returns:
        `{"contacto": set, "dados_pessoais": set}`.
    """
    campos: dict[str, set] = {
        "contacto": set(PORTAL_EXTRA_CONTACT_FIELDS),
        "dados_pessoais": set(),
        "titular2_data": set(),
        "real_estate_data": set(),
        "financial_data": set(),
    }

    for entrada in schema or []:
        if entrada.get("read_only"):
            # Visível, nunca gravável.
            continue
        grupo, nome = entrada["destino"]
        trancado = nome in PORTAL_LOCKED_FIELDS if grupo in ("contacto", "dados_pessoais") else (
            grupo == "titular2_data" and nome in TITULAR2_TRANCADOS
        )
        if trancado:
            # Rede de segurança: um mapeamento novo nunca pode destrancar
            # um campo trancado por regra de negócio.
            logger.warning(
                "[PORTAL-SCHEMA] Campo trancado '%s' ignorado no allowlist", nome
            )
            continue
        campos[grupo].add(nome)

    return campos
