
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

# ======== CONSTS ========
CB_CONFIRM_SIM = "confirm_sim"
WAIT_SECONDS = 120
PENDING_FOLLOWUPS: set[int] = set()
AUDIO_FILE_LOCAL = "Audio.mp3"

# ==== VIP / callbacks ====
CB_ACESSAR_VIP   = "vip_go"
CB_VIP_GARANTIR  = "vip_garantir"
CB_VIP_EXPLICAR  = "vip_explicar"
CB_VIP_PRINT     = "vip_print"
CB_VIP_DEPOSITAR = "vip_depositar"

VIP_WAIT_SECONDS = 7 * 60
VIP_PENDING_PRINT: set[int] = set()

# ====== BOTÕES ======
def btn_criar_conta():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Criar conta agora", url=LINK_CADASTRO)]])
def btn_sim():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ SIM", callback_data=CB_CONFIRM_SIM)]])
def btn_acessar_comunidade():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Acessar comunidade", url=LINK_COMUNIDADE_FINAL)]])
def btn_acessar_vip():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🟣 Acessar VIP", callback_data=CB_ACESSAR_VIP)]])
def btn_vip_primeira_escolha():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Quero Garantir", callback_data=CB_VIP_GARANTIR)],
        [InlineKeyboardButton("ℹ️ Me explica antes", callback_data=CB_VIP_EXPLICAR)],
    ])
def btn_vip_print_deposito():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼️ PRINT = LIBERAR VIP", callback_data=CB_VIP_PRINT)],
        [InlineKeyboardButton("💳 FAZER DEPÓSITO", callback_data=CB_VIP_DEPOSITAR)],
    ])

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
            return await _retry_send(lambda: context.bot.send_photo(chat_id=chat_id, photo=fid, caption=caption, parse_mode="Markdown", reply_markup=reply_markup))
        msg = await _retry_send(lambda: context.bot.send_photo(chat_id=chat_id, photo=url, caption=caption, parse_mode="Markdown", reply_markup=reply_markup))
        if msg and msg.photo:
            FILE_IDS[file_id_key] = msg.photo[-1].file_id; save_cache(FILE_IDS)
        return msg
    except Exception as e:
        log.warning("Falha ao enviar foto (%s)", e)
        await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text=caption or "imagem não disponível", parse_mode="Markdown", reply_markup=reply_markup))

# ====== ÁUDIO ======
async def send_audio_fast(context, chat_id, caption=None, var_name="FILE_ID_AUDIO"):
    fid_env = os.getenv(var_name) or ""
    if fid_env:
        try:
            return await _retry_send(lambda: context.bot.send_audio(chat_id=chat_id, audio=fid_env, caption=caption))
        except Exception as e:
            log.warning("%s falhou: %s", var_name, e)
    fid_cache = FILE_IDS.get("audio")
    if fid_cache:
        try:
            return await _retry_send(lambda: context.bot.send_audio(chat_id=chat_id, audio=fid_cache, caption=caption))
        except Exception as e:
            FILE_IDS.pop("audio", None); save_cache(FILE_IDS)
    full = os.path.join(os.path.dirname(__file__), AUDIO_FILE_LOCAL)
    if os.path.exists(full) and os.path.getsize(full) > 0:
        with open(full, "rb") as f:
            msg = await _retry_send(lambda: context.bot.send_audio(chat_id=chat_id, audio=InputFile(f, filename="Audio.mp3"), caption=caption))
        if msg and msg.audio:
            FILE_IDS["audio"] = msg.audio.file_id; save_cache(FILE_IDS)
        return msg

# ====== VÍDEOS (env/cache) ======
async def send_video_by_slot(context, chat_id, slot: str):
    idx = slot.replace("video", "")
    for name in [f"FILE_ID_VIDEO{idx}", f"FILE_ID_VIDEO0{idx}"]:
        fid_env = os.getenv(name) or ""
        if fid_env:
            try:
                return await _retry_send(lambda: context.bot.send_video(chat_id=chat_id, video=fid_env))
            except Exception as e:
                log.warning("%s falhou: %s", name, e)
    fid_cache = FILE_IDS.get(slot)
    if fid_cache:
        try:
            return await _retry_send(lambda: context.bot.send_video(chat_id=chat_id, video=fid_cache))
        except Exception as e:
            FILE_IDS.pop(slot, None); save_cache(FILE_IDS)

# ====== CAPTURA ======
async def capture_audio(update, context):
    msg = update.effective_message
    fid = msg.audio.file_id if msg.audio else (msg.voice.file_id if msg.voice else None)
    if not fid: return
    FILE_IDS["audio"] = fid; save_cache(FILE_IDS)
    await _retry_send(lambda: context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎧 Áudio salvo!\nFILE_ID_AUDIO=\n{fid}"))

async def capture_video(update, context):
    msg = update.effective_message
    vid = msg.video or (msg.document if msg.document and (msg.document.mime_type or '').startswith('video/') else None) or msg.video_note
    if not vid: return
    fid = vid.file_id
    for key in ("video1","video2","video3"):
        if not FILE_IDS.get(key):
            FILE_IDS[key] = fid; save_cache(FILE_IDS)
            await _retry_send(lambda: context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎬 Vídeo salvo em {key}!\nFILE_ID=\n{fid}"))
            break
    else:
        await _retry_send(lambda: context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎬 Recebi um vídeo.\nFILE_ID=\n{fid}"))

# ====== VIP ======
def schedule_vip_followup(context, chat_id):
    for job in context.application.job_queue.get_jobs_by_name(f"vip:{chat_id}"):
        return
    context.application.job_queue.run_once(vip_followup_job, when=VIP_WAIT_SECONDS, data={"chat_id": chat_id}, name=f"vip:{chat_id}")

async def vip_followup_job(context):
    chat_id = context.job.data["chat_id"]
    if chat_id not in VIP_PENDING_PRINT: return
    txt = ("Eii, tá por aí? Não sei se você esqueceu, mas são pelo menos *R$500* sorteados para 10 pessoas + 1 chance na *roleta* que pode te dar até um *IPHONE 17 PRO HOJE!*\n\n_Tem poucas pessoas, concorrendo…_\n\nVai abandonar mesmo sua chance de entrar no VIP?")
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text=txt, parse_mode="Markdown", reply_markup=btn_vip_print_deposito()))

async def ask_vip_print(context, chat_id):
    VIP_PENDING_PRINT.add(chat_id)
    txt = ("Todas essas pessoas fizeram parte e *ganharam um prêmio muito bom*, escolheram jogar comigo em um grupo com *mais acesso*!\n\n"
           "Vou estar aguardando um *print da sua conta Betboom* (Mostrando *detalhes do Depósito*) com pelo menos *R$35* depositados *hoje* e já libero seu acesso à roleta, ok?")
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text=txt, parse_mode="Markdown", reply_markup=btn_vip_print_deposito()))
    schedule_vip_followup(context, chat_id)

async def acessar_vip(update, context):
    q = update.callback_query; await q.answer()
    chat_id = q.message.chat_id
    first = (q.from_user.first_name or "amigo")
    intro = (f"Fala {first}!\n\nJá quer garantir sua *vaga no VIP* + *Chance na roleta* ou prefere que eu te explique rapidinho como funciona?")
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text=intro, parse_mode="Markdown", reply_markup=btn_vip_primeira_escolha()))
    await send_audio_fast(context, chat_id, caption="🔊 Explicação rápida (1 min)", var_name="FILE_ID_AUDIO_VIP")
    await send_video_by_slot(context, chat_id, "video1")
    await send_video_by_slot(context, chat_id, "video2")
    await send_video_by_slot(context, chat_id, "video3")
    await ask_vip_print(context, chat_id)

async def vip_quero_garantir(update, context):
    q = update.callback_query; await q.answer()
    await ask_vip_print(context, q.message.chat_id)

async def vip_me_explica(update, context):
    q = update.callback_query; await q.answer()
    await ask_vip_print(context, q.message.chat_id)

async def vip_btn_print(update, context):
    q = update.callback_query; await q.answer()
    await _retry_send(lambda: context.bot.send_message(chat_id=q.message.chat_id, text="Perfeito! Me envie **agora** o *print do depósito* para liberar o VIP. 📸", parse_mode="Markdown"))

async def vip_btn_depositar(update, context):
    q = update.callback_query; await q.answer()
    await _retry_send(lambda: context.bot.send_message(chat_id=q.message.chat_id, text="Assim que fizer o depósito, me envie o *print* para eu liberar seu VIP. 👍", parse_mode="Markdown"))

# ====== /start ======
async def start(update, context):
    chat_id = update.effective_chat.id
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text="⏳ Preparando seu presente…"))
    await send_audio_fast(context, chat_id, caption="🔊 Mensagem rápida antes de continuar", var_name="FILE_ID_AUDIO")
    caption = "🎁 *Presente da Marluce aguardando…*\n\nClique no botão abaixo para abrir sua conta e garantir seu presente."
    await send_photo_from_url(context, chat_id, "img1", IMG1_URL, caption, btn_criar_conta())
    # follow-up de 120s
    context.application.job_queue.run_once(send_followup_job, when=WAIT_SECONDS, data={"chat_id": chat_id})

async def send_followup_job(context):
    chat_id = context.job.data["chat_id"]
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text="Eae, já conseguiu finalizar a criação da sua conta?", reply_markup=btn_sim()))

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
    # botão para abrir o funil VIP
    await _retry_send(lambda: context.bot.send_message(chat_id=chat_id, text="Quer já garantir sua vaga no *VIP*?", parse_mode="Markdown", reply_markup=btn_acessar_vip()))

# ====== MAIN ======
async def on_error(update, context):
    log.exception("Unhandled error: %s | update=%s", context.error, update)

def main():
    request = HTTPXRequest(read_timeout=20.0, write_timeout=20.0, connect_timeout=10.0, pool_timeout=10.0)
    app = ApplicationBuilder().token(TOKEN).request(request).job_queue(JobQueue()).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))

    # Capturas de mídia
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, capture_audio))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO | filters.VIDEO_NOTE, capture_video))

    # Callbacks
    app.add_handler(CallbackQueryHandler(confirm_sim, pattern=f"^{CB_CONFIRM_SIM}$"))
    app.add_handler(CallbackQueryHandler(acessar_vip, pattern=f"^{CB_ACESSAR_VIP}$"))
    app.add_handler(CallbackQueryHandler(vip_quero_garantir, pattern=f"^{CB_VIP_GARANTIR}$"))
    app.add_handler(CallbackQueryHandler(vip_me_explica, pattern=f"^{CB_VIP_EXPLICAR}$"))
    app.add_handler(CallbackQueryHandler(vip_btn_print, pattern=f"^{CB_VIP_PRINT}$"))
    app.add_handler(CallbackQueryHandler(vip_btn_depositar, pattern=f"^{CB_VIP_DEPOSITAR}$"))

    app.add_error_handler(on_error)
    log.info("🤖 Bot rodando. VIP habilitado; aguardando prints após os botões.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
