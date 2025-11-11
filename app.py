
import os, json, asyncio, logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue, MessageHandler, filters
)
from telegram.error import RetryAfter, TimedOut
from telegram.request import HTTPXRequest

# ========= LOGGING =========
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("presente-do-jota")

# ========= CONFIG =========
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN") or ""
if not TOKEN:
    raise RuntimeError("❌ Defina TELEGRAM_TOKEN no .env ou nas Variables do Railway")

# Links
LINK_CADASTRO = (
    "https://land.betboom.bet.br/promo/topslots-br/?utm_source=inf&utm_medium=bloggers&utm_campaign=265&utm_content=topslots_br&utm_term=5610&aff=alanbase&qtag=a5610_t265_c270_s019a7023-794b-7178-92ef-f9ceb8fe77a2_"
)
LINK_COMUNIDADE_FINAL = "https://t.me/+Qu9Lkn7hrX1kZjQx"

# Mídias
IMG1_URL = "https://i.postimg.cc/Z5k8RDCs/presente-da-marluce.png"
IMG2_URL = "https://i.postimg.cc/WzkDcT6V/presente-da-marluce-2.png"

# Cache JSON
CACHE_PATH = os.path.join(os.path.dirname(__file__), "file_ids.json")
def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def save_cache(d: dict):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f: json.dump(d, f)
    except Exception as e: log.warning("Não consegui salvar cache de file_id: %s", e)
FILE_IDS = load_cache()

# Constantes
CB_CONFIRM_SIM = "confirm_sim"
WAIT_SECONDS = 120
PENDING_FOLLOWUPS: set[int] = set()
AUDIO_FILE_LOCAL = "Audio.mp3"

# ====== BOTÕES ======
def btn_criar_conta():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Criar conta agora", url=LINK_CADASTRO)]])
def btn_sim():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ SIM", callback_data=CB_CONFIRM_SIM)]])
def btn_acessar_comunidade():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Acessar comunidade", url=LINK_COMUNIDADE_FINAL)]])

# ====== RETRY ======
async def _retry_send(coro_factory, max_attempts=2):
    last = None
    for _ in range(max_attempts):
        try:
            return await coro_factory()
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "retry_after", 1)); last = e
        except TimedOut:
            await asyncio.sleep(1)
        except Exception as e:
            last = e; break
    if last: raise last

# ====== FOTO ======
async def send_photo_from_url(context, chat_id, file_id_key, url, caption=None, reply_markup=None):
    fid = FILE_IDS.get(file_id_key)
    try:
        if fid:
            log.info("Foto via file_id cache (%s)", file_id_key)
            return await _retry_send(lambda: context.bot.send_photo(chat_id=chat_id, photo=fid, caption=caption, parse_mode="Markdown", reply_markup=reply_markup))
        log.info("Foto via URL (%s)", file_id_key)
        msg = await _retry_send(lambda: context.bot.send_photo(chat_id=chat_id, photo=url, caption=caption, parse_mode="Markdown", reply_markup=reply_markup))
        if msg and msg.photo:
            FILE_IDS[file_id_key] = msg.photo[-1].file_id; save_cache(FILE_IDS)
        return msg
    except Exception as e:
        log.warning("Falha ao enviar foto (%s)", e)
        await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text=caption or "imagem não disponível", parse_mode="Markdown", reply_markup=reply_markup))

# ====== ÁUDIO ======
async def send_audio_fast(context, chat_id, caption=None):
    fid_env = os.getenv("FILE_ID_AUDIO") or ""
    if fid_env:
        log.info("Áudio via FILE_ID_AUDIO=%s...", fid_env[:8])
        try:
            return await _retry_send(lambda: context.bot.send_audio(chat_id=chat_id, audio=fid_env, caption=caption))
        except Exception as e:
            log.warning("file_id ENV falhou: %s", e)

    fid_cache = FILE_IDS.get("audio")
    if fid_cache:
        log.info("Áudio via cache=%s...", fid_cache[:8])
        try:
            return await _retry_send(lambda: context.bot.send_audio(chat_id=chat_id, audio=fid_cache, caption=caption))
        except Exception as e:
            log.warning("file_id cache falhou: %s", e)
            FILE_IDS.pop("audio", None); save_cache(FILE_IDS)

    full = os.path.join(os.path.dirname(__file__), AUDIO_FILE_LOCAL)
    if os.path.exists(full) and os.path.getsize(full) > 0:
        with open(full, "rb") as f:
            msg = await _retry_send(lambda: context.bot.send_audio(chat_id=chat_id, audio=InputFile(f, filename="Audio.mp3"), caption=caption))
        if msg and msg.audio:
            FILE_IDS["audio"] = msg.audio.file_id; save_cache(FILE_IDS)
        return msg
    log.warning("Nenhuma rota de áudio disponível.")

# ====== COMANDOS ======
async def envcheck(update, context):
    fid = os.getenv("FILE_ID_AUDIO") or ""
    await _retry_send(lambda: context.bot.send_message(chat_id=update.effective_chat.id, text=f"FILE_ID_AUDIO detectado: {fid[:12]}..."))

async def ids(update, context):
    data = {
        "FILE_ID_AUDIO": FILE_IDS.get("audio"),
        "FILE_ID_IMG_INICIAL": FILE_IDS.get("img1"),
        "FILE_ID_IMG_FINAL": FILE_IDS.get("img2"),
        "FILE_ID_VIDEO1": FILE_IDS.get("video1"),
        "FILE_ID_VIDEO2": FILE_IDS.get("video2"),
        "FILE_ID_VIDEO3": FILE_IDS.get("video3"),
    }
    txt = "file_ids salvos:\n" + "\n".join(f"{k}: {v or '-'}" for k, v in data.items())
    await _retry_send(lambda: context.bot.send_message(chat_id=update.effective_chat.id, text=txt))

async def audiotest(update, context):
    await send_audio_fast(context, update.effective_chat.id, caption="🔊 teste de áudio")

# Captura automática de AUDIO
async def capture_audio(update, context):
    msg = update.effective_message
    fid = msg.audio.file_id if msg.audio else (msg.voice.file_id if msg.voice else None)
    if not fid: return
    FILE_IDS["audio"] = fid; save_cache(FILE_IDS)
    await _retry_send(lambda: context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎧 Áudio salvo!\nFILE_ID_AUDIO=\n{fid}"))
    log.info("Audio file_id salvo: %s", fid)

# ====== Captura automática de VÍDEO (video, document.video e video_note)
async def capture_video(update, context):
    msg = update.effective_message
    vid_obj = None

    if msg.video:
        vid_obj = msg.video
    elif msg.document and (msg.document.mime_type or "").startswith("video/"):
        vid_obj = msg.document
    elif msg.video_note:
        vid_obj = msg.video_note  # vídeo redondo

    if not vid_obj:
        return

    fid = vid_obj.file_id

    # ocupa video1 -> video2 -> video3
    for key in ("video1", "video2", "video3"):
        if not FILE_IDS.get(key):
            FILE_IDS[key] = fid
            save_cache(FILE_IDS)
            await _retry_send(lambda: context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🎬 Vídeo salvo em {key}!\nFILE_ID=\n{fid}"
            ))
            break
    else:
        await _retry_send(lambda: context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎬 Recebi um vídeo.\nFILE_ID=\n{fid}"
        ))
    log.info("Video file_id recebido: %s", fid)

# ====== /start ======
async def start(update, context):
    chat_id = update.effective_chat.id
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text="⏳ Preparando seu presente…"))
    await send_audio_fast(context, chat_id, caption="🔊 Mensagem rápida antes de continuar")
    caption = "🎁 *Presente da Marluce aguardando…*\n\nClique no botão abaixo para abrir sua conta e garantir seu presente."
    await send_photo_from_url(context, chat_id, "img1", IMG1_URL, caption, btn_criar_conta())
    schedule_followup(context, chat_id, WAIT_SECONDS)

# ====== FOLLOW-UP ======
def schedule_followup(context, chat_id, wait_seconds):
    if chat_id in PENDING_FOLLOWUPS: return
    PENDING_FOLLOWUPS.add(chat_id)
    jq = context.application.job_queue
    jq.run_once(send_followup_job, when=wait_seconds, data={"chat_id": chat_id})
async def send_followup_job(context):
    chat_id = context.job.data["chat_id"]
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text="Eae, já conseguiu finalizar a criação da sua conta?", reply_markup=btn_sim()))
    PENDING_FOLLOWUPS.discard(chat_id)

# ====== Clique no SIM ======
async def confirm_sim(update, context):
    q = update.callback_query; await q.answer()
    chat_id = q.message.chat_id
    texto_final = (
        "🎁 *Presente Liberado!!!*\n\n"
        "Basta você entrar na comunidade e buscar o sorteio que já vou te enviar,\n"
        "e fica de olho que o resultado sai na live de *HOJE*."
    )
    await send_photo_from_url(context, chat_id, "img2", IMG2_URL, texto_final, btn_acessar_comunidade())

# ====== MAIN ======
async def on_error(update, context):
    log.exception("Unhandled error: %s | update=%s", context.error, update)

def main():
    request = HTTPXRequest(
        read_timeout=20.0,
        write_timeout=20.0,
        connect_timeout=10.0,
        pool_timeout=10.0,
    )
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .request(request)
        .job_queue(JobQueue())
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audiotest", audiotest))
    app.add_handler(CommandHandler("envcheck", envcheck))
    app.add_handler(CommandHandler("ids", ids))

    # Áudio/voz
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, capture_audio))

    # ✅ Captura VÍDEO enviado como vídeo normal, documento de vídeo e video_note (bolinha)
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.VIDEO | filters.VIDEO_NOTE,
            capture_video,
        )
    )

    # Botão "SIM"
    app.add_handler(CallbackQueryHandler(confirm_sim, pattern=f"^{CB_CONFIRM_SIM}$"))

    app.add_error_handler(on_error)
    log.info("🤖 Bot rodando. FILE_ID de vídeos será capturado automaticamente.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
