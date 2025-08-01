import os
import sys
import asyncio
import json
import traceback
from typing import Optional
import discord
from openai import OpenAI
from telegram import Bot

# ---------- Logging helpers ----------
def log(*args):
    print(*args, flush=True)

def log_exc(prefix: str, e: Exception):
    log(f"⚠️ {prefix}: {e}\n{traceback.format_exc()}")

# ---------- Env ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID_RAW = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

missing = [name for name, val in [
    ("DISCORD_TOKEN", DISCORD_TOKEN),
    ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
    ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID_RAW),
    ("OPENAI_API_KEY", OPENAI_API_KEY),
] if not val]
if missing:
    log(f"❌ Missing required env vars: {', '.join(missing)}")
    sys.exit(1)

try:
    TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID_RAW)
except Exception:
    log(f"❌ TELEGRAM_CHAT_ID must be an integer; got: {TELEGRAM_CHAT_ID_RAW}")
    sys.exit(1)

# ---------- Clients ----------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # also enable in Discord Dev Portal

client = discord.Client(intents=intents)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)  # v13 sync API

# ---------- Prompts ----------
TEXT_SYSTEM_PROMPT = (
    "You are a trading assistant. Extract structured trade intel from text messages. "
    "Focus on: ticker, entry price/zone, stop-loss (SL), take-profit (TP), exit conditions "
    "(e.g., 'if candle closes below X'), directional bias (bullish/bearish/neutral), "
    "key support/resistance levels or breakout/breakdown zones, and short rationale. "
    "If specific values are missing, infer reasonable SL/TP based on context and say they are suggested.\n\n"
    "Output ONLY valid JSON with keys: "
    "{'ticker': str|null, 'entry': str|null, 'stop_loss': str|null, 'take_profit': str|null, "
    "'exit_conditions': str|null, 'bias': str|null, 'levels': str|null, 'rationale': str|null, "
    "'confidence': number (0-1)}"
)

IMAGE_SYSTEM_PROMPT = (
    "You are a trading assistant analyzing a trading chart image. Identify ticker if visible, "
    "trend, key support/resistance, patterns (flags, wedges, H&S), levels/zones, and a likely setup. "
    "If explicit Entry/SL/TP are annotated, extract them. If not, suggest reasonable values "
    "based on the chart (mention they are suggested). Be specific (use numbers when visible).\n\n"
    "Output ONLY valid JSON with keys: "
    "{'ticker': str|null, 'entry': str|null, 'stop_loss': str|null, 'take_profit': str|null, "
    "'exit_conditions': str|null, 'bias': str|null, 'levels': str|null, 'rationale': str|null, "
    "'confidence': number (0-1)}"
)

# ---------- Helpers ----------
def format_trade_summary(obj: dict) -> str:
    def _g(k):
        v = obj.get(k)
        return v if (v is not None and str(v).strip() != "") else "—"
    lines = []
    lines.append("📈 Trade Idea Summary")
    lines.append(f"• Ticker: {_g('ticker')}")
    lines.append(f"• Bias: {_g('bias')}  |  Confidence: {round(float(obj.get('confidence', 0))*100)}%")
    lines.append(f"• Entry: {_g('entry')}")
    lines.append(f"• SL: {_g('stop_loss')}  |  TP: {_g('take_profit')}")
    lines.append(f"• Exit cond.: {_g('exit_conditions')}")
    if obj.get("levels"):
        lines.append(f"• Levels: {_g('levels')}")
    if obj.get("rationale"):
        lines.append(f"• Notes: {_g('rationale')}")
    return "\n".join(lines)

async def send_telegram(text: str):
    """python-telegram-bot v13 sync -> run in a thread to avoid blocking."""
    try:
        MAX_LEN = 4000
        chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [text]
        for chunk in chunks:
            await asyncio.to_thread(
                telegram_bot.send_message,
                chat_id=TELEGRAM_CHAT_ID,
                text=chunk
            )
        log("✅ Sent message to Telegram.")
    except Exception as e:
        log_exc("Telegram send error", e)

async def openai_json_completion(messages):
    """Call OpenAI with JSON mode and basic exponential backoff."""
    delay = 1
    for attempt in range(5):
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                temperature=0.2,
                messages=messages,
            )
            raw = (resp.choices[0].message.content or "").strip().strip("`").strip()
            return json.loads(raw)
        except Exception as e:
            if attempt == 4:
                raise
            log(f"⏳ OpenAI retry {attempt+1}: {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 8)

async def extract_text_from_message(message: discord.Message) -> str:
    """
    Extract useful text when .content is empty (forwards/embeds/replies).
    Checks:
      1) message.content
      2) message.embeds (title, description, fields, footer)
      3) referenced/original message (if it's a reply)
    """
    parts = []

    if message.content and message.content.strip():
        parts.append(message.content.strip())

    for emb in message.embeds or []:
        try:
            if getattr(emb, "title", None):
                parts.append(str(emb.title))
            if getattr(emb, "description", None):
                parts.append(str(emb.description))
            for f in getattr(emb, "fields", []) or []:
                name = f.name if f.name else ""
                value = f.value if f.value else ""
                field_text = f"{name}: {value}".strip(": ").strip()
                if field_text:
                    parts.append(field_text)
            if getattr(emb, "footer", None) and getattr(emb.footer, "text", None):
                parts.append(str(emb.footer.text))
        except Exception:
            pass

    if message.reference and message.reference.message_id:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg and ref_msg.content and ref_msg.content.strip():
                parts.append(ref_msg.content.strip())
            for emb in ref_msg.embeds or []:
                if getattr(emb, "title", None):
                    parts.append(str(emb.title))
                if getattr(emb, "description", None):
                    parts.append(str(emb.description))
                for f in getattr(emb, "fields", []) or []:
                    name = f.name if f.name else ""
                    value = f.value if f.value else ""
                    field_text = f"{name}: {value}".strip(": ").strip()
                    if field_text:
                        parts.append(field_text)
        except Exception:
            pass

    text = "\n".join([p for p in parts if p]).strip()
    return text

# ---------- Discord events ----------
@client.event
async def on_ready():
    log(f"✅ Logged in as {client.user} (intents.message_content={intents.message_content})")
    try:
        await send_telegram("🤖 Bot started on Railway. If you see this, Telegram path is OK.")
    except Exception as e:
        log_exc("Startup Telegram test failed", e)

    async def heartbeat():
        while True:
            log("💓 Heartbeat: bot alive")
            await asyncio.sleep(30)
    asyncio.create_task(heartbeat())

@client.event
async def on_error(event_method, *args, **kwargs):
    log(f"❗ on_error in {event_method}")
    log(traceback.format_exc())

@client.event
async def on_message(message: discord.Message):
    try:
        if message.author == client.user or (hasattr(message.author, "bot") and message.author.bot):
            return

        log(f"👂 on_message: guild={getattr(message.guild, 'name', 'DM')} | "
            f"channel={getattr(message.channel, 'name', 'DM')} | "
            f"user={message.author} | has_content={bool(message.content)} | "
            f"attachments={len(message.attachments)} | embeds={len(message.embeds)} | is_reply={bool(message.reference)}")

        # Extract text from content/embeds/replies
        content = (await extract_text_from_message(message))[:6000]

        image_attachments = [
            a for a in message.attachments
            if (a.content_type and "image" in a.content_type.lower())
               or a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]

        # Health checks
        if (message.content or "").strip().lower() in ("/ping", "!ping"):
            await message.channel.send("pong 🏓")
            return
        if (message.content or "").strip().lower() in ("/status", "!status"):
            await message.channel.send("✅ Online. Telegram OK. Listening for text & image messages.")
            return

        # ---- TEXT ----
        if content:
            try:
                messages = [
                    {"role": "system", "content": TEXT_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ]
                obj = await openai_json_completion(messages)
                summary = format_trade_summary(obj)
                emptyish = sum(1 for k in ["ticker","entry","stop_loss","take_profit","bias"] if not obj.get(k))
                payload = summary if emptyish < 3 else f"{summary}\n\n—\nJSON:\n{json.dumps(obj, indent=2)}"
                await send_telegram(payload)
            except Exception as e:
                log_exc("Text summarization error", e)
        else:
            log("ℹ️ No textual content extracted (content empty, no usable embeds/references).")

        # ---- IMAGES ----
        for a in image_attachments:
            try:
                log(f"🖼️ Image URL: {a.url}")
                messages = [
                    {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": a.url, "detail": "high"}},
                            {"type": "text", "text": content[:2000]} if content else {"type": "text", "text": ""}
                        ]
                    }
                ]
                obj = await openai_json_completion(messages)
                summary = format_trade_summary(obj)
                emptyish = sum(1 for k in ["ticker","entry","stop_loss","take_profit","bias"] if not obj.get(k))
                payload = summary if emptyish < 3 else f"{summary}\n\n—\nJSON:\n{json.dumps(obj, indent=2)}"
                await send_telegram(payload)
            except Exception as e:
                log_exc("Image processing error", e)

    except Exception as e:
        log_exc("on_message outer error", e)

# ---------- Main ----------
if __name__ == "__main__":
    log("🚀 Starting bot...")
    try:
        client.run(DISCORD_TOKEN, log_handler=None)  # use our own prints for logging
    except Exception as e:
        log_exc("Discord client.run failed", e)
        sys.exit(1)
