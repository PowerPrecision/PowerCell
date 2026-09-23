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
Portal é uma decisão de risco, não de interface. Continua oculto na
leitura (`PROFILE_HIDDEN_FIELDS`) e fora do esquema na escrita.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Passo do formulário que corresponde ao perfil do titular. Os passos 2
# (2.º titular) e 3+ (imóvel, crédito) não pertencem a "O Meu Perfil".
PORTAL_PROFILE_STEP = 1

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

# Contactos que o Portal já oferecia e que não existem no formulário
# interno. Continuam a funcionar — esta mudança não pode tirar nada ao
# cliente.
PORTAL_EXTRA_CONTACT_FIELDS = frozenset({"email_secundario", "telefone_secundario"})

# `data_path` do formulário → grupo na ficha do cliente.
_GRUPO_POR_DATA_PATH = {
    "root": "contacto",
    "personal_data": "dados_pessoais",
}

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
        if int(campo.get("step") or 0) != PORTAL_PROFILE_STEP:
            continue

        chave = str(campo.get("field_key") or "").strip()
        if chave in PORTAL_LOCKED_FIELDS:
            continue

        destino = destino_do_campo(campo)
        if not destino:
            continue

        schema.append(
            {
                "field_key": chave,
                "label": campo.get("label") or chave,
                "field_type": campo.get("field_type") or "text",
                "is_required": bool(campo.get("is_required")),
                "options": campo.get("options") or [],
                "hint": campo.get("hint") or "",
                "order": campo.get("order_index", campo.get("order", 0)),
                "destino": destino,
                "is_primary": bool(campo.get("is_required")),
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
                "is_primary": False,
            }
        )

    schema.sort(key=lambda c: (c["order"], c["field_key"]))

    # Um formulário inteiro escondido atrás de um acordeão seria pior do
    # que não ter divulgação progressiva nenhuma. Se o admin não marcou
    # nada como obrigatório, os primeiros campos ficam à vista.
    if schema and not any(c["is_primary"] for c in schema):
        for entrada in schema[:4]:
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
    }

    for entrada in schema or []:
        grupo, nome = entrada["destino"]
        if nome in PORTAL_LOCKED_FIELDS:
            # Rede de segurança: um mapeamento novo nunca pode destrancar
            # um campo trancado por regra de negócio.
            logger.warning(
                "[PORTAL-SCHEMA] Campo trancado '%s' ignorado no allowlist", nome
            )
            continue
        campos[grupo].add(nome)

    return campos
