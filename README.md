# app.py (sem validação OpenAI) + fluxo VIP

- /start: áudio de introdução (FILE_ID_AUDIO) + imagem + follow-up de 120s.
- Após confirmar: mostra imagem final + botão **🟣 Acessar VIP**.
- VIP:
  - Pergunta inicial + botões **Quero Garantir** / **Me explica antes**
  - Envia áudio do VIP (FILE_ID_AUDIO_VIP)
  - Envia até 3 vídeos (FILE_ID_VIDEO1/2/3 ou capturados via chat)
  - Pede print do depósito (≥ R$35, hoje) e agenda lembrete em 7 minutos.
- Captura automática de:
  - Áudio/voz → salva em `file_ids.json`.
  - Vídeo (video/document/video_note) → salva `video1→video3`.

Variáveis:
- TELEGRAM_TOKEN
- FILE_ID_AUDIO
- FILE_ID_AUDIO_VIP
- FILE_ID_VIDEO1, FILE_ID_VIDEO2, FILE_ID_VIDEO3
