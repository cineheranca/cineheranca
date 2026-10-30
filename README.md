# Claquete

Agregador de cinema, TV e séries hospedado no GitHub Pages. Sem banco de dados: tudo é arquivo no repositório.

- `feeds.json` – lista de fontes (RSS de sites, podcasts e canais do YouTube)
- `scripts/fetch_news.py` – lê os feeds, extrai imagem/áudio/vídeo, traduz para PT-BR
- `.github/workflows/update.yml` – roda a cada 30 min e faz commit de `data/items.json`
- `data/items.json` – notícias atuais · `data/translations.json` – cache de traduções
- `index.html` – o site

## Publicar
1. Crie o repositório e suba estes arquivos.
2. Settings → Pages → Deploy from a branch → `main` / root.
3. Settings → Actions → General → Workflow permissions → Read and write.
4. Aba Actions → "Atualizar notícias" → Run workflow (primeira carga).

## Tradução
Padrão: `deep-translator` (sem chave). Para usar LibreTranslate, crie os secrets `LIBRETRANSLATE_URL` e `LIBRETRANSLATE_KEY`.

## Vídeos do YouTube
Feed: `https://www.youtube.com/feeds/videos.xml?channel_id=ID_DO_CANAL`

## Países e descoberta de fontes
- `paises` no `feeds.json`: cada país gera buscas de cinema e séries no Google News (edite os termos).
- `scripts/discover.py` (Action semanal): acha sites e podcasts novos via GDELT e iTunes, valida o feed e lista em `data/candidatos.json`.
- Para aprovar: edite o arquivo no GitHub e troque `"aprovar": false` por `true` (entra no próximo ciclo) ou `"ignorar"`.
- Modo automático: Settings → Secrets and variables → Actions → Variables → `AUTO_APPROVE` = `true`.
