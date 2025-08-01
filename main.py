import os
import discord
import requests
from openai import OpenAI
from telegram import Bot

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

    # 🧠 Summarize text messages
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

    # 🧠 Summarize image attachments
    for file in files:
        if file.content_type and "image" in file.content_type:
            try:
                print(f"🖼️ Image found: {file.url}")
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "You're a trading assistant. Summarize any trading chart image, explaining key levels, patterns, and potential setups."
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": file.url,
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ]
                )
                summary = response.choices[0].message.content
                await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
                print("✅ Image summary sent to Telegram.")
            except Exception as e:
                print(f"⚠️ Image processing error: {e}")

client.run(DISCORD_TOKEN)
