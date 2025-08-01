import os
import discord
from openai import OpenAI
from telegram import Bot
import asyncio

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Required to read message content

client = discord.Client(intents=intents)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()
    if not content and not message.attachments:
        return

    try:
        prompt = content
        if not content and message.attachments:
            prompt = f"This is an image. Describe the trading content in this: {message.attachments[0].url}"

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Summarize or describe the trading alert in simple language."},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content
        await telegram_bot.send_message(chat_id=CHAT_ID, text=summary)
        print("📤 Sent GPT summary to Telegram.")
    except Exception as e:
        print(f"⚠️ Error: {e}")

client.run(DISCORD_TOKEN)