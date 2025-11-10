# Bot Telegram – Funil de Boas‑Vindas (sem ManyChat)

Bot em **Python** usando `python-telegram-bot` (v20) com:
- Boas‑vindas por funil (drip) usando JobQueue
- Consentimento do usuário (LGPD-friendly)
- Deep‑link para levar do grupo ao privado
- Rastreamento de origem (grupo/canal)
- SQLite para persistência simples

## Como usar (local)
1. Copie `.env.example` para `.env` e coloque seu token do BotFather.
2. Crie o ambiente e instale dependências:
   ```bash
   python -m venv venv
   # Windows: .\venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Rode o bot (modo polling):
   ```bash
   python app.py
   ```

## Deploy no Railway (24/7)
1. Faça **fork** ou suba este repo no **GitHub**.
2. No **Railway**: New Project → Deploy from GitHub Repo → selecione seu repo.
3. Em **Variables**, adicione:
   ```
   TELEGRAM_TOKEN=seu_token_aqui
   ```
4. O Railway detecta Python automaticamente. O `Procfile` contém:
   ```
   start: python app.py
   ```

## Observações importantes do Telegram
- O bot **não pode iniciar DM** com o usuário. É preciso o usuário clicar em **Start** ou abrir via **deep‑link**.
- Em grupos/supergrupos, o bot recebe `new_chat_members` (melhor se for admin) e pode responder com botão para o privado.
- Para canais/comunidades com aprovação, use **Chat Join Request** para aprovar e direcionar ao privado.

## Estrutura
```
.
├─ app.py
├─ db.py
├─ sequences.py
├─ utils.py
├─ requirements.txt
├─ .env.example
├─ README.md
├─ Procfile
└─ Dockerfile
```

## Licença
Você pode usar e adaptar livremente.
