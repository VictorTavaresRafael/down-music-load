# Contribuindo

Valeu pelo interesse! Toda ajuda conta: issue, ideia, correção de typo ou feature nova.

## Fluxo

1. Faça um fork e crie uma branch: `git checkout -b feat/minha-feature`
2. Prepare o ambiente:
   ```bash
   cd youtube-downloader
   python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```
3. Faça sua mudança e rode:
   ```bash
   pytest
   ruff check .
   ```
4. Abra um Pull Request explicando **o quê** e **por quê**.

## Padrões

- Python 3.11+, tipado, formatação/lint com `ruff` (linha até 120 colunas).
- Testes não acessam a internet: use o fixture `fake_ydl` de `tests/conftest.py`.
- Frontend é HTML/CSS/JS puro em `app/static/` — sem build step. Mantenha assim.
- Commits curtos e no imperativo (ex.: `Adicionar cancelamento de download`).

## Reportando bugs

Abra uma issue com:

- O que você fez (URL de exemplo, formato escolhido)
- O que esperava e o que aconteceu
- Saída de `GET /api/health` e sua versão do Python/SO

Bugs de extração de um site específico normalmente são do yt-dlp — tente `pip install -U yt-dlp` antes.
