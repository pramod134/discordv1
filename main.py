import os
import discord
import requests
from openai import OpenAI
from telegram import Bot
from io import BytesIO

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.strip()
    files = message.attachments

    # 🧠 Process text
    if content:
        try:
            print(f"📨 Text received: {content[:60]}")
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Summarize this trading alert in simple terms, highlighting key levels and directional bias."},
                    {"role": "user", "content": content}
                ]
            )
            summary = response.choices[0].message.content
            await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
            print("✅ Text summary sent to Telegram.")
        except Exception as e:
            print(f"⚠️ Text summarization error: {e}")

    # 🧠 Process image
    for file in files:
        if file.content_type and "image" in file.content_type:
            try:
                print(f"🖼️ Image found: {file.url}")
                img_data = requests.get(file.url).content
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Analyze this image. If it’s a trading chart, summarize the trade idea, chart patterns, and bias."},
                        {"role": "user", "content": "Here's the chart image."}
                    ],
                    files={"image": BytesIO(img_data)}
                )
                summary = response.choices[0].message.content
                await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
                print("✅ Image summary sent to Telegram.")
            except Exception as e:
                print(f"⚠️ Image processing error: {e}")

client.run(DISCORD_TOKEN)