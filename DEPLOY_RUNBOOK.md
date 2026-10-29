# Runbook de deploy — Lotes 1 a 7.3 (Out 2026)

Passos para pôr em produção o que os Lotes 1–7.3 deixaram **pronto no código mas por
executar na base de dados e no ambiente**. Tudo o que está aqui foi lido dos próprios
scripts; o que não está provado vem dito.

> **Estado (16 Out 2026): executado.** O dono do produto reportou que todas as partes C foram corridas em produção (consola do Render). Este documento fica como referência e para re-verificação (cada `dry-run` deve dizer «0 a fazer»); a execução não foi observada pelo autor.

## Regras gerais

* Os comandos correm a partir de `backend/`, com `MONGO_URL` e `DB_NAME` de **produção** no ambiente.
* Quase todos os scripts **só mostram** o plano (`dry-run`) por omissão e só escrevem com `--aplicar`.
  Excepções: `backfill_network_id` (escreve por fases; tem `--dry-run`) e `promote_to_master` (também
  só mostra sem `--aplicar`).
* São idempotentes: se o `dry-run` disser «nada a fazer», o passo já foi aplicado.
* Corre **sempre o `dry-run` primeiro** e lê-o antes de aplicar.
* **Antes da Parte C faz um snapshot do Atlas.** `limpar_copias_orfas_system_config` não leva backup de propósito.
* Nenhum destes scripts chama `require_non_production_db`: correm contra produção de propósito. Confirma o `DB_NAME`.

## Parte A — Deploy do código

1. Faz o deploy do branch `dev` no serviço web **e** no worker (`powercell-worker`).
   Os índices novos (`db_indexes.py`) criam-se sozinhos no arranque.
2. `GET /health` tem de responder.
3. Nos logs de arranque, procura o erro sobre `TENANT_DEFAULT_NETWORK_ID` em falta (ver B).

## Parte B — Variáveis de ambiente

| Variável | Serviço | Valor | Se faltar |
|---|---|---|---|
| `TENANT_DEFAULT_NETWORK_ID` | web **e** worker | `network_id` do grupo principal (exemplo do `.env.example`: `grupo_power_precision` — confirma o real) | **Não está no `render.yaml`.** A pilha antiga por carimbar fica sem dono (log de erro) e os backfills recusam-se. |
| `FRONTEND_URL` | web **e** worker | URL público do frontend | Emails de tarefas de fundo (retry, boas-vindas) saem **sem o link/botão**. |
| `JWT_PARTNER_SECRET` | web | ≥ 32 caracteres, diferente de `JWT_SECRET` | Portal do Parceiro responde 503. |
| `TRUSTED_PROXY_HOPS` | web | `1` (já definido); `2` com Cloudflare à frente | Com o número errado o limite por IP junta clientes. |
| `SENTRY_AUTH_TOKEN` | build do frontend | token do Sentry | O build sai sem mapas (de propósito) e o Sentry mostra stacks minificados. |
| `PORTAL_JWT_SECRET` | web | opcional, ≥ 32 caracteres | Sem ela nada muda. Se a definires, põe `PORTAL_JWT_ACCEPT_LEGACY=false` cerca de 90 dias depois. |

Opcionais de emergência (interruptores): `IA_DA_ENTRADA_ENABLED=false` corta a IA automática dos
uploads; `IMAP_APPEND_ENABLED=false` desliga a cópia para «Enviados» do servidor.

## Parte C — Scripts, por esta ordem

### C1. Criar o Master (o mais importante)

Nenhuma conta existente é Master. Sem uma, ninguém opera a infraestrutura.

```bash
python scripts/promote_to_master.py --emails dono@empresa.pt            # mostra o plano
python scripts/promote_to_master.py --emails dono@empresa.pt --aplicar
```

Emails sempre explícitos. Um plano com qualquer recusa não escreve nada. Se a conta não for
admin/ceo é preciso `--qualquer-papel`. Depois: faz login com essa conta e confirma o perfil Master.

### C2. Rede nas empresas (e, opcionalmente, nos documentos)

```bash
python -m scripts.backfill_network_id --dry-run
python -m scripts.backfill_network_id --empresas       # obrigatório e barato
python -m scripts.backfill_network_id --documentos     # opcional e pesado
```

Sem `--empresas`, cada empresa antiga passa a ser uma ilha e a Power deixa de ver a Precision.
`--documentos` é uma optimização: enquanto não correr, a rede de omissão cobre o que falta.

### C3. Workflow e formulários por rede

Faz isto **logo a seguir ao deploy**: o primeiro script troca o índice único por `name` pelo
`(network_id, name)`.

```bash
python -m scripts.migrar_workflow_por_rede                          # dry-run
python -m scripts.migrar_workflow_por_rede --aplicar --limpar-is-hub
python -m scripts.migrar_formularios_por_rede                       # dry-run
python -m scripts.migrar_formularios_por_rede --aplicar
```

Nunca alteram uma fase ou um formulário que a rede já tenha.

### C4. Emails e caixas partilhadas

```bash
python scripts/backfill_email_network_id.py                         # dry-run
python scripts/backfill_email_network_id.py --aplicar
python scripts/backfill_shared_mailbox_network_id.py                # dry-run
python scripts/backfill_shared_mailbox_network_id.py --aplicar
```

O segundo recusa-se sem `TENANT_DEFAULT_NETWORK_ID` (ou `--rede`).

### C5. TTL das tentativas de login do Portal

```bash
python scripts/backfill_portal_attempts_ttl.py
python scripts/backfill_portal_attempts_ttl.py --aplicar
```

### C6. `co_buyers` (D-18)

```bash
python scripts/migrar_co_buyers_adicionais.py
python scripts/migrar_co_buyers_adicionais.py --aplicar
```

### C7. Cópias órfãs de configuração (só com o código novo já em produção)

```bash
python scripts/limpar_copias_orfas_system_config.py
python scripts/limpar_copias_orfas_system_config.py --aplicar
```

Só apaga o que prova ser cópia **exacta** da configuração global. Nunca apaga configuração real.

### C8. Medições (só leitura) — colar os números no `worklog.md`

```bash
python scripts/medir_colecoes.py --csv /tmp/colecoes.csv
python scripts/medir_datas_de_nascimento.py
```

## Parte D — Verificação

* Repete o `dry-run` de cada passo: tem de dizer «0 a fazer».
* Login como Master e como um utilizador de cada rede: cada um só vê a sua rede (Kanban, clientes, tarefas).
* Envia um email de teste pelo Webmail: fica em «Enviados».
* Abre um processo: o separador Documentos lista os ficheiros.
* Logs sem avisos novos de «rede por determinar».

## Já executado noutras sessões (não repetir)

`fix_s3_folder_anomalies` (anomalias do `s3_folder`), `diagnose_assignment_drift` (desfasamento de
atribuições) e a medição da D-19.

## Limites

* A ordem e os comandos vêm da leitura dos scripts, **não** de uma execução em produção — nenhum
  foi corrido contra a base de dados real nesta sessão.
* Não sei quais destes passos já correram em produção; o `dry-run` de cada um di-lo.

## Parte D — Atlas: lista de IPs de saída do Render (Out 2026)

O incidente de 16 Out 2026 (deploy «Timed Out», login 500) foi a *IP Access List* do Atlas vazia.
O `0.0.0.0/0` provisório já foi apagado — **a lista tem de ter os IPs de saída reais ANTES de o próximo
deploy ou reinício**, senão o incidente repete-se.

**Onde está a lista (autoridade).** Painel do Render → serviço → botão **Connect** (canto superior direito)
→ separador **Outbound**. Mostra os IPs (ou intervalos) de saída da *região* do serviço. Os dois serviços
do `render.yaml` — `powercell` (web) e `powercell-worker` — estão ambos em `frankfurt`, pelo que **partilham
o mesmo conjunto**; confirma-o abrindo o painel de cada um (não verifiquei daqui: não tenho acesso ao Render).
Os IPs são partilhados por todos os serviços da mesma região, não são exclusivos deste projecto.

**Prova de que o serviço sai mesmo por eles** (Shell do serviço, um de cada vez, web e worker):

```bash
cd backend && python scripts/diagnosticar_saida_para_atlas.py
```

Imprime os IPs de saída observados (3 serviços de eco × 3 amostras) e faz `ping` ao Atlas com o `MONGO_URL`
do serviço (sem imprimir credenciais). Saída 0 = o Atlas aceita; 1 = não aceita (quase de certeza a lista
de acesso). Os IPs observados têm de constar da lista do painel; **o que se acrescenta ao Atlas é a lista do
painel inteira**, não só o IP que o eco devolveu (a saída roda por vários).

**No Atlas.** *Network Access → Add IP Address*, um registo por IP/intervalo da lista do painel, **sem**
«Delete after…» (foi provavelmente uma entrada temporária que expirou que causou o incidente — confirmar no
*Activity Feed* do projecto). Depois de correr o diagnóstico nos dois serviços com saída 0, a lista final
deve ter só os IPs do Render (mais, se for o caso, os IPs de quem opera à mão).

**Se o Render mudar os IPs** (mudança de região, ou aviso do Render): repetir esta parte. Um alerta no Atlas
para «Network Access» alterada e o diagnóstico acima no checklist de cada deploy evitam descobrir isto por 500.

## Parte E — D-15: cifrar as datas de nascimento existentes

Pré-requisitos: o deploy da Parte A com o código da D-15 **nos dois serviços**, e a mesma `ENCRYPTION_KEY`
de sempre (o script recusa-se se a chave não abre os NIFs que já estão cifrados — código 4).
**Snapshot do Atlas antes de aplicar.**

```bash
cd backend
python -m scripts.migrar_datas_de_nascimento             # descreve: contagens, nada é escrito
python -m scripts.migrar_datas_de_nascimento --aplicar   # cifra e carimba o ano
python -m scripts.migrar_datas_de_nascimento             # 2.ª passagem: «0 com algo a fazer»
python scripts/medir_datas_de_nascimento.py              # «com data em claro: 0» nas duas colecções
```

* A ordem deploy → migração **não importa**: o filtro Sub35 aceita os dois estados (ver `services/sub35.py`).
  Fazer a migração ANTES do deploy é que não: o código antigo não sabe ler datas cifradas.
* «perdidos para edições» > 0 = alguém editou o registo a meio; volta a correr.
* «cifradas e ILEGÍVEIS» > 0 = datas cifradas com outra chave. O script não lhes toca.
* **Custo assumido:** o filtro «Sub35» passa a ser por ANO de nascimento e deixa de apanhar quem nasceu em
  `ano_corrente − 36` e ainda não fez anos (a etiqueta no cartão continua exacta).

## Parte F — Notificações no Telegram (Out 2026)

Sem `TELEGRAM_BOT_TOKEN` o canal fica desligado e nada muda. Para ligar:

1. No Telegram, falar com **@BotFather** → `/newbot` → dar nome (ex.: «PowerCell Avisos») e username
   (tem de acabar em `bot`). Guardar o token que ele devolve. Opcional: `/setuserpic`, `/setdescription`.
2. No Render, serviço **web** (não é preciso no worker), *Environment*:
   - `TELEGRAM_BOT_TOKEN` = o token do passo 1;
   - `TELEGRAM_WEBHOOK_SECRET` = uma cadeia aleatória longa (só `A-Z a-z 0-9 _ -`), ex.
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`;
   - `FRONTEND_URL` já tem de existir (é o link do botão «Abrir no PowerCell»);
   - opcionais: `TELEGRAM_BOT_USERNAME` (poupa um `getMe`), `TELEGRAM_JANELA_SEGUNDOS` (90 por omissão:
     quanto tempo se juntam os avisos do mesmo processo), `TELEGRAM_WEBHOOK_URL` (por omissão
     `RENDER_EXTERNAL_URL` + `/api/telegram/webhook`).
3. Deploy. No arranque o worker primário regista o webhook: procurar nos logs «📨 Webhook do Telegram
   registado.» (ou «⚠️ Webhook do Telegram não registado: …» com o motivo).
4. Cada utilizador liga a sua conta em **Definições › Notificações › Ligar Telegram**.
