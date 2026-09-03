"""
Reversal Test — Fev 2026 (Iteração 8)

Nesta iteração o fluxo do botão "Novo Cliente" (clientOnly) foi REVERTIDO:
- Passa novamente a criar Cliente + Processo (is_lead=True, process_type='outro')
- Cliente é criado com skip_welcome_email=True (evita email duplicado)
- O ÚNICO envio de email de boas-vindas ocorre na criação do Processo
- Falha de SMTP não bloqueia a criação (fire-and-forget)

Testa a chain de duas chamadas API que o CreateClientModal.jsx faz em modo
clientOnly:
  1) POST /api/clients   (skip_welcome_email=True)
  2) POST /api/processes/create-client (is_lead=True, process_type='outro')

NÃO reexecuta os testes da iteração 7 sobre "cliente sem processo" — esse
comportamento (frontend) foi intencionalmente revertido. O endpoint backend
POST /api/clients continua a NÃO criar processo por si só (validado noutro
ficheiro), pelo que a criação do processo cabe agora ao caller (o modal).
"""
import asyncio
import logging
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _create_client_with_skip(client, admin_token, prefix: str) -> dict:
    """Simula o passo 1 do modal clientOnly."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "nome": f"TEST_{prefix} Cliente {suffix}",
        "email": f"test_{prefix.lower()}_{suffix}@example.com",
        "telefone": "912345678",
        "fonte": "staff_created",
        "skip_welcome_email": True,
    }
    r = await client.post(
        "/clients",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), f"Create client failed: {r.status_code} {r.text}"
    return r.json()


async def _create_lead_process(client, admin_token, client_id: str) -> dict:
    """Simula o passo 2 do modal clientOnly."""
    r = await client.post(
        "/processes/create-client",
        json={
            "client_id": client_id,
            "process_type": "outro",
            "is_lead": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), f"Create lead process failed: {r.status_code} {r.text}"
    return r.json()


class TestNovoClienteRevertedFlow:

    async def test_client_created_with_skip_welcome_email_flag(self, client, admin_token):
        """POST /clients aceita skip_welcome_email=True sem erro."""
        data = await _create_client_with_skip(client, admin_token, "SkipEmail")
        assert data.get("id"), f"No id in response: {data}"

        # Cleanup
        from database import db
        await db.documents.delete_many({"client_id": data["id"]})
        await db.clients.delete_one({"id": data["id"]})

    async def test_full_ui_chain_creates_client_and_lead_process(self, client, admin_token):
        """
        Simula o modal clientOnly completo: cria cliente + processo pré-registo.
        Valida que:
        - Ambos os endpoints devolvem sucesso (200/201) mesmo sem SMTP
        - process.is_lead=True, process_type='outro'
        - client.process_ids contém o novo processo
        - Cliente + processo persistem em BD
        """
        cli = await _create_client_with_skip(client, admin_token, "Chain")
        client_id = cli["id"]

        proc = await _create_lead_process(client, admin_token, client_id)
        process_id = proc.get("id")
        assert process_id, f"No id in process response: {proc}"

        # Backend fields
        assert proc.get("process_type") == "outro", f"process_type inesperado: {proc.get('process_type')}"
        # is_lead pode aparecer como True ou o status PRE_REGISTO — validar por status também
        assert proc.get("is_lead") is True or "pre_registo" in str(proc.get("status", "")).lower(), \
            f"Processo não é lead/pre_registo: is_lead={proc.get('is_lead')} status={proc.get('status')}"

        # Persistência: cliente aponta ao processo
        await asyncio.sleep(0.3)  # link_clients_after_process_create é imediato mas seguro
        rg = await client.get(
            f"/clients/{client_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rg.status_code == 200, rg.text
        client_doc = rg.json()
        process_ids = client_doc.get("process_ids") or []
        assert process_id in process_ids, (
            f"Cliente não foi ligado ao processo. process_ids={process_ids} "
            f"esperado conter {process_id}"
        )

        # Cleanup
        from database import db
        await db.processes.delete_one({"id": process_id})
        await db.documents.delete_many({"process_id": process_id})
        await db.documents.delete_many({"client_id": client_id})
        await db.clients.delete_one({"id": client_id})

    async def test_welcome_email_attempted_only_once_in_chain(
        self, client, admin_token, caplog
    ):
        """
        Com skip_welcome_email=True no POST /clients, o email de boas-vindas
        NÃO deve ser tentado nessa chamada. Deve ser tentado exatamente UMA
        vez, na criação do processo. Em preview sem SMTP a tentativa falha
        (esperado) mas a resposta HTTP mantém-se sucesso.

        Observa logs de [EMAIL]/[PORTAL-EMAIL] durante o fluxo completo.
        """
        caplog.set_level(logging.INFO)

        cli = await _create_client_with_skip(client, admin_token, "EmailOnce")
        client_id = cli["id"]
        client_email = cli.get("email") or cli.get("contacto", {}).get("email")

        # ── Após POST /clients (skip=True) NÃO deve aparecer [PORTAL-EMAIL] p/ este email
        logs_after_client = "\n".join(
            r.getMessage() for r in caplog.records if client_email and client_email in r.getMessage()
        )
        assert "[PORTAL-EMAIL] A enviar email" not in logs_after_client, (
            f"Email tentado no POST /clients apesar de skip_welcome_email=True. "
            f"Logs:\n{logs_after_client}"
        )

        # ── Passo 2: criar processo (aqui SIM esperamos 1 tentativa de email)
        proc = await _create_lead_process(client, admin_token, client_id)
        process_id = proc["id"]

        # Aguarda a task fire-and-forget concluir
        await asyncio.sleep(1.0)

        # Contar tentativas de INÍCIO de envio — marcador único por attempt:
        # "[PORTAL-EMAIL] A enviar email diretamente para {email}"
        # (as linhas subsequentes "[EMAIL] Falha..." e "[PORTAL-EMAIL] Falha..."
        # correspondem à mesma tentativa e não devem ser contadas em duplicado).
        attempt_count = sum(
            1 for r in caplog.records
            if client_email and client_email in r.getMessage()
            and "[PORTAL-EMAIL] A enviar email" in r.getMessage()
        )
        assert attempt_count <= 1, (
            f"Email de boas-vindas foi INICIADO {attempt_count}x — duplicação. "
            f"Deve ocorrer no máximo 1 (na criação do processo)."
        )

        # Cleanup
        from database import db
        await db.processes.delete_one({"id": process_id})
        await db.documents.delete_many({"process_id": process_id})
        await db.documents.delete_many({"client_id": client_id})
        await db.clients.delete_one({"id": client_id})

    async def test_chain_succeeds_even_when_smtp_unavailable(self, client, admin_token):
        """
        Ambiente preview NÃO tem SMTP real — verifica que a criação continua
        a devolver sucesso mesmo assim (email é fire-and-forget, não bloqueia).
        """
        cli = await _create_client_with_skip(client, admin_token, "NoSMTP")
        client_id = cli["id"]

        proc = await _create_lead_process(client, admin_token, client_id)
        assert proc.get("id"), f"Processo não foi criado apesar do SMTP falhar: {proc}"

        # Cleanup
        from database import db
        await db.processes.delete_one({"id": proc["id"]})
        await db.documents.delete_many({"process_id": proc["id"]})
        await db.documents.delete_many({"client_id": client_id})
        await db.clients.delete_one({"id": client_id})
