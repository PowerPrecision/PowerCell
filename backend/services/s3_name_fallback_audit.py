"""Quanto custa cortar o recurso por NOME (D-19) — a medição.

A PERGUNTA QUE ESTE MÓDULO RESPONDE
===================================
O Lote 6 fez a pasta documental derivar do ID e **despromoveu** a procura
por nome: perdeu o score, ficou só com o match EXACTO e serve a LEITURA
de um registo legado sem `s3_folder` gravado. Apagá-la é o fecho da D-19
— mas apagá-la às cegas esconde documentos que existem, e um documento
que desaparece não produz erro nenhum.

Logo, antes de apagar: **quantas fichas deixam de ver os seus documentos,
e quantos ficheiros são?** É esse número que decide, e é esse número que
este módulo calcula.

O QUE ACONTECE QUANDO O RECURSO CAI
===================================
`s3_storage.list_files` decide por uma coisa só: o `s3_folder` que lhe
passam. Com valor, lê a UNIÃO derivada dele e nunca procura por nome.
Sem valor (`None`, `""`), cai em `_get_possible_client_paths`, que deriva
palpites do NOME. Cortar o recurso é fazer esse segundo ramo devolver
lista vazia — logo o custo mede-se nas fichas SEM `s3_folder`.

CINCO VEREDICTOS, E SÓ DOIS CUSTAM
==================================
``mapeado``            tem `s3_folder`. O corte não lhe toca.
``mapeado_quebrado``   tem `s3_folder` e a pasta não existe no bucket.
                       **Já está partido hoje** — o corte não agrava, mas
                       conta-se porque é a mesma ida ao painel.
``sem_pasta``          não tem `s3_folder` e o nome não resolve para
                       pasta nenhuma. O corte não lhe tira nada: já não
                       vê documentos.
``depende_do_nome``    não tem `s3_folder`, o nome resolve EXACTAMENTE
                       para uma pasta que EXISTE e tem ficheiros. **É
                       este que perde documentos no corte** — e é
                       religável, porque a pasta certa é conhecida.
``colisao_de_nome``    o mesmo que o anterior, mas a pasta é reclamada
                       por DUAS OU MAIS fichas. É a D-19 na sua forma
                       pura: o religamento é obrigatório e uma pessoa tem
                       de decidir de quem é a pasta (o auto-mapeamento
                       recusa-se, e bem).

A ORDEM DOS VEREDICTOS NÃO É ARBITRÁRIA: `colisao_de_nome` tem de ser
avaliado DEPOIS de se conhecerem todas as fichas, porque é uma
propriedade do CONJUNTO e não da ficha. Classificar ficha a ficha dava
`depende_do_nome` às duas e a colisão — o pior caso — ficava invisível,
que é precisamente como a D-19 nasceu.

«FICHEIROS» CONTA-SE SEM OS MARCADORES
======================================
Uma pasta criada pelo `initialize_client_folders` leva um `.keep` por
subpasta. Contar os `.keep` fazia uma pasta VAZIA parecer ter 6
documentos, e o relatório anunciava um custo que não existe — o `list_files`
salta-os. Daí `conta_ficheiros_uteis`.

UMA MEDIÇÃO QUE FALHOU NÃO É UM CUSTO ZERO
==========================================
Sem inventário de pastas, TODAS as fichas sem `s3_folder` caem em
`sem_pasta` e o relatório conclui «pode apagar-se, não custa nada» — que
é a frase mais perigosa que este script pode imprimir. Em dev o S3 não
está configurado e foi exactamente isso que a primeira execução disse.

Daí `inventario_utilizavel`: sem pastas não se classifica, recusa-se.
É a mesma regra do `rede_consensual` do `backfill_network_id` — perante
uma pergunta sem resposta, não adivinhar.

ESTE MÓDULO NÃO SABE O QUE É MONGO NEM O QUE É S3
=================================================
Recebe fichas e um inventário de pastas e devolve veredictos. Quem lê a
base de dados e o bucket é o `scripts/diagnose_s3_name_fallback.py`. É o
que permite afirmar a aritmética do relatório num teste sem rede — e a
aritmética é a única coisa que aqui pode estar errada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from services.s3_document_root import RAIZ, e_id_gerado

#: Nome da pasta → caminho completo, em minúsculas, como o
#: `_find_client_folder_combined` compara. É a ÚNICA forma de comparação
#: aqui: o match por score foi o que produziu a colisão original e
#: reintroduzi-lo na medição daria um custo inflacionado e falso.
VEREDICTO_MAPEADO = "mapeado"
VEREDICTO_MAPEADO_QUEBRADO = "mapeado_quebrado"
VEREDICTO_SEM_PASTA = "sem_pasta"
VEREDICTO_DEPENDE_DO_NOME = "depende_do_nome"
VEREDICTO_COLISAO = "colisao_de_nome"

#: Os dois que o corte do recurso por nome faz perder documentos.
VEREDICTOS_QUE_CUSTAM = (VEREDICTO_DEPENDE_DO_NOME, VEREDICTO_COLISAO)

MARCADOR_DE_PASTA = ".keep"


def conta_ficheiros_uteis(chaves: Iterable[str]) -> int:
    """Quantos objectos são documentos — os marcadores `.keep` não contam.

    O `list_files` salta-os explicitamente; contá-los aqui faria uma
    pasta recém-criada e vazia aparecer no relatório com seis documentos
    a perder.
    """
    return sum(
        1 for chave in chaves
        if chave and not str(chave).endswith(MARCADOR_DE_PASTA)
    )


def sanitizar_como_pasta(nome: Optional[str]) -> str:
    """A grafia sanitizada que o sistema também produziu para um nome.

    Importado tardiamente para este módulo não arrastar o `s3_storage`
    (e com ele o `boto3`) para dentro dos testes unitários.
    """
    from services.s3_storage import sanitize_folder_name

    return sanitize_folder_name(nome or "")


def nomes_de_pasta_candidatos(
    nome: Optional[str], segundo_nome: Optional[str] = None,
) -> list[str]:
    """As grafias EXACTAS que o sistema produziu para este nome, em minúsculas.

    Espelha `s3_storage._nomes_de_pasta_candidatos` de propósito: medir
    com uma regra mais LARGA do que a do código contaria fichas que o
    recurso nunca serviu, e medir com uma mais ESTREITA esconderia custo.
    Há um teste a cruzar as duas listas.
    """
    limpo = (nome or "").strip()
    if not limpo:
        return []
    segundo = (segundo_nome or "").strip()
    if segundo:
        candidatos = [
            f"{limpo} e {segundo}",
            f"{sanitizar_como_pasta(limpo)}_e_{sanitizar_como_pasta(segundo)}",
        ]
    else:
        candidatos = [limpo, sanitizar_como_pasta(limpo)]
    vistos: list[str] = []
    for candidato in candidatos:
        baixo = candidato.lower()
        if baixo and baixo not in vistos:
            vistos.append(baixo)
    return vistos


@dataclass(frozen=True)
class Pasta:
    """Uma pasta de topo do bucket, com a contagem de documentos úteis."""

    nome: str
    ficheiros: int = 0

    @property
    def caminho(self) -> str:
        return f"{RAIZ}{self.nome}"

    @property
    def por_id(self) -> bool:
        return e_id_gerado(self.nome)


@dataclass
class Ficha:
    """Uma ficha a auditar — um processo ou um cliente."""

    tipo: str
    id: str
    nome: str
    s3_folder: Optional[str] = None
    segundo_nome: Optional[str] = None
    etiqueta: str = ""


@dataclass
class Resultado:
    """O veredicto de uma ficha e a pasta que o recurso por nome lhe dava."""

    ficha: Ficha
    veredicto: str
    pasta: Optional[str] = None
    ficheiros: int = 0
    partilhada_com: list[str] = field(default_factory=list)


def _indice_de_pastas(pastas: Iterable[Pasta]) -> dict[str, Pasta]:
    return {pasta.nome.lower(): pasta for pasta in pastas}


def _pasta_pelo_nome(
    ficha: Ficha, indice: dict[str, Pasta],
) -> Optional[Pasta]:
    for candidato in nomes_de_pasta_candidatos(ficha.nome, ficha.segundo_nome):
        pasta = indice.get(candidato)
        if pasta is not None:
            return pasta
    return None


class InventarioIndisponivel(RuntimeError):
    """Não há inventário do bucket — logo não há medição, e não há conclusão.

    Levantada em vez de devolver veredictos porque o veredicto que sairia
    (`sem_pasta` para todos) lê-se como «não custa nada apagar».
    """


def inventario_utilizavel(pastas: Optional[Iterable[Pasta]]) -> bool:
    """True quando o bucket foi lido e tem pastas para comparar.

    `None` é «a leitura falhou» e uma lista vazia é «o bucket não tem
    pastas». As duas impedem a medição, mas por motivos diferentes, e é o
    chamador que explica qual — num bucket com 12.450 pastas, zero é
    sempre uma falha de leitura disfarçada.
    """
    return bool(pastas)


def auditar(
    fichas: Iterable[Ficha], pastas: Optional[Iterable[Pasta]],
) -> list[Resultado]:
    """Classifica cada ficha. A colisão só se vê no conjunto — ver o cabeçalho.

    Raises:
        InventarioIndisponivel: sem pastas para comparar. Ver o cabeçalho.
    """
    pastas = list(pastas or [])
    if not inventario_utilizavel(pastas):
        raise InventarioIndisponivel(
            "Sem inventário de pastas do bucket não há medição: todas as "
            "fichas sem mapeamento cairiam em «sem_pasta» e o relatório "
            "concluiria que o corte não custa nada."
        )
    indice = _indice_de_pastas(pastas)
    nomes_existentes = {pasta.nome.lower() for pasta in pastas}

    preliminares: list[Resultado] = []
    for ficha in fichas:
        gravado = (ficha.s3_folder or "").strip().rstrip("/")
        if gravado and gravado.lower() not in ("undefined", "null", "none"):
            nome_gravado = gravado[len(RAIZ):] if gravado.startswith(RAIZ) else gravado
            existe = nome_gravado.split("/")[0].lower() in nomes_existentes
            preliminares.append(Resultado(
                ficha=ficha,
                veredicto=(
                    VEREDICTO_MAPEADO if existe else VEREDICTO_MAPEADO_QUEBRADO
                ),
                pasta=gravado,
            ))
            continue

        pasta = _pasta_pelo_nome(ficha, indice)
        if pasta is None or pasta.ficheiros <= 0:
            # Sem pasta OU com pasta vazia: o corte não tira documento
            # nenhum. Uma pasta vazia que o nome resolve continua a ser um
            # candidato a religamento, mas não é um custo — e inflacionar
            # o custo é a maneira de o relatório deixar de ser levado a
            # sério.
            preliminares.append(Resultado(
                ficha=ficha,
                veredicto=VEREDICTO_SEM_PASTA,
                pasta=pasta.caminho if pasta else None,
            ))
            continue

        preliminares.append(Resultado(
            ficha=ficha,
            veredicto=VEREDICTO_DEPENDE_DO_NOME,
            pasta=pasta.caminho,
            ficheiros=pasta.ficheiros,
        ))

    # A colisão é uma propriedade do CONJUNTO: só agora se sabe quantas
    # fichas chegam à mesma pasta pelo nome.
    por_pasta: dict[str, list[Resultado]] = {}
    for resultado in preliminares:
        if resultado.veredicto == VEREDICTO_DEPENDE_DO_NOME and resultado.pasta:
            por_pasta.setdefault(resultado.pasta, []).append(resultado)

    for _caminho, grupo in por_pasta.items():
        if len(grupo) < 2:
            continue
        etiquetas = [f"{r.ficha.tipo}:{r.ficha.id}" for r in grupo]
        for resultado in grupo:
            resultado.veredicto = VEREDICTO_COLISAO
            resultado.partilhada_com = [
                etiqueta for etiqueta in etiquetas
                if etiqueta != f"{resultado.ficha.tipo}:{resultado.ficha.id}"
            ]

    return preliminares


def resumir(resultados: Iterable[Resultado]) -> dict:
    """Os números do relatório.

    `ficheiros_em_risco` conta SÓ os veredictos que custam e **soma cada
    pasta uma vez**: na colisão, duas fichas apontam para a mesma pasta e
    somar as duas anunciaria o dobro dos documentos que existem.
    """
    por_veredicto: dict[str, int] = {}
    pastas_em_risco: dict[str, int] = {}
    for resultado in resultados:
        por_veredicto[resultado.veredicto] = (
            por_veredicto.get(resultado.veredicto, 0) + 1
        )
        if resultado.veredicto in VEREDICTOS_QUE_CUSTAM and resultado.pasta:
            pastas_em_risco[resultado.pasta] = resultado.ficheiros

    return {
        "total": sum(por_veredicto.values()),
        "por_veredicto": por_veredicto,
        "fichas_em_risco": sum(
            por_veredicto.get(v, 0) for v in VEREDICTOS_QUE_CUSTAM
        ),
        "pastas_em_risco": len(pastas_em_risco),
        "ficheiros_em_risco": sum(pastas_em_risco.values()),
    }


def para_religar(resultados: Iterable[Resultado]) -> list[dict]:
    """As linhas accionáveis no painel de religamento, pior caso primeiro.

    A ordem é deliberada: a colisão primeiro (duas fichas a partilhar
    documentação é o risco de RGPD que abriu o Lote 6), depois pelo número
    de ficheiros que se perdem. Uma lista por id não diz a ninguém onde
    começar.
    """
    accionaveis = [
        r for r in resultados if r.veredicto in VEREDICTOS_QUE_CUSTAM
    ]
    accionaveis.sort(
        key=lambda r: (
            0 if r.veredicto == VEREDICTO_COLISAO else 1,
            -r.ficheiros,
            r.ficha.id,
        )
    )
    return [
        {
            "tipo": r.ficha.tipo,
            "id": r.ficha.id,
            "nome": r.ficha.nome,
            "etiqueta": r.ficha.etiqueta,
            "veredicto": r.veredicto,
            "s3_folder_sugerido": r.pasta,
            "ficheiros": r.ficheiros,
            "partilhada_com": r.partilhada_com,
        }
        for r in accionaveis
    ]


__all__ = [
    "InventarioIndisponivel",
    "inventario_utilizavel",
    "VEREDICTO_MAPEADO",
    "VEREDICTO_MAPEADO_QUEBRADO",
    "VEREDICTO_SEM_PASTA",
    "VEREDICTO_DEPENDE_DO_NOME",
    "VEREDICTO_COLISAO",
    "VEREDICTOS_QUE_CUSTAM",
    "Ficha",
    "Pasta",
    "Resultado",
    "auditar",
    "MARCADOR_DE_PASTA",
    "conta_ficheiros_uteis",
    "nomes_de_pasta_candidatos",
    "para_religar",
    "resumir",
]
