import os, json, asyncio, logging
from dotenv import load_dotenv
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, User
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue, MessageHandler, filters, ChatJoinRequestHandler  # <-- ADICIONADO ChatJoinRequestHandler
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
    "https://click.betboom.com/BdnxJncs?landing=2833&sub_id1=Telegram"
)
LINK_COMUNIDADE_FINAL = "https://t.me/+rtq84bGVBhQyZmJh"

# Mídias
IMG1_URL = "https://i.postimg.cc/wxkkz20M/presente-do-jota.jpg"
IMG2_URL = "https://i.postimg.cc/8kbbG4tT/presente-do-jota-2.png"

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
            return await _retry_send(lambda: context.bot.send_photo(
                chat_id=chat_id,
                photo=fid,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup
            ))
        log.info("Foto via URL (%s)", file_id_key)
        msg = await _retry_send(lambda: context.bot.send_photo(
            chat_id=chat_id,
            photo=url,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        ))
        if msg and msg.photo:
            FILE_IDS[file_id_key] = msg.photo[-1].file_id; save_cache(FILE_IDS)
        return msg
    except Exception as e:
        log.warning("Falha ao enviar foto (%s)", e)
        await _retry_send(lambda: context.bot.send_message(
            chat_id=chat_id,
            text=caption or "imagem não disponível",
            parse_mode="Markdown",
            reply_markup=reply_markup
        ))

# ====== ÁUDIO ======
async def send_audio_fast(context, chat_id, caption=None):
    fid_env = os.getenv("FILE_ID_AUDIO") or ""
    if fid_env:
        log.info("Áudio via FILE_ID_AUDIO=%s...", fid_env[:8])
        try:
            return await _retry_send(lambda: context.bot.send_audio(
                chat_id=chat_id,
                audio=fid_env,
                caption=caption
            ))
        except Exception as e:
            log.warning("file_id ENV falhou: %s", e)

    fid_cache = FILE_IDS.get("audio")
    if fid_cache:
        log.info("Áudio via cache=%s...", fid_cache[:8])
        try:
            return await _retry_send(lambda: context.bot.send_audio(
                chat_id=chat_id,
                audio=fid_cache,
                caption=caption
            ))
        except Exception as e:
            log.warning("file_id cache falhou: %s", e)
            FILE_IDS.pop("audio", None); save_cache(FILE_IDS)

    full = os.path.join(os.path.dirname(__file__), AUDIO_FILE_LOCAL)
    if os.path.exists(full) and os.path.getsize(full) > 0:
        with open(full, "rb") as f:
            msg = await _retry_send(lambda: context.bot.send_audio(
                chat_id=chat_id,
                audio=InputFile(f, filename="Audio.mp3"),
                caption=caption
            ))
        if msg and msg.audio:
            FILE_IDS["audio"] = msg.audio.file_id; save_cache(FILE_IDS)
        return msg
    log.warning("Nenhuma rota de áudio disponível.")

# ====== HELPERS ======
def format_user_name(user: Optional[User]) -> str:
    if not user:
        return ""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.first_name or user.username or ""

# ====== COMANDOS AUXILIARES ======
async def envcheck(update, context):
    fid = os.getenv("FILE_ID_AUDIO") or ""
    await _retry_send(lambda: context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"FILE_ID_AUDIO detectado: {fid[:12]}..."
    ))

async def ids(update, context):
    data = {
        "FILE_ID_AUDIO": FILE_IDS.get("audio"),
        "FILE_ID_IMG_INICIAL": FILE_IDS.get("img1"),
        "FILE_ID_IMG_FINAL": FILE_IDS.get("img2")
    }
    txt = "file_ids salvos:\n" + "\n".join(f"{k}: {v or '-'}" for k, v in data.items())
    await _retry_send(lambda: context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=txt
    ))

async def audiotest(update, context):
    await send_audio_fast(context, update.effective_chat.id, caption="🔊 teste de áudio")

# Captura automática
async def capture_audio(update, context):
    msg = update.effective_message
    fid = msg.audio.file_id if msg.audio else (msg.voice.file_id if msg.voice else None)
    if not fid: return
    FILE_IDS["audio"] = fid; save_cache(FILE_IDS)
    await _retry_send(lambda: context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🎧 Áudio salvo!\nFILE_ID_AUDIO=\n{fid}"
    ))
    log.info("Audio file_id salvo: %s", fid)

# ====== FLUXO INICIAL (FUNIL) ======
async def run_start_flow(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: Optional[User] = None):
    """
    Funil completo:
    - Saudação personalizada
    - Áudio rápido
    - Imagem de presente + botão de cadastro
    - Agenda follow-up com botão "SIM"
    """
    nome = format_user_name(user)
    saudacao = f"Falaaa {nome}, tá por aí? 👋" if nome else "Falaaa jogador, tá por aí? 👋"

    texto_abertura = (
        f"{saudacao}\n\n"
        "Agora você está na *TROPA DO JOTA* 🏆\n\n"
        "Aqui é melhor que programa do Silvio Santos, você sempre ganha 💰\n\n"
        "Milhares de pessoas já ganharam nas minhas lives, só falta você agora.\n\n"
        "SÃO R$500 A R$1.000 TODOS OS DIAS PRA VOCÊS 🎁\n\n"
        "Vou te mandar um áudio rápido e em seguida o botão pra você garantir sua vaga pro próximo prêmio 👇"
    )

    await _retry_send(lambda: context.bot.send_message(
        chat_id=chat_id,
        text=texto_abertura,
        parse_mode="Markdown"
    ))

    # Áudio
    await send_audio_fast(
        context,
        chat_id,
        caption="🔊 Ouve esse áudio que eu te explico como funciona o presente de hoje."
    )

    # Imagem com botão de cadastro
    caption = (
        "🎁 *Você acaba de ganhar um presente da live!*\n\n"
        "Clique no botão abaixo para abrir sua conta e garantir sua vaga pro próximo prêmio 👇"
    )
    await send_photo_from_url(
        context,
        chat_id,
        "img1",
        IMG1_URL,
        caption,
        btn_criar_conta()
    )

    # Agenda follow-up perguntando se já criou a conta
    schedule_followup(context, chat_id, WAIT_SECONDS)

# ====== /start (continua funcionando, ex: se usuário te chamar direto no PV) ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    await run_start_flow(context, chat_id, user)

# ====== FOLLOW-UP ======
def schedule_followup(context, chat_id, wait_seconds):
    if chat_id in PENDING_FOLLOWUPS:
        return
    PENDING_FOLLOWUPS.add(chat_id)
    jq = context.application.job_queue
    jq.run_once(send_followup_job, when=wait_seconds, data={"chat_id": chat_id})

async def send_followup_job(context):
    chat_id = context.job.data["chat_id"]
    await _retry_send(lambda: context.bot.send_message(
        chat_id=chat_id,
        text="Eae, já conseguiu finalizar a criação da sua conta? 👇",
        reply_markup=btn_sim()
    ))
    PENDING_FOLLOWUPS.discard(chat_id)

# ====== Clique no SIM ======
async def confirm_sim(update, context):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    texto_final = (
        "🎁 *Presente Liberado!!!*\n\n"
        "Agora é só entrar na comunidade e buscar o sorteio que eu já vou te enviar.\n\n"
        "Fica de olho que o resultado sai na live de *HOJE* 🔥"
    )
    await send_photo_from_url(
        context,
        chat_id,
        "img2",
        IMG2_URL,
        texto_final,
        btn_acessar_comunidade()
    )

# ====== QUANDO CLICA EM "REQUEST TO JOIN" ======
async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Disparado quando alguém aperta em 'Request to Join' no grupo/canal.
    Aqui a gente:
    - Pega o user_chat_id (chat privado com o usuário)
    - Roda o funil no PV com nome da pessoa
    - (Opcional) aprova automaticamente a entrada no grupo
    """
    req = update.chat_join_request
    if not req:
        return

    user = req.from_user
    user_chat_id = req.user_chat_id  # chat privado com o usuário

    log.info("Novo pedido de entrada: user=%s chat=%s", user.id, req.chat.id)

    if not user_chat_id:
        log.warning("Join request SEM user_chat_id para user=%s", user.id)
        return

    # Envia funil completo no privado
    try:
        await run_start_flow(context, user_chat_id, user)
    except Exception as e:
        log.error("Erro ao enviar funil para user %s: %s", user.id, e)

    # Aprova automaticamente o pedido (se quiser deixar manual, comenta esse bloco)
    try:
        await req.approve()
        log.info("Pedido aprovado para user=%s", user.id)
    except Exception as e:
        log.warning("Erro ao aprovar pedido de entrada (user=%s): %s", user.id, e)

# ====== MAIN / ERROR ======
async def on_error(update, context):
    log.exception("Unhandled error: %s | update=%s", context.error, update)

def main():
    request = HTTPXRequest(
        read_timeout=20.0,
        write_timeout=20.0,
        connect_timeout=10.0,
        pool_timeout=10.0
    )
    app = ApplicationBuilder().token(TOKEN).request(request).job_queue(JobQueue()).build()

    # Quando alguém clica em "Request to Join"
    app.add_handler(ChatJoinRequestHandler(on_join_request))

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audiotest", audiotest))
    app.add_handler(CommandHandler("envcheck", envcheck))
    app.add_handler(CommandHandler("ids", ids))

    # Captura de áudio (pra salvar file_id)
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, capture_audio))

    # Botão "SIM"
    app.add_handler(CallbackQueryHandler(confirm_sim, pattern=f"^{CB_CONFIRM_SIM}$"))

    app.add_error_handler(on_error)
    log.info("🤖 Bot rodando. JoinRequest + funil no privado ativo.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
