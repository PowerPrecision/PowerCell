"""Apagar um campo opcional: o que «apagar» significa em cada sítio onde o dado vive.

O QUE FALHAVA
  Apagar o email num processo já funcionava (``encryption.limpar_blind_indexes_de_campos_vazios``,
  ``client_crud.sync_de_contactos_limpos``). Apagar o NIF — ou a morada, a
  naturalidade… — dava o toast de sucesso e o valor antigo voltava, porque a
  ficha do cliente é só UMA das cópias do dado:

    * o PROCESSO guarda cópias (``client_nif`` na raiz, ``personal_data.*``);
    * a pesquisa usa um índice cego (``personal_data.nif_hash``) que também
      vive no processo — apagar o valor sem apagar o hash deixa o processo
      «encontrável» pelo NIF que já não existe;
    * há NOMES ALTERNATIVOS para o mesmo dado (``morada`` / ``address`` para
      ``morada_fiscal``, ``birth_date`` para ``data_nascimento``…) que a
      hidratação do ecrã usa como recurso quando o canónico está vazio — logo
      apagar só o canónico faz o alternativo «ressuscitar» o valor.

  E a leitura (``process_service.populate_client_data``) só recompõe a partir do
  cliente quando o do processo está vazio: bastava UMA cópia ficar para trás.

REGRA DE FUNDO (a mesma do email)
  Chave presente e vazia (``""``, ``null``, só espaços) = «apaga». Chave ausente
  = «não alterei». Um espelho vazio que o formulário reenvia em toda a gravação
  NÃO é um pedido para apagar (ver ``process_service.extract_client_updates_from_body``).

O QUE NÃO SE APAGA POR AQUI
  * o NOME do cliente (``nome``): é o identificador que o resto do sistema mostra
    e pesquisa. Pedir para o apagar é um erro e responde-se 400 (``exigir_nome``),
    em vez de ignorar em silêncio — ignorar é o mesmo sintoma do bug que isto
    corrige (grava «com sucesso» e o valor volta);
  * os contactos (email/telefone), que têm o seu próprio caminho.

Módulo PURO: sem I/O. Quem escreve na base é o chamador.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

#: Nomes alternativos de um campo de ``dados_pessoais`` (cliente) / ``personal_data`` (processo).
#: Simétrico onde o dado tem dois nomes equivalentes.
ALIASES_PESSOAIS: dict[str, tuple[str, ...]] = {
    "morada_fiscal": ("morada", "address"),
    "data_nascimento": ("birth_date",),
    "birth_date": ("data_nascimento",),
    "estado_civil": ("marital_status",),
    "nacionalidade": ("nationality",),
}

#: Nomes alternativos de ``financial_data`` que a hidratação do ecrã usa como
#: recurso do campo canónico (ver ``frontend/.../processDetailsHydration.js``).
ALIASES_FINANCEIROS: dict[str, tuple[str, ...]] = {
    "monthly_income": ("rendimento_mensal", "salario_liquido"),
    "rendimento_bruto": ("salario_bruto",),
    "capital_proprio": ("other_income",),
    "nr_dependentes": ("number_of_dependents",),
    "employer_name": ("empresa", "entidade_patronal"),
    "employment_type": ("tipo_contrato",),
    "employment_duration": ("antiguidade_emprego",),
}

#: Campos de ``dados_pessoais`` que este caminho NÃO limpa: nome (obrigatório),
#: contactos (têm o seu caminho) e índices cegos (derivam do valor).
_FORA_DA_LIMPEZA_GENERICA = frozenset({
    "nome", "name", "nome_completo",
    "email", "telefone", "phone", "telefone_secundario", "email_secundario",
})

#: Campos que não são texto: ``None`` é o seu «sem valor» e ``""`` seria um tipo errado.
_NAO_TEXTO = frozenset({"menor_35_anos"})

#: Campos com índice cego que vive TAMBÉM no processo (``personal_data.<indice>``).
_INDICES_NO_PROCESSO: dict[str, str] = {"nif": "nif_hash"}

#: Cópias na RAIZ do processo.
_RAIZ_DO_PROCESSO: dict[str, str] = {"nif": "client_nif"}


def esta_vazio(valor: Any) -> bool:
    """``None``, ``""`` e só espaços: o campo foi limpo."""
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _e_indice(campo: str) -> bool:
    return campo.endswith("_hash")


def campos_pessoais_limpos(dados: Optional[dict]) -> list[str]:
    """Campos de ``dados_pessoais`` que a submissão ESCREVEU vazios (chave presente).

    Normaliza o valor para ``""`` (``None`` e espaços passam a ``""``) e devolve os
    nomes, na ordem em que aparecem. Só mexe nas chaves que a submissão trouxe: uma
    chave ausente é «não alterei». Não inclui o nome, os contactos nem os índices.
    """
    limpos: list[str] = []
    if not isinstance(dados, dict):
        return limpos
    for campo in list(dados):
        if campo in _FORA_DA_LIMPEZA_GENERICA or campo in _NAO_TEXTO or _e_indice(campo):
            continue
        valor = dados[campo]
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            dados[campo] = ""
            limpos.append(campo)
    return limpos


def campos_pessoais_limpos_em_updates(updates: Optional[dict]) -> list[str]:
    """Os campos de ``dados_pessoais`` limpos num ``$set`` de chaves pontuadas.

    Forma que o PUT do processo usa (``{"dados_pessoais.nif": ""}``). Não altera
    ``updates``.
    """
    if not isinstance(updates, dict):
        return []
    prefixo = "dados_pessoais."
    dados = {
        chave[len(prefixo):]: valor
        for chave, valor in updates.items()
        if chave.startswith(prefixo) and "." not in chave[len(prefixo):]
    }
    return campos_pessoais_limpos(dados)


def aliases_do_campo(campo: str, tabela: dict[str, tuple[str, ...]] = ALIASES_PESSOAIS) -> tuple[str, ...]:
    return tabela.get(campo, ())


def aliases_a_limpar_no_cliente(existentes: Optional[dict], campos: Iterable[str]) -> dict:
    """``{alias: ""}`` para os nomes alternativos que a ficha do cliente TEM.

    Só os que existem: criar uma chave ``address: ""`` numa ficha que nunca a teve
    seria ruído. ``existentes`` é a secção ``dados_pessoais`` do cliente.
    """
    base = existentes if isinstance(existentes, dict) else {}
    saida: dict[str, str] = {}
    for campo in campos:
        for alias in aliases_do_campo(campo):
            if alias in base and not esta_vazio(base[alias]):
                saida[alias] = ""
    return saida


def espelhos_no_processo(processo: Optional[dict], campos: Iterable[str]) -> dict:
    """``$set`` que apaga, NO PROCESSO, as cópias dos campos pessoais limpos.

    Cobre, só onde existem (``populate_client_data`` recompõe a partir do cliente o
    que falta, e o cliente já está limpo):

      * ``personal_data.<campo>`` e os seus nomes alternativos;
      * o índice cego (``personal_data.nif_hash``) e a cópia da raiz (``client_nif``)
        quando o campo é o NIF.
    """
    doc = processo if isinstance(processo, dict) else {}
    pd = doc.get("personal_data") if isinstance(doc.get("personal_data"), dict) else {}
    sets: dict[str, str] = {}
    for campo in campos:
        for nome in (campo, *aliases_do_campo(campo)):
            if nome in pd and not esta_vazio(pd[nome]):
                sets[f"personal_data.{nome}"] = ""
        indice = _INDICES_NO_PROCESSO.get(campo)
        if indice and indice in pd and not esta_vazio(pd[indice]):
            sets[f"personal_data.{indice}"] = ""
        raiz = _RAIZ_DO_PROCESSO.get(campo)
        if raiz and raiz in doc and not esta_vazio(doc[raiz]):
            sets[raiz] = ""
    return sets


def aliases_financeiros_a_remover(incoming: Optional[dict]) -> set[str]:
    """Nomes alternativos de ``financial_data`` a retirar porque o canónico foi limpo.

    ``incoming`` é o que o pedido trouxe. O canónico limpo (chave presente e vazia)
    leva consigo os alternativos — senão o ecrã volta a mostrá-los no lugar dele.
    """
    if not isinstance(incoming, dict):
        return set()
    remover: set[str] = set()
    for canonico, aliases in ALIASES_FINANCEIROS.items():
        if canonico in incoming and esta_vazio(incoming[canonico]):
            remover.update(aliases)
    # Um alternativo que o pedido TRAZ preenchido não se retira: é uma escrita explícita.
    return {a for a in remover if a not in incoming or esta_vazio(incoming[a])}


def exigir_nome(campos_enviados: Iterable[str], nome: Any) -> None:
    """Recusa (400) um pedido que tenta APAGAR o nome do cliente.

    ``campos_enviados`` é ``model_fields_set`` do pedido: distingue «não mandei o
    nome» (legítimo) de «mandei o nome vazio» (erro).
    """
    from fastapi import HTTPException

    if "nome" in set(campos_enviados) and esta_vazio(nome):
        raise HTTPException(
            status_code=400,
            detail="O nome do cliente é obrigatório e não pode ficar vazio.",
        )


async def limpar_espelhos_nos_processos(
    db,
    client_id: Optional[str],
    process_ids: Optional[Iterable[str]],
    campos: Iterable[str],
    *,
    excluir: Optional[Iterable[str]] = None,
) -> int:
    """Apaga as cópias dos campos pessoais limpos em TODOS os processos do cliente.

    Procura pelos ``process_ids`` da ficha E por ``client_id``: o ``process_ids`` do
    cliente nem sempre está mantido, e um processo que escapasse guardava o NIF
    antigo (e o índice cego) para sempre. Cada processo leva só o ``$set`` do que
    ele de facto tem (``espelhos_no_processo``). ``excluir`` são ids já tratados
    pelo chamador (o processo do próprio pedido). Devolve quantos foram escritos.

    O ``db`` é do módulo do chamador (não um ``from database import db`` aqui):
    os testes que o substituem no escritor não apanhariam outro.
    """
    campos = list(campos)
    if not campos:
        return 0
    ids = [p for p in (process_ids or []) if p]
    ramos: list[dict] = []
    if ids:
        ramos.append({"id": {"$in": ids}})
    if client_id:
        ramos.append({"client_id": client_id})
    if not ramos:
        return 0
    ignorados = set(excluir or ())
    escritos = 0
    cursor = db.processes.find(
        {"$or": ramos} if len(ramos) > 1 else ramos[0],
        {"_id": 0, "id": 1, "client_nif": 1, "personal_data": 1},
    )
    async for doc in cursor:
        if doc.get("id") in ignorados:
            continue
        sets = espelhos_no_processo(doc, campos)
        if sets:
            await db.processes.update_one({"id": doc["id"]}, {"$set": sets})
            escritos += 1
    return escritos
