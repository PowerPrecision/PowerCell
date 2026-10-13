"""
====================================================================
«O Meu Perfil» do Portal — as secções para além dos dados pessoais (Out 2026)
====================================================================
O perfil do Portal só mostrava o passo 1 do registo (dados pessoais + contactos).
O pedido: espelhar TODO o formulário de registo — segundo titular, imóvel
pretendido e situação financeira — e garantir que o `PUT /portal/me` os grava.

ONDE ESTÁ CADA DADO (e porque é que isto não é «só mais uns campos»)
  O cliente é o dono do que foi dito no registo, mas o PROCESSO guarda a sua
  cópia, e é a do processo que o CRM mostra em «Detalhes do Processo»:

    secção               cliente                         processo
    ───────────────────  ──────────────────────────────  ───────────────
    segundo titular      `titular2_data`                 `titular2_data`
    imóvel pretendido    `pending_real_estate_data`      `real_estate_data`
    situação financeira  `dados_financeiros`             `financial_data`

  Gravar só no cliente deixava o CRM a mostrar o valor antigo (a cópia do
  processo é lida primeiro) — um «guardado com sucesso» que não chega a quem
  decide. Por isso cada escrita vai para o cliente **e** para os processos dele
  (`espelhar_nos_processos`), e a leitura prefere o processo e cai no cliente
  (`valores_da_seccao`).

  O perfil só é editável enquanto NENHUM processo do cliente saiu da recolha
  (`portal_profile.construir_query_do_perfil_trancado`), logo os processos a que
  se escreve estão todos na fase em que o cliente é quem manda nos dados.

REGRAS QUE NÃO SE PODEM PERDER
  * **O que se vê não é o que se grava.** O NIF (do titular e do 2.º) e o nome do
    2.º titular aparecem SÓ DE LEITURA e o NIF MASCARADO; as listas de bancos não
    têm editor e ficam só de leitura. Tudo o que não está no esquema editável é
    `recusado` e dito ao cliente (nunca descartado em silêncio).
  * **Só se escreve o 2.º titular a quem declarou ter um.** `compra_tipo` é
    campo trancado: o cliente não passa a «ter» um 2.º titular pelo perfil.
  * **Um nome, vários alias.** O registo grava o mesmo dado com mais de um nome
    (`salario_liquido`/`monthly_income`/`rendimento_mensal`; `employment_type`/
    `tipo_contrato`…). Escrever só o canónico faz o alias antigo «ressuscitar» o
    valor no ecrã do CRM — o defeito dos campos limpos. `expandir_aliases` escreve
    todos, e o `rendimento_anual` deriva do mensal.
  * **PII cifrada como no registo**: `documento_id`/`phone` do 2.º titular e o NIF
    da entidade patronal.
  * **Tipos.** Número que não é número é `recusado` (não vira texto); lista de
    opções é lista; checkbox simples é booleano.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Grupo do formulário → campo onde vive na ficha do CLIENTE.
CAMPO_DO_CLIENTE = {
    "titular2_data": "titular2_data",
    "real_estate_data": "pending_real_estate_data",
    "financial_data": "dados_financeiros",
}

#: Grupo do formulário → campo onde vive no PROCESSO (a cópia que o CRM lê primeiro).
CAMPO_DO_PROCESSO = {
    "titular2_data": "titular2_data",
    "real_estate_data": "real_estate_data",
    "financial_data": "financial_data",
}

#: Campos cifrados em repouso, por grupo (como o registo e o CRM os gravam).
CAMPOS_CIFRADOS = {
    "titular2_data": frozenset({"documento_id", "phone", "telefone", "nif"}),
    "financial_data": frozenset({"employer_nif"}),
}

#: Nomes alternativos escritos pelo registo para o MESMO dado (ver
#: `campos_limpaveis.ALIASES_FINANCEIROS`, que é o lado de leitura/limpeza).
ALIASES_ESCRITOS: dict[str, dict[str, tuple[str, ...]]] = {
    "financial_data": {
        "salario_liquido": ("monthly_income", "rendimento_mensal"),
        "employment_type": ("tipo_contrato",),
        "employment_duration": ("antiguidade_emprego",),
        "employer_name": ("empresa",),
    },
    "real_estate_data": {
        "ja_tem_casa_escolhida": ("ja_tem_imovel", "has_property"),
    },
}

_VAZIO = (None, "")


def _esta_vazio(valor: Any) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    if isinstance(valor, (list, tuple, dict, set)):
        return len(valor) == 0
    return False


# ====================================================================
# Máscaras e resumos (só de leitura)
# ====================================================================

def mascarar_nif(nif: Any) -> str:
    """`123456789` → `••••••789`. Vazio fica vazio; o que não tem 4+ dígitos fica todo oculto."""
    texto = "".join(c for c in str(nif or "") if c.isalnum())
    if not texto:
        return ""
    if len(texto) <= 3:
        return "•" * len(texto)
    return "•" * (len(texto) - 3) + texto[-3:]


def resumir_lista(valor: Any) -> str:
    """Texto de uma lista de bancos para mostrar só de leitura.

    `[{"banco": "BPI", "valor": 12000}, "CGD"]` → `BPI (12000 €), CGD`.
    """
    if _esta_vazio(valor):
        return ""
    if not isinstance(valor, (list, tuple)):
        return str(valor)
    partes = []
    for item in valor:
        if isinstance(item, dict):
            nome = item.get("banco") or item.get("nome") or item.get("name") or ""
            quantia = item.get("valor")
            partes.append(f"{nome} ({quantia} €)" if nome and quantia not in _VAZIO else str(nome))
        elif not _esta_vazio(item):
            partes.append(str(item))
    return ", ".join(p for p in partes if p)


# ====================================================================
# Cifra
# ====================================================================

def _decifrar(valor: Any) -> Any:
    if not isinstance(valor, str) or not valor.startswith("ENC:"):
        return valor
    try:
        from services.encryption import decrypt_value

        claro = decrypt_value(valor)
        return claro if claro else valor
    except Exception:  # noqa: BLE001 - ilegível não derruba o perfil
        return valor


def _cifrar(grupo: str, chave: str, valor: Any) -> Any:
    if chave not in CAMPOS_CIFRADOS.get(grupo, frozenset()) or _esta_vazio(valor):
        return valor
    if isinstance(valor, str) and valor.startswith("ENC:"):
        return valor
    try:
        from services.encryption import encrypt_value

        cifrado = encrypt_value(str(valor))
        return cifrado or valor
    except Exception:  # noqa: BLE001
        logger.warning("[PORTAL-PERFIL] Não foi possível cifrar %s.%s", grupo, chave)
        return valor


# ====================================================================
# Leitura
# ====================================================================

def valores_da_seccao(grupo: str, cliente: Optional[dict], processo: Optional[dict]) -> dict:
    """Os valores (decifrados) de um grupo: o PROCESSO manda, o cliente preenche o que falta.

    O CRM lê a cópia do processo primeiro; mostrar ao cliente outra coisa seria
    mostrar-lhe um dado diferente do que a equipa vê.
    """
    do_cliente = (cliente or {}).get(CAMPO_DO_CLIENTE[grupo])
    if grupo == "real_estate_data" and _esta_vazio(do_cliente):
        do_cliente = (cliente or {}).get("dados_imobiliarios")
    do_processo = (processo or {}).get(CAMPO_DO_PROCESSO[grupo])

    saida: dict = {}
    for fonte in (do_cliente, do_processo):
        if not isinstance(fonte, dict):
            continue
        for chave, valor in fonte.items():
            if chave.endswith("_hash"):
                continue
            if _esta_vazio(valor) and chave in saida:
                continue
            saida[chave] = _decifrar(valor)
    return saida


def tem_segundo_titular(cliente: Optional[dict], processo: Optional[dict] = None) -> bool:
    """O cliente declarou um 2.º titular (`compra_tipo = outra_pessoa`) ou já há dados dele."""
    pessoais = (cliente or {}).get("dados_pessoais") or {}
    if str(pessoais.get("compra_tipo") or "").strip() == "outra_pessoa":
        return True
    for fonte in ((cliente or {}).get("titular2_data"), (processo or {}).get("titular2_data")):
        if isinstance(fonte, dict) and any(
            not _esta_vazio(fonte.get(c)) for c in ("name", "nif", "email", "phone")
        ):
            return True
    return False


def valores_somente_leitura(schema: list[dict], cliente: dict, valores: dict[str, dict]) -> dict:
    """`{field_key: texto}` dos campos só de leitura: NIF mascarado, nome, listas resumidas."""
    pessoais = (cliente or {}).get("dados_pessoais") or {}
    saida: dict[str, str] = {}
    for entrada in schema or []:
        if not entrada.get("read_only"):
            continue
        grupo, nome = entrada["destino"]
        chave = entrada["field_key"]
        if grupo == "dados_pessoais":
            bruto = _decifrar(pessoais.get(nome))
        else:
            bruto = (valores.get(grupo) or {}).get(nome)
        if nome == "nif":
            saida[chave] = mascarar_nif(bruto)
        elif isinstance(bruto, (list, tuple)):
            saida[chave] = resumir_lista(bruto)
        else:
            saida[chave] = "" if _esta_vazio(bruto) else str(bruto)
    return saida


# ====================================================================
# Escrita
# ====================================================================

def _coagir(entrada: dict, valor: Any) -> tuple[bool, Any]:
    """`(aceite, valor_normalizado)` segundo o tipo do campo no formulário."""
    tipo = entrada.get("field_type") or "text"
    tem_opcoes = bool(entrada.get("options"))

    if tipo == "number":
        if _esta_vazio(valor):
            return True, None
        try:
            texto = str(valor).strip().replace(" ", "").replace(",", ".")
            numero = float(texto)
        except (TypeError, ValueError):
            return False, None
        if numero != numero or numero in (float("inf"), float("-inf")):
            return False, None
        return True, numero

    if tipo == "checkbox":
        if tem_opcoes:
            if _esta_vazio(valor):
                return True, None
            if not isinstance(valor, (list, tuple)):
                return False, None
            permitidas = {
                o if isinstance(o, str) else (o.get("value") if isinstance(o, dict) else None)
                for o in entrada.get("options") or []
            }
            escolhidas = [v for v in valor if isinstance(v, str)]
            if len(escolhidas) != len(valor) or any(v not in permitidas for v in escolhidas):
                return False, None
            return True, list(escolhidas)
        if valor is None or _esta_vazio(valor) and not isinstance(valor, bool):
            return True, None
        if isinstance(valor, bool):
            return True, valor
        return False, None

    # texto, data, select, radio, textarea, email, tel
    if _esta_vazio(valor):
        return True, ""
    if isinstance(valor, (dict, list, tuple, set)):
        return False, None
    texto = str(valor).strip()
    if tem_opcoes and tipo in ("select", "radio"):
        permitidas = {
            str(o if isinstance(o, str) else (o.get("value") if isinstance(o, dict) else ""))
            for o in entrada.get("options") or []
        }
        if texto not in permitidas:
            return False, None
    return True, texto


def expandir_aliases(grupo: str, chave: str, valor: Any) -> dict:
    """O valor escrito sob o nome canónico E sob os alias que o registo também grava."""
    escritos = {chave: valor}
    for alias in ALIASES_ESCRITOS.get(grupo, {}).get(chave, ()):
        escritos[alias] = valor
    if grupo == "financial_data" and chave == "salario_liquido":
        # O registo grava o anual como mensal × 12; sem isto o CRM ficava com o antigo.
        escritos["rendimento_anual"] = valor * 12 if isinstance(valor, (int, float)) else None
    return escritos


def construir_update_das_seccoes(
    pedido: dict[str, Optional[dict]],
    *,
    cliente: dict,
    schema: list[dict],
    permitidos: dict[str, set],
    agora: str,
    recusados: list,
) -> tuple[dict, dict[str, dict]]:
    """O `$set` do cliente e os valores a espelhar nos processos.

    ``pedido`` é `{grupo: {campo: valor}}` (só os três grupos das secções).
    Devolve ``(set_do_cliente, espelhos)`` onde ``espelhos`` é `{grupo: {campo: valor}}`
    já cifrado e com alias. Campos fora do allowlist, de tipo errado ou do 2.º titular
    de quem não o declarou são acrescentados a ``recusados`` — nunca descartados em silêncio.
    """
    indice = {
        (e["destino"][0], e["destino"][1]): e
        for e in schema or []
        if not e.get("read_only") and e["destino"][0] in CAMPO_DO_CLIENTE
    }
    com_segundo = tem_segundo_titular(cliente)

    set_do_cliente: dict[str, Any] = {}
    espelhos: dict[str, dict] = {}

    for grupo, campos in (pedido or {}).items():
        if grupo not in CAMPO_DO_CLIENTE or not campos:
            continue
        if not isinstance(campos, dict):
            recusados.append(grupo)
            continue
        liberados = permitidos.get(grupo) or set()
        for chave, valor in campos.items():
            entrada = indice.get((grupo, chave))
            if chave not in liberados or entrada is None:
                recusados.append(chave)
                continue
            if grupo == "titular2_data" and not com_segundo:
                recusados.append(chave)
                continue
            aceite, normalizado = _coagir(entrada, valor)
            if not aceite:
                recusados.append(chave)
                continue
            for nome, v in expandir_aliases(grupo, chave, normalizado).items():
                cifrado = _cifrar(grupo, nome, v)
                set_do_cliente[f"{CAMPO_DO_CLIENTE[grupo]}.{nome}"] = cifrado
                espelhos.setdefault(grupo, {})[nome] = cifrado

    if set_do_cliente:
        set_do_cliente["updated_at"] = agora
    return set_do_cliente, espelhos


async def espelhar_nos_processos(db, process_ids: list, espelhos: dict[str, dict]) -> int:
    """Copia os valores para a cópia de cada processo. Devolve quantos processos tocou.

    Um grupo ausente ou `null` no processo não aceita chaves pontuadas (o MongoDB recusa
    `titular2_data.nif` sobre `null`), por isso o grupo é criado inteiro nesse caso.
    """
    if not espelhos or not process_ids:
        return 0
    tocados = 0
    projeccao = {"_id": 0, "id": 1, **{CAMPO_DO_PROCESSO[g]: 1 for g in espelhos}}
    processos = await db.processes.find({"id": {"$in": list(process_ids)}}, projeccao).to_list(50)
    for processo in processos:
        para_definir: dict[str, Any] = {}
        for grupo, valores in espelhos.items():
            campo = CAMPO_DO_PROCESSO[grupo]
            if isinstance(processo.get(campo), dict):
                for nome, v in valores.items():
                    para_definir[f"{campo}.{nome}"] = v
            else:
                para_definir[campo] = dict(valores)
        if para_definir:
            await db.processes.update_one({"id": processo["id"]}, {"$set": para_definir})
            tocados += 1
    return tocados


def dados_financeiros_do_registo(financial_data: Optional[dict]) -> dict:
    """Os dados financeiros do registo público prontos a gravar no cliente.

    Cifra o NIF da entidade patronal e deita fora o que não é um dicionário. Valores
    `None` ficam como vieram (o ecrã do CRM trata-os como «sem valor»).
    """
    if not isinstance(financial_data, dict):
        return {}
    return {
        chave: _cifrar("financial_data", chave, valor)
        for chave, valor in financial_data.items()
        if isinstance(chave, str) and not chave.endswith("_hash")
    }
