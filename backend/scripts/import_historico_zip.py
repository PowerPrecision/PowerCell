#!/usr/bin/env python3
"""Importa um ZIP de documentos HISTÓRICOS (recibos, extratos, declarações) para a pesquisa do Index (Out 2026).

    # ver o que o ZIP tem (omissão — NÃO lê o conteúdo, NÃO chama a IA, NÃO escreve)
    python -m scripts.import_historico_zip /dados/arquivo_onedrive.zip --rede grupo_power_precision

    # importar (um ficheiro de cada vez; pode ser interrompido e repetido)
    python -m scripts.import_historico_zip /dados/arquivo_onedrive.zip --rede grupo_power_precision --aplicar

    # um lote por noite, com tecto de custo (documentos enviados ao modelo)
    python -m scripts.import_historico_zip /dados/arquivo_onedrive.zip --rede grupo_power_precision --aplicar --limite-ia 500

    # ligar os ficheiros a uma importação antiga (feita antes de 28/10/2026, só com os dados): o MESMO comando.
    # O que já está importado não volta à IA; só se guarda o ficheiro no S3 e se liga à linha.
    python -m scripts.import_historico_zip /dados/arquivo_onedrive.zip --rede grupo_power_precision --aplicar

    # o ZIP que está no S3 (ex.: na Shell do Render): descarrega para um temporário, importa e apaga o temporário
    python -m scripts.import_historico_zip s3://bucket/temp/import/import.zip --rede grupo_power_precision --aplicar

    # desfazer uma importação (o `import_id` vem na linha PROGRESSO; apaga também os ficheiros no S3)
    python -m scripts.import_historico_zip --desfazer 1a2b3c4d5e6f --aplicar

O QUE FAZ
=========
Abre o ZIP SEM o descomprimir (lê o índice e depois UM ficheiro de cada vez, em blocos de 1 MB, com tecto de 20 MB
por ficheiro): serve ZIPs de 85 MB e de mais de 2 GB com a mesma memória. Para cada PDF/imagem: o nome/pasta
sugerem o tipo (de graça) ou a IA classifica; os recibos, extratos e declarações de efetividade são extraídos
com a IA do Index e gravados em `process_index_documents` (com um `process_id` artificial
`historical_import_<hash do ZIP>`); as entidades patronais com NIF válido vão para o directório `employers`.
Documentos de identificação são reconhecidos e IGNORADOS. O ficheiro de cada linha importada guarda-se no S3 em
`Arquivo Histórico Index/<rede>/<import_id>/<id>.<ext>` (só ids: nenhum nome de ficheiro, caminho ou cliente chega
ao modelo, à chave S3, à base de dados ou ao ecrã), para o Index o ver e descarregar na pesquisa avançada.

OPÇÕES
======
  zip                  caminho do ZIP, ou `s3://bucket/chave.zip` (obrigatório, excepto com --desfazer)
  --rede REDE          OBRIGATÓRIA para importar: o `network_id` que pode ver estes documentos (tem de existir
                       numa empresa; uma gralha seria rejeitada). O Master vê todas as redes.
  --etiqueta TEXTO     o que o ecrã mostra («Arquivo histórico — TEXTO»); omissão: o nome do ZIP
  --aplicar            lê, chama a IA e grava (omissão: só descreve)
  --limite-ia N        pára depois de N chamadas ao modelo (tecto de custo; repetir o comando retoma)
  --classificar-sempre ignora a pista do nome/pasta e deixa a IA classificar tudo (mais caro, mais fiável)
  --pausa SEGUNDOS     pausa entre ficheiros pagos (omissão 0,5; env IMPORT_HISTORICO_PAUSE_SECONDS)
  --permitir-simulado  (dev/testes) aceita o motor simulado — escreve dados SIMULADOS
  --sem-ficheiros      só os dados, como antes de 28/10/2026 (não guarda nem exige o S3)
  --desfazer ID        apaga as linhas da importação ID e os seus ficheiros no S3 (as entidades patronais ficam)

IDEMPOTENTE: o id de cada linha deriva do conteúdo do ficheiro + a rede. Repetir o comando, ou retomar um que
caiu a meio, não duplica nem volta a pagar o que já foi importado ou classificado como «não serve».

CÓDIGOS DE SAÍDA:  0 ok · 2 ZIP ilegível/inexistente · 3 motor de IA simulado (recusado) · 4 rede em falta ou
desconhecida · 5 S3 não configurado (use --sem-ficheiros para importar só os dados) · 130 interrompido (o progresso fica e retoma-se)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import index_historical_import as imp  # noqa: E402


def _argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("zip", nargs="?", help="caminho do ZIP")
    p.add_argument("--rede", default=None)
    p.add_argument("--etiqueta", default=None)
    p.add_argument("--aplicar", action="store_true")
    p.add_argument("--limite-ia", type=int, default=None)
    p.add_argument("--classificar-sempre", action="store_true")
    p.add_argument("--pausa", type=float, default=None)
    p.add_argument("--permitir-simulado", action="store_true")
    p.add_argument("--sem-ficheiros", action="store_true")
    p.add_argument("--desfazer", metavar="IMPORT_ID", default=None)
    return p.parse_args(argv)


def _pausa(args) -> float:
    if args.pausa is not None:
        return max(0.0, min(args.pausa, 60.0))
    try:
        valor = float(os.environ.get("IMPORT_HISTORICO_PAUSE_SECONDS", imp.PAUSA_POR_OMISSAO_SEGUNDOS))
    except ValueError:
        return imp.PAUSA_POR_OMISSAO_SEGUNDOS
    return imp.PAUSA_POR_OMISSAO_SEGUNDOS if valor < 0 else min(valor, 60.0)


async def _s3_pronto() -> bool:
    """O S3 configurado (env ou a configuração da BD, como no arranque do servidor)?"""
    from services.s3_storage import s3_service, sync_s3_from_db_config

    await sync_s3_from_db_config()
    return s3_service.is_configured()


def separar_uri_s3(texto: str) -> tuple[str, str] | None:
    """`s3://bucket/chave` → `(bucket, chave)`; `None` se não for um URI S3 completo. PURA."""
    if not isinstance(texto, str) or not texto.startswith("s3://"):
        return None
    bucket, _, chave = texto[len("s3://"):].partition("/")
    return (bucket, chave) if bucket and chave and not chave.endswith("/") else None


async def _descarregar_do_s3(bucket: str, chave: str) -> str:
    """Copia o ZIP do S3 para um ficheiro temporário (em blocos, nunca na memória). Devolve o caminho."""
    from services.s3_storage import s3_service

    descritor, caminho = tempfile.mkstemp(prefix="import_historico_", suffix=".zip")
    os.close(descritor)
    await asyncio.to_thread(s3_service.s3_client.download_file, bucket, chave, caminho)
    return caminho


async def principal(argv=None) -> int:
    """Com um `s3://…` no lugar do caminho, descarrega o ZIP para um temporário, importa e apaga o temporário."""
    args = _argumentos(argv)
    uri = separar_uri_s3(args.zip or "")
    if args.zip and args.zip.startswith("s3://") and uri is None:
        print("URI S3 inválido (use s3://bucket/caminho/ficheiro.zip).")
        return 2
    if uri is None:
        return await _principal(args)
    if not await _s3_pronto():
        print("S3 não configurado: não é possível ler o ZIP do S3.")
        return 5
    print("[import-historico] A descarregar o ZIP do S3 para um ficheiro temporário…")
    try:
        temporario = await _descarregar_do_s3(*uri)
    except Exception as exc:  # noqa: BLE001
        print(f"ZIP não descarregado do S3 ({type(exc).__name__}): confirme o URI e as permissões.")
        return 2
    try:
        args.zip = temporario
        return await _principal(args)
    finally:
        try:
            os.remove(temporario)
        except OSError:
            pass


async def _principal(args) -> int:

    if args.desfazer:
        if not args.aplicar:
            print(f"[import-historico] --desfazer {args.desfazer}: nada foi apagado. Repetir com --aplicar.")
            return 0
        apagar = imp.apagar_do_s3 if await _s3_pronto() else None
        apagadas = await imp.desfazer_importacao(args.desfazer, apagar_ficheiro=apagar)
        print(f"[import-historico] importação {args.desfazer} desfeita: {apagadas} linhas apagadas (entidades mantidas).")
        return 0

    if not args.zip:
        print("Falta o caminho do ZIP.")
        return 2
    if not Path(args.zip).is_file():
        print("ZIP não encontrado.")
        return 2

    try:
        previa = await asyncio.to_thread(imp.analise_previa, args.zip)
    except imp.ZipInvalido as exc:
        print(f"ZIP ilegível ({exc}).")
        return 2
    mb = previa["bytes_candidatos"] / (1024 * 1024)
    pistas = previa["por_pista"]
    print(
        f"[import-historico] {previa['membros']} entradas · {previa['candidatos']} ficheiros analisáveis ({mb:.1f} MB) · "
        f"pelo nome: recibos={pistas['recibo']} extratos={pistas['extrato']} declaracoes={pistas['declaracao']} "
        f"identificacao={pistas['identificacao']} · sem pista (a IA classifica)={pistas['sem_pista']} · "
        f"demasiado grandes={previa['demasiado_grandes']} · excluídos={sum(previa['excluidos'].values())}"
    )

    if not args.rede:
        print("Falta --rede: sem ela ninguém poderia ver estes documentos (e com a rede errada, só o Master).")
        return 4
    try:
        existe = await imp.rede_existe(args.rede)
        conhecidas = [] if existe else await imp.redes_conhecidas()
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: {type(exc).__name__}")
        return 2
    if not existe:
        print(f"Rede desconhecida. Redes declaradas pelas empresas: {', '.join(conhecidas) or '(nenhuma)'}")
        return 4

    if not args.aplicar:
        print(f"→ Nada foi lido nem gravado. Repetir com --aplicar (rede={args.rede}). Máximo de chamadas à IA: "
              f"{previa['candidatos']} a {2 * previa['candidatos']}.")
        return 0

    guardar = None
    if not args.sem_ficheiros:
        if not await _s3_pronto():
            print("S3 não configurado: os ficheiros não se podiam guardar. Configure o armazenamento ou use --sem-ficheiros.")
            return 5
        guardar = imp.guardar_no_s3

    try:
        resumo = await imp.importar_zip(
            args.zip, rede=args.rede, etiqueta=args.etiqueta, limite_ia=args.limite_ia,
            classificar_sempre=args.classificar_sempre, pausa=_pausa(args), permitir_simulado=args.permitir_simulado,
            guardar_ficheiro=guardar,
        )
    except imp.IASimulada as exc:
        print(f"RECUSADO: {exc}")
        return 3
    except imp.RedeDesconhecida:
        print("Rede desconhecida.")
        return 4
    except imp.ZipInvalido as exc:
        print(f"ZIP ilegível ({exc}).")
        return 2
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("INTERROMPIDO: o que já foi importado fica; repetir o mesmo comando retoma sem repetir custos.")
        return 130
    if resumo.parou_por == "limite_ia":
        print("→ Parou no limite de chamadas à IA. Repetir o mesmo comando para continuar.")
    print(f"→ Para desfazer: python -m scripts.import_historico_zip --desfazer {resumo.import_id} --aplicar")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(principal()))
    except KeyboardInterrupt:
        print("INTERROMPIDO.")
        sys.exit(130)
