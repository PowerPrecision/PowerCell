"""
====================================================================
PORTAL DO PARCEIRO — EDITAR OS DADOS DO CLIENTE (Out 2026)
====================================================================
O PEDIDO
  O separador de dados do cliente no Portal do Parceiro usa **a mesma
  estrutura do registo público** e suporta a adição de **Segundos
  Titulares**.

POR ISSO O ESQUEMA NÃO É NOSSO — É O DO FORMULÁRIO PÚBLICO
  Os campos, as etiquetas, as opções e a obrigatoriedade saem do
  `form_config` que o administrador configura (`load_merged_form_fields`),
  tal como o Portal do Cliente e o próprio registo público. Uma lista
  paralela escrita aqui divergiria no dia em que o administrador ligasse um
  campo (foi o que aconteceu ao perfil do Portal do Cliente).

  Só entram os passos que uma LEAD guarda: o **titular** (passo 1) e o
  **2.º titular** (passo 2). Imóvel e financiamento pertencem ao processo
  (o registo público também os não guarda na ficha do cliente), e o
  consentimento é do parceiro, já dado ao submeter.

O QUE O SERVIDOR GARANTE (o corpo é de um agente externo)
  * **lista positiva**: um campo que não está no esquema é 400 (nunca é
    ignorado em silêncio — o parceiro leria «guardado» sobre um valor que
    não existe);
  * cada valor é validado pelo TIPO do campo (NIF, email, telefone, data,
    opção de uma lista, número);
  * só se edita o que ainda é do parceiro: rascunho, devolvida, ou lead
    ainda sem processo. Um **processo** é da equipa; uma lead **expirada**
    não se trabalha;
  * a PII é cifrada e os blind indexes recalculados (`encrypt_client_data`);
  * **2.º titular**: ligado por `compra_tipo = outra_pessoa`. Desligar
    apaga os dados do 2.º titular — explicitamente, e dito no ecrã.
====================================================================
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.encryption import decrypt_client_data, encrypt_client_data
from services.partner_portal_read import resolver_caso
from services.partner_visibility import ETAPA_DEVOLVIDA, ETAPA_LEAD, ETAPA_PENDENTE, etapa_de_uma_lead
from services.public_form_config import load_merged_form_fields
from utils.input_sanitization import (
    sanitize_email,
    sanitize_nif,
    sanitize_phone,
    sanitize_string,
)

logger = logging.getLogger(__name__)

#: Os passos do formulário público que uma lead guarda.
PASSO_DO_TITULAR = 1
PASSO_DO_SEGUNDO_TITULAR = 2
PASSOS = (PASSO_DO_TITULAR, PASSO_DO_SEGUNDO_TITULAR)

ROTULOS_DOS_PASSOS = {
    PASSO_DO_TITULAR: "Dados do titular",
    PASSO_DO_SEGUNDO_TITULAR: "2.º titular",
}

#: Onde cada `data_path` do formulário vive na ficha do cliente.
DATA_PATHS = ("root", "personal_data", "titular2_data")

#: O campo que liga o 2.º titular no formulário público, e o valor que o liga.
CAMPO_DO_SEGUNDO_TITULAR = "compra_tipo"
VALOR_DO_SEGUNDO_TITULAR = "outra_pessoa"

#: Campos de raiz → onde caem no documento do cliente.
_RAIZ_PARA_FICHA = {"name": ("nome", None), "email": ("contacto", "email"), "phone": ("contacto", "telefone")}

#: Obrigatórios SEMPRE (uma lead sem nome ou email não tem como ser tratada).
OBRIGATORIOS_DA_LEAD = frozenset({"name", "email"})

ETAPAS_EDITAVEIS = (ETAPA_PENDENTE, ETAPA_DEVOLVIDA, ETAPA_LEAD)

ERRO_NAO_EDITAVEL = "Estes dados já não podem ser editados por si."

_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TAMANHO_MAXIMO = 300


class ClientFormIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: `field_key` → valor, exactamente como o formulário público os nomeia.
    values: dict[str, Any] = Field(..., max_length=60)


# ════════════════════════════════════════════════════════════════════
#  O ESQUEMA (PURO)
# ════════════════════════════════════════════════════════════════════
def _opcoes(campo: dict) -> list[dict]:
    """As opções como ``{value, label}`` — o ecrã mostra a etiqueta, o
    servidor valida o valor (o formulário público mistura as duas formas)."""
    opcoes: list[dict] = []
    for opcao in campo.get("options") or []:
        if isinstance(opcao, dict):
            valor = opcao.get("value", opcao.get("label"))
            etiqueta = opcao.get("label", valor)
        else:
            valor = etiqueta = opcao
        if valor not in (None, ""):
            opcoes.append({"value": str(valor), "label": str(etiqueta)})
    return opcoes


def construir_esquema(campos: list[dict]) -> list[dict]:
    """Os passos do formulário que uma lead edita, a partir do `form_config`.

    Devolve ``[{step, label, fields: [...]}]`` — só campos visíveis, nos
    passos 1 e 2, com `data_path` conhecido. Cada campo leva o que o ecrã
    precisa para o desenhar sem conhecer o servidor.
    """
    passos: dict[int, list[dict]] = {p: [] for p in PASSOS}
    for campo in sorted(campos or [], key=lambda c: (int(c.get("step") or 0), c.get("order_index", c.get("order", 0)))):
        chave = str(campo.get("field_key") or "").strip()
        passo = int(campo.get("step") or 0)
        if not chave or passo not in PASSOS or not campo.get("is_visible"):
            continue
        if campo.get("data_path") not in DATA_PATHS:
            continue
        passos[passo].append({
            "field_key": chave,
            "label": campo.get("label") or chave,
            "field_type": campo.get("field_type") or "text",
            "is_required": bool(campo.get("is_required")) or chave in OBRIGATORIOS_DA_LEAD,
            "options": _opcoes(campo),
            "placeholder": campo.get("placeholder"),
            "hint": campo.get("hint") or campo.get("help_text"),
            "data_path": campo["data_path"],
            "depends_on": campo.get("depends_on"),
        })
    return [
        {"step": p, "label": ROTULOS_DOS_PASSOS[p], "fields": passos[p]}
        for p in PASSOS
        if passos[p]
    ]


def _campos_por_chave(esquema: list[dict]) -> dict[str, dict]:
    return {f["field_key"]: f for passo in esquema for f in passo["fields"]}


# ════════════════════════════════════════════════════════════════════
#  LER E ESCREVER VALORES NA FICHA (PURAS)
# ════════════════════════════════════════════════════════════════════
def _chave_do_segundo_titular(chave: str) -> str:
    return chave[len("titular2_"):] if chave.startswith("titular2_") else chave


def ler_valor(cliente: dict, campo: dict) -> Any:
    chave = campo["field_key"]
    destino = campo["data_path"]
    if destino == "root":
        grupo, nome = _RAIZ_PARA_FICHA.get(chave, (None, None))
        if grupo is None:
            return None
        return cliente.get(grupo) if nome is None else (cliente.get(grupo) or {}).get(nome)
    if destino == "personal_data":
        return (cliente.get("dados_pessoais") or {}).get(chave)
    return (cliente.get("titular2_data") or {}).get(_chave_do_segundo_titular(chave))


def escrever_valor(cliente: dict, campo: dict, valor: Any) -> None:
    chave = campo["field_key"]
    destino = campo["data_path"]
    if destino == "root":
        grupo, nome = _RAIZ_PARA_FICHA[chave]
        if nome is None:
            cliente[grupo] = valor
        else:
            cliente.setdefault(grupo, {})
            cliente[grupo][nome] = valor
        return
    if destino == "personal_data":
        cliente.setdefault("dados_pessoais", {})
        cliente["dados_pessoais"][chave] = valor
        return
    if not isinstance(cliente.get("titular2_data"), dict):
        cliente["titular2_data"] = {}
    cliente["titular2_data"][_chave_do_segundo_titular(chave)] = valor


def segundo_titular_ligado(cliente: dict) -> bool:
    return (cliente.get("dados_pessoais") or {}).get(CAMPO_DO_SEGUNDO_TITULAR) == VALOR_DO_SEGUNDO_TITULAR


# ════════════════════════════════════════════════════════════════════
#  VALIDAR (PURA)
# ════════════════════════════════════════════════════════════════════
def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip()) or valor == []


def validar_valor(campo: dict, valor: Any) -> Any:
    """O valor limpo, ou 400. Vazio é válido (apaga o campo)."""
    chave, tipo = campo["field_key"], campo.get("field_type") or "text"
    rotulo = campo.get("label") or chave
    if _vazio(valor):
        return None

    def erro(motivo: str) -> HTTPException:
        return HTTPException(status_code=400, detail=f"«{rotulo}»: {motivo}")

    if chave.endswith("nif") and chave not in ("employer_nif",):
        limpo = sanitize_nif(str(valor))
        if not limpo:
            raise erro("NIF inválido.")
        return limpo
    if tipo == "email":
        limpo = sanitize_email(str(valor))
        if not limpo:
            raise erro("email inválido.")
        return limpo
    if tipo == "tel":
        limpo = sanitize_phone(str(valor))
        if not limpo:
            raise erro("telefone inválido.")
        return limpo
    if tipo == "date":
        texto = str(valor).strip()
        if not _DATA_ISO.match(texto):
            raise erro("use o formato AAAA-MM-DD.")
        try:
            datetime.strptime(texto, "%Y-%m-%d")
        except ValueError:
            raise erro("data inexistente.")
        return texto
    if tipo in ("select", "radio"):
        texto = str(valor).strip()
        if texto not in [o["value"] for o in campo.get("options", [])]:
            raise erro("escolha uma das opções.")
        return texto
    if tipo == "number":
        try:
            numero = float(str(valor).replace(",", "."))
        except ValueError:
            raise erro("indique um número.")
        return int(numero) if numero.is_integer() else numero
    if tipo == "checkbox":
        if isinstance(valor, bool):
            return valor
        raise erro("valor inválido.")
    texto = sanitize_string(str(valor), max_length=_TAMANHO_MAXIMO)
    if not texto:
        raise erro("valor inválido.")
    return texto


# ════════════════════════════════════════════════════════════════════
#  CARREGAR A FICHA COMPLETA DO CASO
# ════════════════════════════════════════════════════════════════════
async def _ficha(caso) -> tuple[Any, dict]:
    """(colecção, documento completo) da lead. Um processo nunca chega aqui."""
    colecao = db.partner_drafts if caso.e_rascunho else db.clients
    doc = await colecao.find_one({"id": caso.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    return colecao, doc


def _exigir_editavel(caso) -> None:
    if caso.e_processo or etapa_de_uma_lead(caso.client or {}) not in ETAPAS_EDITAVEIS:
        raise HTTPException(status_code=409, detail=ERRO_NAO_EDITAVEL)


# ════════════════════════════════════════════════════════════════════
#  LER
# ════════════════════════════════════════════════════════════════════
async def run_get_client_form(partner: dict, case_id: str) -> dict:
    caso = await resolver_caso(partner, case_id)
    esquema = construir_esquema(await load_merged_form_fields())
    if caso.e_processo:
        return {"editavel": False, "passos": esquema, "values": {}, "segundo_titular": False}

    _, doc = await _ficha(caso)
    cliente = decrypt_client_data(doc)
    valores: dict[str, Any] = {}
    for campo in _campos_por_chave(esquema).values():
        valor = ler_valor(cliente, campo)
        if not _vazio(valor):
            valores[campo["field_key"]] = valor
    return {
        "editavel": etapa_de_uma_lead(caso.client or {}) in ETAPAS_EDITAVEIS,
        "passos": esquema,
        "values": valores,
        "segundo_titular": segundo_titular_ligado(cliente),
        "ligar_segundo_titular": {"field": CAMPO_DO_SEGUNDO_TITULAR, "value": VALOR_DO_SEGUNDO_TITULAR},
    }


# ════════════════════════════════════════════════════════════════════
#  GUARDAR
# ════════════════════════════════════════════════════════════════════
async def run_save_client_form(partner: dict, case_id: str, data: ClientFormIn) -> dict:
    caso = await resolver_caso(partner, case_id)
    _exigir_editavel(caso)

    esquema = construir_esquema(await load_merged_form_fields())
    campos = _campos_por_chave(esquema)

    desconhecidos = sorted(k for k in data.values if k not in campos)
    if desconhecidos:
        raise HTTPException(
            status_code=400,
            detail=f"Campos desconhecidos: {', '.join(desconhecidos[:10])}.",
        )

    colecao, doc = await _ficha(caso)
    cliente = decrypt_client_data(doc)
    tinha_segundo = segundo_titular_ligado(cliente)

    # 1. Valida tudo ANTES de escrever o que quer que seja.
    limpos = {chave: validar_valor(campos[chave], valor) for chave, valor in data.values.items()}

    # 2. Aplica sobre a ficha (em memória).
    for chave, valor in limpos.items():
        campo = campos[chave]
        if campo["data_path"] == "titular2_data":
            continue  # depois de saber se o 2.º titular está ligado
        escrever_valor(cliente, campo, valor)

    ligado = segundo_titular_ligado(cliente)
    pedidos_do_segundo = {k: v for k, v in limpos.items() if campos[k]["data_path"] == "titular2_data"}
    if pedidos_do_segundo and not ligado:
        raise HTTPException(
            status_code=400,
            detail="Active «com outra pessoa» antes de preencher o 2.º titular.",
        )
    if tinha_segundo and not ligado:
        # Desligar apaga os dados do 2.º titular — explicitamente.
        cliente["titular2_data"] = {}
    for chave, valor in pedidos_do_segundo.items():
        escrever_valor(cliente, campos[chave], valor)
    if ligado:
        nome_do_segundo = (cliente.get("titular2_data") or {}).get("name")
        if _vazio(nome_do_segundo):
            raise HTTPException(status_code=400, detail="Indique o nome do 2.º titular.")

    # 3. O que é sempre obrigatório numa lead.
    for chave in OBRIGATORIOS_DA_LEAD:
        if chave in campos and _vazio(ler_valor(cliente, campos[chave])):
            raise HTTPException(status_code=400, detail=f"«{campos[chave]['label']}» é obrigatório.")

    # 4. Cifra, recalcula os blind indexes e grava só as secções tocadas.
    agora = datetime.now(timezone.utc).isoformat()
    cliente["updated_at"] = agora
    if caso.e_rascunho:
        cliente["last_activity_at"] = agora
    try:
        cifrado = encrypt_client_data(cliente)
    except Exception as exc:  # noqa: BLE001 — sem cifra não se grava PII em claro
        logger.error("[PARCEIRO] Falha a cifrar a edição de %s: %s", caso.id, exc)
        raise HTTPException(status_code=500, detail="Não foi possível guardar. Tente novamente.")

    sets = {k: cifrado[k] for k in ("nome", "contacto", "dados_pessoais", "titular2_data", "updated_at") if k in cifrado}
    if caso.e_rascunho:
        sets["last_activity_at"] = agora
    elif doc.get("submitted_by_partner_id"):
        sets["last_activity_at"] = agora
    await colecao.update_one({"id": caso.id}, {"$set": sets})

    return {
        "success": True,
        "campos_guardados": sorted(limpos),
        "segundo_titular": ligado,
    }


__all__ = [
    "ClientFormIn",
    "OBRIGATORIOS_DA_LEAD",
    "construir_esquema",
    "ler_valor",
    "escrever_valor",
    "run_get_client_form",
    "run_save_client_form",
    "segundo_titular_ligado",
    "validar_valor",
]
