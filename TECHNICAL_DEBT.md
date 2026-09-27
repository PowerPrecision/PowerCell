# Registo de Dívida Técnica — PowerCell

Dívida **conhecida, avaliada e adiada de propósito**. Não é uma lista de
desejos nem um caderno de ideias: cada entrada foi encontrada a resolver outra
coisa, foi medida, e a decisão de não a fechar naquele momento foi tomada por
escrito.

Isto existe porque dívida que vive só em comentários de código não é um
registo — ninguém a lê toda, ninguém a prioriza, e ela reaparece como
incidente. Quando uma entrada for fechada, sai daqui e entra no `worklog.md`
com a iteração que a fechou.

**Ao acrescentar uma entrada:** o que está mal, por que razão foi adiado,
quem é atingido se explodir, e o que é preciso para a fechar. Sem estes
quatro, é um comentário e não uma dívida.

---

## Segurança

### D-1 · `document_direct_upload.py` sem quarentena de magic bytes
**Onde:** `backend/services/document_direct_upload.py` (o `confirm-upload` do **CRM**).

O caminho do CRM usa o mesmo upload pré-assinado do Portal e tem a mesma
lacuna que a [quarentena](ARCHITECTURE.md) fechou no Portal: os bytes vão do
browser para o S3 sem passar pelo backend, e o `file_size`/`content_type`
gravados são os que o cliente **declarou**. A parede de `file_validation.py`
não é chamada neste caminho.

**Porque foi adiado:** a exposição é **interna** — utilizadores autenticados da
equipa, não a Internet. Interromper o Caminho 4 (Portal do Cliente) por ela
custava mais do que o risco que fecha.

**Quem é atingido:** um membro da equipa com sessão válida pode arquivar
qualquer conteúdo no bucket, e os metadados do documento ficam a mentir. Não é
escalada de privilégio; é integridade de dados e higiene do bucket.

**Para fechar:** `services.s3_content_quarantine.exigir_conteudo_valido` serve
tal como está — é uma chamada, mais o `file_size`/`content_type` a vir do
veredicto. Ver o padrão em `portal_upload_ops.run_confirm_portal_upload`.

---

### D-2 · Segredo JWT partilhado entre o Portal e o staff
**Onde:** `backend/config.py` (`JWT_SECRET`), `services/portal_security.py`,
`services/auth.py`.

Os tokens do Portal do Cliente e os do staff são assinados com o **mesmo**
segredo. Até ao lote dos WebSockets externos, o que separava as duas famílias
era uma **coincidência**: o `sub` de um token de Portal é um `process_id`, que
não existe em `db.users`.

**Porque foi adiado:** separar os segredos invalida **todos** os magic links em
circulação — clientes a meio de um onboarding perdem o acesso e têm de pedir
um link novo. A mitigação escolhida foi tornar a claim `type` **autoritativa**
nos dois lados (`ws_client_identity.tipo_de_token_e_de_staff` /
`tipo_de_token_e_do_portal`), o que fecha o problema prático sem invalidar
nada.

**Quem é atingido:** com o `type` autoritativo, ninguém hoje. A dívida é de
**defesa em profundidade**: um segredo só significa que um erro futuro num
verificador de tipo volta a ser explorável, em vez de ser inofensivo.

**Para fechar:** `PORTAL_JWT_SECRET` próprio + rotação com janela de
sobreposição (aceitar os dois segredos durante o tempo de vida do magic link
mais longo), ou aceitar a invalidação numa janela de manutenção anunciada.

---

### D-3 · `GOV_AUTH_JWT_SECRET` com valor por omissão em código
**Onde:** `backend/services/gov_auth_api_helpers.py:20`

```python
_JWT_SECRET = os.environ.get("GOV_AUTH_JWT_SECRET", "dev-secret-change-in-prod")
```

O `gov_token` carrega `verified_by_gov: True` e pré-preenche o formulário
público. Se a variável não estiver definida em produção, qualquer pessoa forja
uma identidade "verificada pelo Estado".

**Porque foi adiado:** é o fluxo gov **mockado**; não está em uso real. Mas é
o mesmo padrão do CORS do bucket S3 — um recurso em código que ninguém vê
falhar.

**Quem é atingido:** se o fluxo gov entrar em produção sem a variável, a
verificação de identidade do Estado passa a ser forjável.

**Para fechar:** falhar no arranque quando `ENVIRONMENT` é de produção e a
variável não existe (o padrão que o `config.py` já usa para o `JWT_SECRET` e o
`CORS_ORIGINS`), e apagar o valor por omissão.

---

### D-4 · Varrimento de limites de pedidos nos restantes routers
**Onde:** `backend/routes/*.py`

Os três endpoints de upload do Portal não tinham `@limiter.limit` nenhum,
ao lado de um `/public/client-registration` com `5/hour` desde sempre. O
padrão foi encontrado no lote do Incidente P0 e corrigido **só** nesses três.
Não houve inventário dos restantes.

**Porque foi adiado:** o incidente P0 era um hotfix e alargá-lo a 60 ficheiros
de rotas tornava-o irrevisável.

**Quem é atingido:** qualquer endpoint autenticado mas sem limite é um vector
de varrimento ou de esgotamento de recursos.

**Para fechar:** inventário por AST de todos os `@router.<método>` sem
`@limiter.limit`, triado por superfície (público > Portal > staff), com um
teste-inventário como o de
`test_portal_upload_path_traversal.py::TestOsEndpointsDoPortalTemLimiteDePedidos`.

---

### D-5 · Tolerância a tokens de staff sem claim `type`
**Onde:** `backend/services/ws_client_identity.py::tipo_de_token_e_de_staff`

Os três produtores de tokens do CRM estampam hoje `type: "access"`
(`auth.tipo_de_token_do_crm`), mas dois deles — o `/auth/register` e o
*impersonate* — não estampavam nada antes deste lote. O verificador aceita
`None` para não invalidar as sessões abertas no momento do deploy.

**Porque foi adiado:** é a condição para o deploy não deslogar a equipa inteira.

**Quem é atingido:** ninguém enquanto a lista de tipos **estranhos** for
recusada — a segurança está nesse lado, não neste.

**Para fechar:** passadas `JWT_EXPIRATION_HOURS` (hoje **24h**) depois do
deploy, nenhum token sem `type` pode existir: apagar o ramo do `None` e o teste
`test_um_token_de_staff_LEGADO_sem_type_continua_a_entrar`. É uma linha, e é a
dívida mais fácil desta lista.

---

### D-11 · Os sourcemaps do frontend são servidos em produção
**Onde:** `frontend/vite.config.js` (`sourcemap: isProduction ? 'hidden' : true`)

`'hidden'` remove o comentário `//# sourceMappingURL=` do ficheiro mas
**continua a emitir os `.map`**, que vão no artefacto de deploy e são
servidos: `GET https://www.powercell.pt/assets/<chunk>.js.map` devolve 200
com o código-fonte completo, comentários incluídos.

Foi o que permitiu diagnosticar o erro desta iteração sem a mensagem de
erro — resolver `6:23816` para `UsersAccessAdminTab.jsx:103` — e é o que
permite a qualquer pessoa ler o frontend todo.

**Porque foi adiado:** não é uma correcção óbvia, é um **compromisso**.
Apagar os `.map` do artefacto cega o diagnóstico de todos os erros futuros,
incluindo os do Sentry. Enviá-los para o Sentry e não os servir mantém as
duas coisas, mas é trabalho de pipeline (o plugin do Sentry já está no
`vite.config.js`, ver o bloco `sourcemaps:`) e uma decisão de quem paga a
conta.

**Quem é atingido:** ninguém directamente — não há autenticação nem segredos
nos mapas (o DSN do Sentry num bundle é público por desenho). O que se
expõe é estrutura, nomes de endpoints internos e os comentários que
explicam regras de negócio, o que baixa o custo de quem procure uma
fraqueja.

**Para fechar:** decidir entre (a) `sourcemap: false` em produção, (b)
upload para o Sentry com `filesToDeleteAfterUpload` no artefacto, ou (c)
manter e assumir a decisão por escrito. A opção (b) é a que não perde nada.

---

### D-10 · As definições de índices vivem dentro de `create_indexes`
**Onde:** `backend/services/db_indexes.py::create_indexes`

Os índices são 15 literais de lista **locais** dentro de uma função async
de ~380 linhas, cada um seguido do seu ciclo de criação. Não há forma de
um teste (nem de um script de diagnóstico) obter as definições sem
executar a função contra uma base de dados.

Foi isso que permitiu o placebo: o `test_db_indexes.py` mantinha uma
CÓPIA das definições escrita à mão e injectava-a em
`sys.modules['services.db_indexes']`, substituindo o módulo inteiro. A
cópia tinha 2 colecções e 6 índices de `processes`; o módulo real tem 13 e
18. Hoje o teste lê o módulo por **AST** — honesto, mas é uma leitura de
texto a fazer o trabalho que uma estrutura de dados faria.

**Porque foi adiado:** mover 380 linhas do caminho de ARRANQUE da
aplicação, no dia de um deploy, por um ganho que é de forma e não de
comportamento. O AST fecha o problema que importava (o teste passou a
poder falhar) sem tocar em produção.

**Quem é atingido:** ninguém em produção. Quem escrever o próximo teste ou
script sobre índices paga o preço: ou repete a leitura por AST, ou
recria a cópia que acabámos de apagar — e a cópia é o defeito.

**Para fechar:** extrair um `INDEX_DEFINITIONS: dict[str, list[dict]]` ao
nível do módulo, `create_indexes` passa a iterá-lo (`for colecao, indices
in INDEX_DEFINITIONS.items()`), e o leitor por AST do teste é substituído
por um import. A lista de colecções que o `get_index_stats` reporta sai da
mesma estrutura, em vez de ser uma segunda lista à mão.

---

## Correcção e modelo de dados

### D-6 · `INACTIVE_STATUSES` é resíduo legado, não definição
**Onde:** `backend/services/process_status.py`,
`services/my_clients_api_helpers.py`, `services/client_list_search.py`

Quem define o que está "fechado" é a flag `is_active` da fase no **motor de
workflow** (`workflow_phases.nomes_terminais`). O `INACTIVE_STATUSES` é uma
lista cravada em código que sobrevive como **recurso** para quando o motor não
é injectado — e continua a ser o caminho usado em `client_list_search`.

**Porque foi adiado:** substituí-lo exige passar o motor por funções que são
**puras** de propósito (é isso que as torna testáveis sem Mongo no
`backend-fast`), e cada chamador tem de o injectar.

**Quem é atingido:** uma fase nova marcada como terminal no painel de admin
não é reconhecida como fechada nos caminhos que ainda usam a lista — os
números de "carteira activa" divergem do quadro.

**Para fechar:** injectar `terminais=` em todos os chamadores (o
`my_clients_api_helpers` já o aceita) e reduzir o `INACTIVE_STATUSES` a um
recurso de arranque, com um teste a afirmar que nenhum caminho de produção o lê
sem tentar o motor primeiro.

---

## Produto e âmbito

### D-7 · Relatório semanal do CEO mantém âmbito global
**Onde:** `backend/services/analytics_service.py::generate_weekly_team_report`

Sem `user`, o relatório atravessa todas as redes e regista um `warning`. A
chamada agendada de segunda-feira não passa utilizador.

**Porque foi adiado:** é uma **decisão de produto** (a Direcção quer o
consolidado) e não um defeito. Fica registada porque é a única excepção
deliberada ao isolamento por rede do Lote 4/5.

**Para fechar:** decidir se o email de segunda é consolidado (e então
documentá-lo como excepção explícita, com destinatários credenciados nas três
empresas) ou segmentado por rede.

---

### D-8 · `db.emails` não tem carimbo de rede
**Onde:** colecção `emails`

Os processos, clientes e leads têm `network_id`; os emails não. Pertence ao
lote do webmail.

**Para fechar:** carimbo na escrita (`resolve_tenant_stamp`) + backfill com a
regra do `rede_consensual` (recusa adivinhar quando há mais de uma candidata).

---

## Fechadas

Ficam aqui só o número e a iteração que as fechou — o detalhe vive no
`worklog.md`, que é o histórico. Uma dívida fechada não volta a este registo.

| # | Dívida | Fechada em |
|---|---|---|
| D-9 | Portal do Cliente em polling das mensagens | Iteração `ws-portal-ui` — ligado a `/api/ws/portal` com o polling mantido como recurso |
