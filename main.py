import os
import asyncio
import json
import time
import discord
from openai import OpenAI
from telegram import Bot

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Discord setup ---
intents = discord.Intents.default()
intents.message_content = True  # listen to all text
intents.messages = True

client = discord.Client(intents=intents)

# --- OpenAI & Telegram ---
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --------- PROMPTS ---------
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

# --------- UTILITIES ---------
def format_trade_summary(obj: dict) -> str:
    """Turn our JSON into a clean Telegram message."""
    def _g(k): 
        v = obj.get(k)
        return v if (v is not None and str(v).strip() != "") else "—"

    lines = []
    lines.append("📈 **Trade Idea Summary**")
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
    # Telegram Bot API is async in v20+, so awaiting is correct.
    # Split if >4096 chars
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=None)
    else:
        for i in range(0, len(text), MAX_LEN):
            await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text[i:i+MAX_LEN], parse_mode=None)

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
            raw = resp.choices[0].message.content
            # Occasionally models wrap JSON in code fences—strip gracefully
            raw = raw.strip().strip("`").strip()
            return json.loads(raw)
        except Exception as e:
            if attempt == 4:
                raise
            await asyncio.sleep(delay)
            delay = min(delay * 2, 8)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (watching all channels)")

@client.event
async def on_message(message: discord.Message):
    # Ignore own msgs & other bots to avoid infinite loops / bot gossip
    if message.author == client.user or message.author.bot:
        return

    # Handle text
    content = (message.content or "").strip()
    # Collect attachments that are images
    image_attachments = [
        a for a in message.attachments
        if (a.content_type and "image" in a.content_type.lower()) or a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]

    # ---- TEXT SUMMARIZATION / EXTRACTION ----
    if content:
        try:
            print(f"📨 Text received (#{message.channel}, {message.author}): {content[:80]}...")
            messages = [
                {"role": "system", "content": TEXT_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ]
            obj = await openai_json_completion(messages)
            human_summary = format_trade_summary(obj)

            # Send to Telegram (summary + raw JSON for transparency if fields are sparse)
            payload = human_summary
            # If most fields are empty, include JSON too
            emptyish = sum(1 for k in ["ticker","entry","stop_loss","take_profit","bias"] if not obj.get(k))
            if emptyish >= 3:
                payload = f"{human_summary}\n\n—\nJSON:\n{json.dumps(obj, indent=2)}"

            await send_telegram(payload)
            print("✅ Text summary sent to Telegram.")
        except Exception as e:
            print(f"⚠️ Text summarization error: {e}")

    # ---- IMAGE SUMMARIZATION / EXTRACTION ----
    for a in image_attachments:
        try:
            print(f"🖼️ Image found: {a.url}")
            messages = [
                {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": a.url, "detail": "high"}
                        },
                        # Optional hint: pass the text too if present, helps disambiguate labels
                        {"type": "text", "text": content[:2000]} if content else {"type": "text", "text": ""}
                    ],
                },
            ]
            obj = await openai_json_completion(messages)
            human_summary = format_trade_summary(obj)

            payload = human_summary
            emptyish = sum(1 for k in ["ticker","entry","stop_loss","take_profit","bias"] if not obj.get(k))
            if emptyish >= 3:
                payload = f"{human_summary}\n\n—\nJSON:\n{json.dumps(obj, indent=2)}"

            await send_telegram(payload)
            print("✅ Image summary sent to Telegram.")
        except Exception as e:
            print(f"⚠️ Image processing error: {e}")

# Run the Discord client
client.run(DISCORD_TOKEN)
