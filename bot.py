
import os, io, base64, logging
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
from PIL import Image

# ---- Config ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot-validacao")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TZ_OFFSET = int(os.getenv("TZ_OFFSET_HOURS", "-3"))  # padrão -03:00 (Brasil)
MIN_VALUE = float(os.getenv("MIN_DEPOSIT_VALUE", "35"))  # mínimo R$35
VALIDATION_MODE = os.getenv("VALIDATION_MODE", "today")  # 'today' ou 'after_chat'

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN não definido.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY não definido.")

client = OpenAI(api_key=OPENAI_API_KEY)

chat_start_times = {}  # armazena quando o usuário iniciou a conversa

# ---- Util ----
def now_iso():
    tz = timezone(timedelta(hours=TZ_OFFSET))
    return datetime.now(tz).isoformat()

def today_str_ddmmyy():
    tz = timezone(timedelta(hours=TZ_OFFSET))
    return datetime.now(tz).strftime("%d.%m.%y")

async def _download_bytes(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    file = await context.bot.get_file(file_id)
    ba = await file.download_as_bytearray()
    return bytes(ba)

def _img_bytes_to_data_url(raw: bytes) -> str:
    img = Image.open(io.BytesIO(raw))
    if img.mode in ("P", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

# ---- Prompts ----
def _build_user_instructions(chat_started_at_iso: str) -> str:
    if VALIDATION_MODE.lower() == "today":
        today_txt = today_str_ddmmyy()
        rule_line = f"Considere APROVADO somente se: status='Concluído', valor >= {MIN_VALUE:.2f} e a data do depósito é IGUAL a {today_txt}."
    else:
        rule_line = f"Considere APROVADO somente se: status='Concluído', valor >= {MIN_VALUE:.2f} e a data/hora do depósito é POSTERIOR a {chat_started_at_iso}."

    return f"""
    Você é um validador de prints de histórico da BetBoom.
    Analise APENAS o item de **Depósito** que está **expandido** (seta para cima).
    Extraia campos:
      - valor (número, ignorar 'R$')
      - data_hora_texto (como aparece, ex.: 17.07.25 00:18)
      - status (ex.: Concluído)
      - id_transacao (se visível)

    Regras de aprovação:
    - {rule_line}

    Responda em JSON estrito:
    {{
      "valor": number | null,
      "data_hora_texto": string | null,
      "status": string | null,
      "id_transacao": string | null,
      "aprovado": boolean,
      "motivos": string[]
    }}
    Se algum dado essencial estiver ausente, marque "aprovado": false e explique em "motivos".
    """

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_start_times[chat_id] = now_iso()
    mode_msg = "hoje (dd.mm.aa)" if VALIDATION_MODE.lower() == "today" else "após o início da conversa"
    await update.message.reply_text(
        f"Olá! 👋\nEnvie um PRINT do seu depósito.\n"
        f"A validação exige: status Concluído, valor >= R$ {MIN_VALUE:.2f} e data {mode_msg}."
    )

async def _handle_image_common(update: Update, context: ContextTypes.DEFAULT_TYPE, raw: bytes):
    chat_id = update.effective_chat.id
    chat_started_at_iso = chat_start_times.get(chat_id)
    if not chat_started_at_iso:
        await update.message.reply_text("Por favor, envie /start antes de mandar o print.")
        return

    try:
        data_url = _img_bytes_to_data_url(raw)
        user_prompt = _build_user_instructions(chat_started_at_iso)
        response = client.responses.create(
            model="gpt-4o",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_prompt},
                    {"type": "input_image", "image_url": data_url}
                ]
            }],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "deposit_validation",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "valor": {"type": ["number","null"]},
                            "data_hora_texto": {"type": ["string","null"]},
                            "status": {"type": ["string","null"]},
                            "id_transacao": {"type": ["string","null"]},
                            "aprovado": {"type": "boolean"},
                            "motivos": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["aprovado","motivos"]
                    }
                }
            },
            temperature=0
        )

        result_json = response.output_text  # já vem como JSON string pelo response_format
        await update.message.reply_text(result_json[:4096])

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text("⚠️ Ocorreu um erro ao analisar a imagem. Tente reenviar como *foto* (não como arquivo).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    raw = await _download_bytes(context, photo.file_id)
    await _handle_image_common(update, context, raw)

async def handle_image_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not (doc.mime_type or "").startswith("image/"):
        return
    raw = await _download_bytes(context, doc.file_id)
    await _handle_image_common(update, context, raw)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_image_document))
    app.run_polling()

if __name__ == "__main__":
    main()
