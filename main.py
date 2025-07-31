import os
import discord
from openai import OpenAI
from telegram import Bot as TelegramBot

DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))  # e.g., 117654321987654321
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("CHAT_ID"))

openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = TelegramBot(token=TELEGRAM_BOT_TOKEN)

intents = discord.Intents.default()
intents.messages = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"🤖 Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.channel.id != DISCORD_CHANNEL_ID:
        return
    if message.author.bot:
        return

    print(f"📥 Message: {message.content[:60]}...")

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Summarize this trading message in plain English."},
                {"role": "user", "content": message.content}
            ]
        )
        summary = response.choices[0].message.content
        print(f"📤 GPT Summary: {summary[:60]}...")

        # Send via Telegram
        await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)

    except Exception as e:
        print(f"⚠️ Error: {e}")

client.run(os.getenv("DISCORD_BOT_TOKEN"))
