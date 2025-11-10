import os
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatJoinRequest
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatJoinRequestHandler, ContextTypes, filters
)

from db import init_db, upsert_user, set_consent, set_stage, log_event
from sequences import WELCOME_SEQUENCE
from utils import deep_link

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not TOKEN:
    raise RuntimeError("Defina TELEGRAM_TOKEN no .env")

# ===== Handlers =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []
    source = None
    if args:
        source = args[0][:100]  # startparam de origem (ex.: grp_-100123456)
    upsert_user(user.id, user.username, user.full_name, source)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Quero receber as boas‑vindas", callback_data="consent_yes")],
        [InlineKeyboardButton("Não, obrigado", callback_data="consent_no")],
    ])
    await update.message.reply_text(
        f"Olá, {user.first_name}! Posso te enviar uma sequência curta de boas‑vindas?",
        reply_markup=kb,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comandos: /start /help /stop")

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_consent(user.id, False)
    set_stage(user.id, "stopped")
    await update.message.reply_text("Ok! Parei a sequência. Para retomar, mande /start.")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispara quando alguém entra no GRUPO/SUPERGRUPO. Convida pro privado."""
    bot = context.bot
    chat = update.effective_chat
    me = await bot.get_me()
    for member in update.message.new_chat_members:
        upsert_user(member.id, member.username, member.full_name, source=f"grp_{chat.id}")
        start_link = deep_link(me.username, f"grp_{chat.id}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Começar no privado", url=start_link)]])
        await update.message.reply_text(
            f"Bem‑vindo(a), {member.first_name}! Para receber a experiência completa, toque abaixo:",
            reply_markup=kb,
        )
        log_event(member.id, "invited_to_private", str(chat.id))

async def join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aprova solicitações (Chat Join Request) e envia instruções."""
    req: ChatJoinRequest = update.chat_join_request
    me = await context.bot.get_me()

    try:
        await req.approve()
    except Exception as e:
        if ADMIN_CHAT_ID:
            await context.bot.send_message(int(ADMIN_CHAT_ID), f"Falha ao aprovar: {e}")

    upsert_user(req.from_user.id, req.from_user.username, req.from_user.full_name, source=f"cjr_{req.chat.id}")
    start_link = deep_link(me.username, f"cjr_{req.chat.id}")
    try:
        await context.bot.send_message(
            chat_id=req.from_user.id,
            text=(
                "Pedido aprovado! Para ativar suas mensagens de boas‑vindas, toque em ‘Start’ aqui: "
                f"{start_link}"
            ),
        )
    except Exception as e:
        # Caso o usuário não permita mensagens privadas antes de iniciar o bot
        if ADMIN_CHAT_ID:
            await context.bot.send_message(int(ADMIN_CHAT_ID), f"Não consegui DM {req.from_user.id}: {e}")
    log_event(req.from_user.id, "approved_join", str(req.chat.id))

async def consent_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user

    if q.data == "consent_yes":
        set_consent(user.id, True)
        set_stage(user.id, "welcome_queue")
        log_event(user.id, "consent", "yes")
        await q.edit_message_text("Perfeito! Vou te enviar algumas mensagens úteis nas próximas horas.")
        # agendar sequência
        for step in WELCOME_SEQUENCE:
            context.job_queue.run_once(send_sequence_step, when=step.delay_seconds, data={
                "telegram_id": user.id,
                "step_id": step.id,
                "text": step.text,
            })
    elif q.data == "consent_no":
        set_consent(user.id, False)
        set_stage(user.id, "no_consent")
        log_event(user.id, "consent", "no")
        await q.edit_message_text("Sem problemas! Se mudar de ideia, mande /start.")

async def send_sequence_step(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    uid = data["telegram_id"]
    text = data["text"]
    step_id = data["step_id"]
    try:
        await context.bot.send_message(chat_id=uid, text=text, disable_web_page_preview=True)
        log_event(uid, "drip_sent", step_id)
    except Exception as e:
        admin = os.getenv("ADMIN_CHAT_ID")
        if admin:
            await context.bot.send_message(int(admin), f"Erro ao enviar {step_id} para {uid}: {e}")

async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # opcional: tratamento de texto no privado
    pass

# ===== Main =====

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    app.add_handler(ChatJoinRequestHandler(join_request))
    app.add_handler(CallbackQueryHandler(consent_buttons))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    print("Bot rodando (polling). Ctrl+C para sair.")
    app.run_polling(allowed_updates=["message", "chat_join_request", "callback_query"])

if __name__ == "__main__":
    main()
