#!/usr/bin/env python3
"""Atlas — de que IP sai este serviço, e o Atlas deixa-o entrar? (só leitura)

Para correr DENTRO do Render (Shell do serviço web e do worker), um de cada vez:

    cd backend && python scripts/diagnosticar_saida_para_atlas.py

O QUE FAZ
  1. Pergunta a serviços públicos de eco de que IP sai o pedido, algumas vezes.
     O Render partilha um conjunto de IPs de saída por região — o IP que aqui
     aparece tem de estar na lista do painel (serviço → *Connect* → *Outbound*).
     A lista do painel é a autoridade (é a lista completa); isto é só a prova de
     que o serviço sai mesmo por um deles.
  2. Faz `ping` ao MongoDB com `MONGO_URL` e diz se o Atlas aceitou a ligação.
     Um `ServerSelectionTimeoutError` com o cluster activo é, quase sempre, a
     *IP Access List* do Atlas: o Atlas descarta os pacotes em silêncio.

O QUE NÃO FAZ
  * Não escreve nada em lado nenhum.
  * Não imprime o `MONGO_URL` (leva credenciais) — só o host, sem utilizador.

CÓDIGOS DE SAÍDA: 0 saiu e o Atlas respondeu; 1 o Atlas não respondeu;
2 não foi possível determinar o IP de saída; 3 `MONGO_URL` não definido.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request
from collections import Counter

#: Serviços de eco. Mais do que um: se um estiver em baixo não se conclui nada.
ECOS = ("https://api.ipify.org", "https://ifconfig.me/ip", "https://checkip.amazonaws.com")
AMOSTRAS_POR_ECO = 3
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def ips_de_saida() -> Counter:
    vistos: Counter = Counter()
    for url in ECOS:
        for _ in range(AMOSTRAS_POR_ECO):
            try:
                with urllib.request.urlopen(url, timeout=8) as resposta:  # noqa: S310 — URLs fixos acima
                    texto = resposta.read().decode().strip()
            except Exception:  # noqa: BLE001 — um eco em baixo não é o diagnóstico
                continue
            if _IPV4.match(texto):
                vistos[texto] += 1
    return vistos


def host_do_url(url: str) -> str:
    """O(s) host(s) do URL, sem utilizador nem palavra-passe."""
    sem_esquema = url.split("://", 1)[-1]
    sem_credenciais = sem_esquema.rsplit("@", 1)[-1]
    return sem_credenciais.split("/", 1)[0].split("?", 1)[0]


def main() -> int:
    url = os.environ.get("MONGO_URL", "")
    print("=" * 72)
    print("ATLAS — IP DE SAÍDA E LIGAÇÃO (só leitura)")
    print("=" * 72)

    vistos = ips_de_saida()
    if not vistos:
        print("Não foi possível determinar o IP de saída (os serviços de eco não responderam).")
        return 2
    print("IP(s) de saída observados:")
    for ip, n in vistos.most_common():
        print(f"  {ip}   ({n} resposta(s))")
    print("  → confirmar que estão na lista do painel do Render (Connect → Outbound)\n"
          "    e que o Atlas (Network Access) tem ESSA lista — a do painel inteira, não só estes.")

    if not url:
        print("\nMONGO_URL não está definido neste ambiente.")
        return 3
    print(f"\nMongoDB: {host_do_url(url)}")
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    try:
        cliente = MongoClient(url, serverSelectionTimeoutMS=8000)
        cliente.admin.command("ping")
    except PyMongoError as exc:
        print(f"  ping: FALHOU ({type(exc).__name__})")
        print("  Se o cluster está activo, é quase de certeza a IP Access List do Atlas:")
        print("  Atlas → Network Access → acrescentar os IPs de saída acima (web E worker).")
        return 1
    print("  ping: OK — o Atlas aceita a ligação a partir deste serviço.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
