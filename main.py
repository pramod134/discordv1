import os
import discord
from discord.ext import commands
import requests
from openai import OpenAI
from telegram import Bot

# 🔐 Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 🤖 GPT + Telegram Bot setup
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tg_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ⚙️ Discord bot setup (intents to read messages + attachments)
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    try:
        content = message.content.strip()
        image_url = None

        # 🖼️ Check for image attachment
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and "image" in attachment.content_type:
                    image_url = attachment.url
                    break

        # 🎯 Determine what to send to GPT
        messages = [{"role": "system", "content": "Summarize and explain this trading alert in simple English."}]
        if content:
            messages.append({"role": "user", "content": content})
        if image_url:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze the chart and summarize trade ideas from this image."},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            })

        # 🧠 Call GPT-4o
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        gpt_reply = response.choices[0].message.content

        # 📬 Send to Telegram
        await tg_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=gpt_reply)
        print(f"✅ Sent to Telegram: {gpt_reply[:60]}...")

    except Exception as e:
        print(f"⚠️ Error processing message: {e}")

client.run(DISCORD_TOKEN)