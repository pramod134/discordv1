import os
import sys
import asyncio
import json
import time
import traceback
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

# Validate env presence (without printing secrets)
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
    # Allow channel IDs like -100123... (still int), but if this fails, bail early
    log(f"❌ TELEGRAM_CHAT_ID must be an integer; got: {TELEGRAM_CHAT_ID_RAW}")
    sys.exit(1)

# ---------- Clients ----------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # requires toggle in Discord Portal

client = discord.Client(intents=intents)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ---------- Prompts ----------
TEXT_SYSTEM_PROMPT = (
    "You are a trading assistant. Extract structured trade intel from text messages. "
    "Output ONLY JSON with keys: "
    "{'ticker': str|null, 'entry': str|null, 'stop_loss': str|null, 'take_profit': str|null, "
    "'exit_conditions': str|null, 'bias': str|null, 'levels': str|null, 'rationale': str|null, "
    "'confidence': number (0-1)}"
)

IMAGE_SYSTEM_PROMPT = (
    "You are a trading assistant analyzing a trading chart image. "
    "Output ONLY JSON with keys: "
    "{'ticker': str|null, 'entry': str|null, 'stop_loss': str|null, 'take_profit': str|null, "
    "'exit_conditions': str|null, 'bias': str|null, 'levels': str|null, 'rationale': str|null, "
    "'confidence': number (0-1)}"
)

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
    try:
        # Telegram methods are coroutines in PTB v20+, can be awaited directly.
        # Split long messages
        MAX_LEN = 4000
        if len(text) <= MAX_LEN:
            await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        else:
            for i in range(0, len(text), MAX_LEN):
                await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text[i:i+MAX_LEN])
        log("✅ Sent message to Telegram.")
    except Exception as e:
        log_exc("Telegram send error", e)

async def openai_json_completion(messages):
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

# ---------- Discord events ----------
@client.event
async def on_ready():
    log(f"✅ Logged in as {client.user} (intents.message_content={intents.message_content})")

    # Startup self-tests
    try:
        await send_telegram("🤖 Bot started on Railway. If you see this, Telegram path is OK.")
    except Exception as e:
        log_exc("Startup Telegram test failed", e)

    # Heartbeat task
    async def heartbeat():
        while True:
            log("💓 Heartbeat: bot alive")
            await asyncio.sleep(30)
    asyncio.create_task(heartbeat())

@client.event
async def on_error(event_method, *args, **kwargs):
    # Catch unhandled exceptions in event handlers
    log(f"❗ on_error in {event_method}")
    log(traceback.format_exc())

@client.event
async def on_message(message: discord.Message):
    try:
        if message.author == client.user or (hasattr(message.author, "bot") and message.author.bot):
            return

        # Log every message hit (helps confirm Discord intent works)
        log(f"👂 on_message: guild={getattr(message.guild, 'name', 'DM')} | "
            f"channel={getattr(message.channel, 'name', 'DM')} | "
            f"user={message.author} | has_content={bool(message.content)} | "
            f"attachments={len(message.attachments)}")

        content = (message.content or "").strip()
        image_attachments = [
            a for a in message.attachments
            if (a.content_type and "image" in a.content_type.lower()) or a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]

        # TEXT
        if content:
            try:
                messages = [
                    {"role": "system", "content": TEXT_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ]
                obj = await openai_json_completion(messages)
                summary = format_trade_summary(obj)
                # Attach JSON if sparse
                emptyish = sum(1 for k in ["ticker","entry","stop_loss","take_profit","bias"] if not obj.get(k))
                payload = summary if emptyish < 3 else f"{summary}\n\n—\nJSON:\n{json.dumps(obj, indent=2)}"
                await send_telegram(payload)
            except Exception as e:
                log_exc("Text summarization error", e)

        # IMAGES
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
        client.run(DISCORD_TOKEN, log_handler=None)  # let our own prints handle logs
    except Exception as e:
        log_exc("Discord client.run failed", e)
        sys.exit(1)
