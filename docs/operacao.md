# Operação do Ofertinhas

Como o sistema roda hoje, como publicar uma versão nova e como voltar ao PC se a nuvem falhar.

## Quem faz o quê

| Peça | Onde roda | Papel |
|---|---|---|
| Backend (API da extensão, bot, jobs, banco) | **Nuvem**: Worker `ofertinhas` da Cloudflare, com o SQLite de um Durable Object | Produção. Ranqueia, desenha os cards, posta e manda os avisos |
| Coleta e links de afiliado | Extensão no **Brave** do PC | O Mercado Livre bloqueia navegador automatizado, então isso não sai do PC |
| Sessões de coleta | **Agendador do Windows** (`Ofertinhas coleta 05h30`, `11h30` e `17h00`) | Acorda o PC, abre o Brave e o mantém acordado 45 min. Se a nuvem ainda pedir coleta ou link, a sessão se estende de 5 em 5 min, até 2 h |
| `python -m ofertinhas run` | PC | **Só desenvolvimento e plano B.** Recusa rodar enquanto a nuvem estiver no ar |

O PC e a nuvem rodam os mesmos jobs no mesmo calendário (`jobs.SCHEDULE`):

| Job | Quando (horário de SP) |
|---|---|
| `publish`, `notify_pending`, `render` | todo minuto |
| `stock_alert` | a cada 5 min |
| `expire` | a cada 15 min |
| `prune`: limpa ofertas, decisões e preços com mais de `retention_days` (60) | 04:30 |
| `status`: edita a mensagem fixada no chat do admin | 08:00, 13:00 e 20:00 |
| `backup` (só no PC; a nuvem usa a recuperação de 30 dias do Durable Object) | 04:00 |

### Coleta pedida pela nuvem (`collect_now`)

Um grupo está "curto" quando nem todas as aprovadas, com link ou esperando, cobrem os posts
das próximas `stock_hours` horas. Nesse caso o `/ext/config` devolve `collect_now: true` e a
extensão coleta na hora, sem esperar o alarme. Ela faz isso no máximo uma vez a cada
`collector.collect_now_gap_min` minutos (30 por padrão), e nunca com a coleta pausada.

### Desconto inflado (`price_check`)

Cada coleta guarda o preço e o preço "de" no `price_history`. Antes de decidir, a oferta é
conferida contra os últimos `lookback_days` (30). Duas situações barram a oferta:

- **Preço já foi menor:** se o preço já esteve mais de `tolerance_pct` (5%) abaixo do atual,
  o desconto conta como 0%.
- **Preço "de" inflado:** se o "de" subiu mais que a folga, o desconto é recalculado sobre o
  "de" antigo.

As regras de desconto e comissão decidem com esse desconto conferido. O total de ofertas
barradas no dia aparece no status fixado e em `/admin/stats` (`inflated_today`).

## Tokens

- `EXTENSION_TOKEN` (header `X-Ofertinhas-Token`): usado pela extensão nas rotas `/ext/*` e
  `/health`.
- `ADMIN_TOKEN` (header `X-Ofertinhas-Admin`): usado só nas rotas `/admin/*` (`status`,
  `stats`, `post-now`, `post-x` e `import`). Sem ele configurado, essas rotas recusam tudo.
  O `cloud/worker/push_secrets.py` cria o token no `.env` se faltar e o envia ao Worker.

```powershell
$h = @{ "X-Ofertinhas-Admin" = (Select-String -Path .env -Pattern '^ADMIN_TOKEN=(.*)').Matches[0].Groups[1].Value }
Invoke-RestMethod https://ofertinhas.marciopetigrosso.workers.dev/admin/status -Headers $h
```

## Publicar uma versão (deploy versionado)

Na pasta `cloud/worker`, com o `.venv` no PATH:

```powershell
python push_secrets.py   # só quando um segredo mudar ou for novo (ex.: ADMIN_TOKEN)
python deploy.py         # --dry-run valida sem publicar
```

O `deploy.py` faz cinco coisas, nesta ordem:

1. Recusa se houver mudança não commitada. A versão é o commit; `--allow-dirty` publica assim
   mesmo e marca a versão com `+mod`.
2. Roda `tests/cloud`, que inclui o teste do bundle.
3. Monta o bundle com o `version.json`: commit, hash do `config.yaml` e data.
4. Publica com `--tag <commit>` e `--message "<commit> config <hash>"`.
5. Guarda a cópia do `config.yaml` publicado em `data/deploys/` e anota o deploy em
   `data/deploys/deploys.jsonl`.

O `config.yaml` fica fora do Git e não vai ao R2, porque o bucket é público.

Para conferir o que está no ar, veja o `build` em `/health` e em `/admin/status`, ou a linha
"Versão" do status fixado.

**Voltar a uma versão anterior:** `npx wrangler versions list` mostra as tags e
`npx wrangler rollback <version-id>` volta o código. Para voltar o config também, faça
checkout do commit, copie o yaml de `data/deploys/` para `config.yaml` e rode o
`python deploy.py --allow-dirty`.

## Plano B: voltar ao PC

Use só se a nuvem ficar fora do ar por muito tempo. Com a nuvem e o PC ligados ao mesmo
tempo, os dois postam nos grupos.

1. Desligue a postagem na nuvem: `DRY_RUN = "true"` no `cloud/worker/wrangler.toml` e
   `python deploy.py --allow-dirty`.
2. `python set_webhook.py --delete`, para o bot voltar ao polling.
3. Na extensão, troque o `backendUrl` para `http://127.0.0.1:8765` (no
   `extension/config.local.json` ou nas Opções) e recarregue a extensão.
4. `python -m ofertinhas run --take-over`.

Para voltar à nuvem, faça o caminho inverso: pare o `run`, rode `python set_webhook.py`,
volte o `backendUrl` da extensão, ponha `DRY_RUN = "false"` e rode o `python deploy.py`.

O banco do PC e o da nuvem são separados. O `cloud/worker/import_history.py` leva o
cooldown e os posts recentes do PC para a nuvem.
