# Credenciais de Teste — PowerCell CRM (ambiente dev/preview)

> Nota: ambiente foi reconstruído nesta sessão (2026-08-31) por ausência de
> `.env`. Utilizadores e dados de exemplo foram semeados via
> `backend/seed.py` + `backend/scripts/seed_realistic_data.py`.

## Login (todas as contas usam a mesma password)
Password (todas as contas): `PowerCell_Dev_2026!`

| Email | Role |
|---|---|
| admin@sistema.pt | admin |
| geral@powerealestate.pt | admin (conta de teste indicada pelo utilizador) |
| pedroborges@powerealestate.pt | ceo |
| tiagoborges@powerealestate.pt | consultor |
| flaviosilva@powerealestate.pt | consultor |
| silvamiranda@precisioncredito.pt | intermediario |
| fernandoandrade@precisioncredito.pt | intermediario |
| carinaamuedo@powerealestate.pt | diretor |
| marisarodrigues@powerealestate.pt | administrativo |

## Dados de exemplo
- 30 clientes e 20 processos gerados via `scripts/seed_realistic_data.py` (dados fictícios, Faker pt_PT).
- Para repetir/limpar: `python scripts/seed_realistic_data.py --clear`

## MongoDB local
- `MONGO_URL=mongodb://localhost:27017`
- `DB_NAME=powercell_dev`

## Scripts de manutenção CLI (backend/scripts/)
- `cleanup_prod_test_data.py` e `delete_process_by_id.py` correm em dry-run por omissão.
- Com `--execute`, pedem password via `getpass` (terminal). Compara com env var
  `CLEANUP_SCRIPT_PASSWORD` (não definida neste ambiente) → usa o fallback
  `POWERCELL_CLEANUP_2026`. Não criam ficheiros de log.

