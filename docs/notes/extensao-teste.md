# Extensão no Brave: instalação e primeiro teste

Este teste valida **a coleta e a geração de link de verdade**, com a sua conta. Bot do Telegram e disparo ainda não entram: os avisos aparecem no terminal.

## 1. Preparar o backend (uma vez)

No PowerShell, na pasta do projeto:

1. `Copy-Item config.example.yaml config.yaml` e ajuste os nichos e categorias, se quiser. Para este teste, os chat ids de exemplo podem ficar.
2. `Copy-Item .env.example .env`
3. `.\.venv\Scripts\python.exe -m ofertinhas new-token` e cole a linha `EXTENSION_TOKEN=...` no `.env`.
4. No `.env`, preencha `ML_AFFILIATE_TAG=` com a sua tag de afiliado.

## 2. Subir a API local

```
.\.venv\Scripts\python.exe -m ofertinhas api
```

Deixe esse terminal aberto. Cada chamada da extensão aparece ali (`POST /ext/raw`, `GET /ext/link-requests`…), assim como os avisos ao admin (`[aviso ao admin] ...`).

## 3. Instalar a extensão

1. No Brave, abra `brave://extensions` e ligue o **Modo do desenvolvedor**.
2. **Carregar sem compactação** → selecione a pasta `extension` do projeto.
3. Fixe o ícone laranja "%" na barra.
4. Clique com o botão direito no ícone → **Opções**. Cole o mesmo token do `.env` e clique em **Testar conexão**. Tem que aparecer "Conectado ao backend".
5. Recomendado: em `brave://settings/system`, ligue "Continuar executando apps em segundo plano quando o Brave estiver fechado".

## 4. Teste da coleta

1. Esteja logado no Mercado Livre no Brave.
2. Abra o popup e clique em **Coletar agora**.
3. O esperado:
   - Uma aba **fixada** do portal de afiliados abre (ou é reaproveitada).
   - No terminal aparecem vários `POST /ext/raw ... 200`, com 5 a 15 s entre eles: 3 páginas por categoria, 6 categorias no exemplo, ~2 a 4 min no total.
   - No fim, o popup mostra "Última coleta: HH:MM · N ofertas (M novas)".
4. Se o popup mostrar **Pausada**, o motivo diz o que aconteceu: login, captcha, token ou recusa do ML. O terminal também mostra o aviso.

## 5. Teste da geração de link

Depois da coleta, as ofertas com nota ≥ `auto_approve_at` já ficam aprovadas. Ofertas pendentes ainda precisam do bot (próxima fase).

1. Com aprovadas na fila, em até ~1 a 2 min aparecem no terminal `GET /ext/link-requests` e depois `POST /ext/links`.
2. O popup mostra "Links hoje: N gerados".
3. **Atenção:** é a sua conta real. Cada link gerado entra na sua lista de links do portal, igual ao Gerador de link manual. O limite é de 30 por hora, um a cada 30 a 90 s.

## 6. Teste do freio

1. No popup, clique em **Pausar**. O ícone ganha "II" e o terminal mostra `[aviso ao admin] ⏸️ A extensão parou: manual...`.
2. Clique em **Retomar**. O badge some e uma coleta começa em ~5 s.

## O que me mandar depois do teste

- O texto do popup (estado, última coleta, links hoje).
- As linhas do terminal com erro, se houver (sem o token).
- Se o ML mostrou captcha ou deslogou em algum momento.
