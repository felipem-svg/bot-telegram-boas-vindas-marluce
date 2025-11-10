from dataclasses import dataclass

@dataclass
class Step:
    id: str
    delay_seconds: int
    text: str

# Ajuste a copy conforme sua comunidade
WELCOME_SEQUENCE = [
    Step(id="welcome_0", delay_seconds=0, text=(
        "🎉 Bem‑vindo(a)! Sou o bot da comunidade.\n\n"
        "Vou te guiar pelos primeiros passos para você aproveitar tudo."
    )),
    Step(id="welcome_30m", delay_seconds=1800, text=(
        "🚀 Dica rápida: apresente-se no chat e conte seu objetivo aqui 👋"
    )),
    Step(id="welcome_24h", delay_seconds=86400, text=(
        "📚 Conteúdo recomendado inicial: Guia Rápido e Canal de Anúncios. Precisa de ajuda para configurar?"
    )),
]
