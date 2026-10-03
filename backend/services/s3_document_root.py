"""A raiz documental deriva de IDs, nunca de um nome (Lote 6, ponto 1).

O QUE CORREU MAL
================
Os documentos de uma cliente nova ("Carolina Agostinho da Silva") foram
servidos na pasta de uma cliente existente ("Carolina Silva"). A causa
não é o `fuzzy match` a "falhar" — é identidade derivada de um nome, e a
aritmética do `_find_client_folder_combined` dava-lhe razão:

    palavras em comum / palavras totais  = 2/3  = 0.667   ("da" é descartada)
  + 0.2 porque o primeiro nome aparece na pasta
  ------------------------------------------------------
  = 0.867  >=  0.7  →  mesma pasta

A assinatura da colisão é **mesmo primeiro nome + um conjunto de nomes
contido no outro**: mãe e filha, dois irmãos, e sobretudo a MESMA pessoa
inserida uma vez com nome curto e outra com nome completo. Não é o caso
raro, é o frequente.

E o sistema não tinha rede: `_get_client_base_path` — a única função que
acrescentava `_2`/`_3` a um nome repetido — **não tinha um único
chamador**. A que corria (`_get_client_base_path_for_upload`) diz na
própria docstring que não usa incrementador. Dois clientes com o mesmo
nome nunca tiveram pastas separadas, e o `s3_folder_relink` documentava o
`_2` como "precisamente como o sistema desambigua homónimos" — um
mecanismo documentado que não existia.

A REGRA NOVA
============
    Documentação Clientes/{client_id}/                      ← documentos do CLIENTE
    Documentação Clientes/{client_id}/processos/{process_id}/ ← documentos do PROCESSO

Um id é único por construção, não muda com um casamento nem com a
correcção de uma gralha, e não se parece com o id de ninguém.

TRÊS DECISÕES QUE NÃO SE PODEM PERDER
=====================================
1. **A raiz canónica é a MESMA** (`Documentação Clientes/`). É a que o
   `assert_path_within_document_root` exige e a que o Explorador usa;
   uma raiz nova obrigaria a alargar a guarda de segurança para a
   acomodar, e alargar uma parede para caber a correcção é como o
   Incidente P0 do Portal começou.

2. **Nada se migra e nada se move.** Os 12.450 `s3_folder` já gravados
   continuam a ser lidos tal e qual. Mover objectos foi exactamente o que
   produziu as 205 ligações partidas que o Épico 10 mediu. A regra nova
   vale para mapeamentos NOVOS e para o religamento manual.

3. **A pasta do processo fica DENTRO da do cliente, e por isso a leitura
   de um processo é uma UNIÃO.** Listar só a subpasta esconderia tudo o
   que o cliente enviou antes de o processo existir (o onboarding do
   Portal inteiro) — e um documento que desaparece não produz erro
   nenhum, que é a forma de defeito desta casa. A união é explícita, tem
   teste, e exclui a subárvore `processos/` para o processo do lado nunca
   entrar.

A FRONTEIRA DE SEGMENTO
=======================
`dentro_da_pasta` compara por SEGMENTO. Um `startswith` cru sobre
`Documentação Clientes/Carolina Silva` autoriza
`Documentação Clientes/Carolina Silva Agostinho/...` — o buraco que as
guardas de posse tinham e que não precisava do `fuzzy match` nenhum para
se abrir. É a regra que o `s3_folder_relink.reescrever_prefixo` já
aplicava ("`Joao_Silva_2` começa pelo mesmo texto e é OUTRO cliente").
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: A raiz canónica de toda a documentação de clientes. A MESMA constante
#: que `document_process_resolve.DOCUMENT_S3_ROOT_PREFIX` e
#: `s3_explorer_paths.RAIZ_DO_EXPLORADOR` — há um teste a cruzá-las.
RAIZ = "Documentação Clientes/"

#: O segmento que separa os documentos do cliente dos de cada processo.
#: Não colide com nenhuma categoria (`DEFAULT_CATEGORIES`) — afirmado em
#: teste, porque a categoria é derivada do primeiro segmento do caminho
#: relativo e uma colisão faria um processo aparecer como categoria.
SEGMENTO_DOS_PROCESSOS = "processos"

#: Um id só serve como segmento de caminho se não puder sair dele.
#: Aceita o `str(uuid.uuid4())` que o sistema gera e os ids legados
#: alfanuméricos; recusa barras, espaços, `..` e um ponto inicial.
#: Fail-closed: um id que não passe NÃO produz pasta (devolve `None`) em
#: vez de produzir uma pasta num sítio imprevisto.
REGEX_DE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

#: "Isto é um id que NÓS geramos" — a forma do `str(uuid.uuid4())`.
#:
#: É uma pergunta DIFERENTE de `id_valido`, e confundi-las decide ao contrário:
#: `id_valido` pergunta "serve como segmento de caminho?", e um nome sanitizado
#: (`Rui_Pereira`) serve. Quem precisa de distinguir uma pasta por id de uma
#: pasta por nome — os reparadores de `client_name`, que extraem o nome DA
#: PASTA — precisa desta. Com a outra, gravavam `Rui Pereira` como se fosse um
#: id (não reparavam nada) ou um uuid como se fosse um nome, que depois sai em
#: emails, PDFs e documentos RGPD.
REGEX_DE_ID_GERADO = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class Leitura:
    """Um prefixo a varrer, e se a subárvore dos processos entra.

    `excluir_processos` só é verdadeiro na raiz do CLIENTE quando se está
    a abrir UM processo: aí os documentos soltos do cliente contam e os
    do processo do lado não.
    """

    prefixo: str
    excluir_processos: bool = False


def e_pasta_gravada_corrompida(valor: Any) -> bool:
    """O campo `s3_folder` tem valor mas NÃO é texto — logo não é uma pasta.

    Produção tem fichas com `s3_folder` gravado como LISTA, e foi a
    medição da D-19 a dar com elas:

        gravado = (ficha.s3_folder or "").strip()
        AttributeError: 'list' object has no attribute 'strip'

    **Uma lista é truthy.** O `or ""` não a substitui e o `if s3_folder:`
    deixa-a passar — é a regra do `Array.isArray` do frontend escrita em
    Python: um valor do tipo errado não desaparece com um `or`, só muda o
    sítio onde o erro acontece (aqui, a linha seguinte).

    `None` e `""` respondem **False**: são a ausência NORMAL de
    mapeamento, que tem caminho próprio e documentado (o recurso por
    nome). Confundir as duas fazia a ausência comum parecer corrupção.
    """
    return valor is not None and not isinstance(valor, str)


def pasta_gravada(valor: Any, *, contexto: str = "") -> Optional[str]:
    """O `s3_folder` gravado como texto utilizável, ou `None` — com registo.

    O ponto único por onde todos os leitores de `s3_folder` passam antes
    de lhe aplicarem um método de string. Devolver `None` faz o chamador
    cair no caminho de «sem mapeamento», que é o degradado CERTO: para
    uma leitura, procura-se pelo nome; para uma escrita, deriva-se do ID
    (nunca de um nome — Lote 6, ponto 1). Nenhum dos dois inventa uma
    pasta a partir de um valor que não se entende.

    **Nunca em silêncio.** Um `s3_folder` corrompido é lixo na base de
    dados que alguém tem de corrigir, e um degradado calado é a forma de
    defeito desta casa: os documentos deixavam de aparecer e ninguém
    sabia porquê. Daí o `warning` com o valor cru e o contexto.
    """
    if e_pasta_gravada_corrompida(valor):
        logger.warning(
            "[S3-PASTA] `s3_folder` corrompido (%s, não é texto): %r%s. "
            "Tratado como SEM mapeamento; corrigir o registo.",
            type(valor).__name__,
            valor,
            f" — {contexto}" if contexto else "",
        )
        return None
    if not isinstance(valor, str):
        return None
    limpo = valor.strip()
    return limpo or None


def id_valido(valor: Any) -> bool:
    """O valor serve como segmento de caminho?"""
    if not isinstance(valor, str):
        return False
    return bool(REGEX_DE_ID.match(valor.strip()))


def e_id_gerado(valor: Any) -> bool:
    """O valor é um id gerado pelo sistema (uuid4), e não um nome?

    Um id legado que não seja uuid responde `False` — e aí quem pergunta trata
    a pasta como pasta por nome, que é o comportamento anterior. Falhar para o
    lado antigo é seguro; o contrário gravava um uuid onde vai um nome.
    """
    if not isinstance(valor, str):
        return False
    return bool(REGEX_DE_ID_GERADO.match(valor.strip()))


def _id_limpo(valor: Any) -> Optional[str]:
    return valor.strip() if id_valido(valor) else None


def pasta_do_cliente(client_id: Any) -> Optional[str]:
    """`Documentação Clientes/{client_id}` — ou `None` se o id não serve."""
    ident = _id_limpo(client_id)
    if ident is None:
        return None
    return f"{RAIZ}{ident}"


def pasta_do_processo(
    process_id: Any, client_id: Any = None
) -> Optional[str]:
    """A pasta de um processo, sob a do cliente quando ele é conhecido.

    Sem `client_id` utilizável, a identidade passa a ser o PRÓPRIO
    processo. Degradar para o id do processo é seguro (continua único);
    degradar para o nome era o defeito.
    """
    pid = _id_limpo(process_id)
    if pid is None:
        return None
    base = pasta_do_cliente(client_id)
    if base is None:
        return f"{RAIZ}{pid}"
    return f"{base}/{SEGMENTO_DOS_PROCESSOS}/{pid}"


def normalizar(caminho: Any) -> str:
    """Caminho sem barra final nem barra inicial (comparável)."""
    if not isinstance(caminho, str):
        return ""
    return caminho.strip().lstrip("/").rstrip("/")


def dentro_da_pasta(caminho: Any, pasta: Any) -> bool:
    """`caminho` é a própria `pasta` ou está dentro dela, por SEGMENTO.

    Uma `pasta` vazia não autoriza nada: o degradado antigo com nome
    vazio produzia o prefixo `Documentação Clientes/` e aceitava a árvore
    inteira — no CRM um incómodo, no Portal a fuga.
    """
    base = normalizar(pasta)
    alvo = normalizar(caminho)
    if not base or not alvo:
        return False
    return alvo == base or alvo.startswith(f"{base}/")


def e_pasta_de_processo(pasta: Any) -> bool:
    """A pasta é `.../{client_id}/processos/{process_id}`?"""
    partes = normalizar(pasta)
    if not partes.startswith(RAIZ):
        return False
    segmentos = partes[len(RAIZ):].split("/")
    return len(segmentos) == 3 and segmentos[1] == SEGMENTO_DOS_PROCESSOS


def raiz_do_cliente_de(pasta: Any) -> Optional[str]:
    """A pasta do cliente a que esta pasta de processo pertence."""
    if not e_pasta_de_processo(pasta):
        return None
    partes = normalizar(pasta)
    return partes.rsplit(f"/{SEGMENTO_DOS_PROCESSOS}/", 1)[0]


def leituras_do_mapeamento(s3_folder: Any) -> list[Leitura]:
    """Os prefixos a varrer para mostrar os documentos de um mapeamento.

    - pasta legada (por nome) ou pasta de CLIENTE → ela própria, inteira;
    - pasta de PROCESSO → ela própria **mais** a raiz do cliente sem a
      subárvore dos processos.
    """
    base = normalizar(s3_folder)
    if not base:
        return []
    raiz_cliente = raiz_do_cliente_de(base)
    if raiz_cliente is None:
        return [Leitura(prefixo=base, excluir_processos=False)]
    return [
        Leitura(prefixo=base, excluir_processos=False),
        Leitura(prefixo=raiz_cliente, excluir_processos=True),
    ]


def chave_pertence_a_leitura(chave: Any, leitura: Leitura) -> bool:
    """A chave S3 entra nesta leitura?"""
    if not dentro_da_pasta(chave, leitura.prefixo):
        return False
    if not leitura.excluir_processos:
        return True
    relativo = normalizar(chave)[len(normalizar(leitura.prefixo)):].lstrip("/")
    return not relativo.startswith(f"{SEGMENTO_DOS_PROCESSOS}/")


def pasta_do_processo_sob_mapeamento_do_cliente(
    process_id: Any, client_id: Any, pasta_do_cliente_gravada: Any = None
) -> Optional[str]:
    """A pasta de um processo NOVO, respeitando o mapeamento legado do cliente.

    Há fluxos em que o processo nasce a HERDAR o `s3_folder` do cliente (o
    `onboarding_mandatory_config`, quando a checklist fica completa). Herdá-lo
    cegamente deixaria o processo a apontar para a raiz do cliente, e aí a
    leitura dele traria também os documentos dos OUTROS processos do mesmo
    cliente (`leituras_do_mapeamento` de uma raiz de cliente não exclui a
    subárvore `processos/`, de propósito: na ficha do cliente mostra-se tudo).

    Mas trocar o mapeamento por um caminho novo é pior ainda quando o cliente
    tem uma pasta LEGADA (por nome) ou escolhida à mão: os documentos estão lá,
    e o processo passaria a olhar para uma pasta vazia. Daí a regra:

      * o cliente tem uma pasta que NÃO é a sua raiz canónica → herda-se tal e
        qual (é legado ou uma decisão humana, e nenhuma das duas se adivinha);
      * caso contrário → o processo recebe a sua subpasta.
    """
    gravada = normalizar(pasta_do_cliente_gravada)
    canonica = pasta_do_cliente(client_id)
    if gravada and gravada != canonica:
        return gravada
    return pasta_do_processo(process_id, client_id=client_id) or gravada or None
