import os
import discord
import requests
import base64
import asyncio
from openai import OpenAI
from telegram import Bot

# Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# GPT + Telegram bot setup
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Discord Client
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)

async def summarize_trade(text: str, image_url: str = None):
    messages = [{"role": "system", "content": (
        "You're a professional trading assistant. Your job is to extract and summarize the trade idea from the provided Discord message "
        "and image/chart (if available). Focus only on what's actually in the message/image. "
        "Output a structured summary with the following fields if available or infer where possible:\n\n"
        "**Ticker**:\n**Entry**:\n**Stop Loss**:\n**Take Profit**:\n**Exit Condition**:\n\n"
        "Also include a brief explanation of the trade idea and setup. Be specific. Do NOT provide general trading advice."
    )},
    {"role": "user", "content": text}]
    
    if image_url:
        messages.append({"role": "user", "content": f"Here is the chart: {image_url}"})

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    return response.choices[0].message.content

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.strip()
    image_url = None

    # Detect attachments
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
                image_url = attachment.url
                print(f"🖼️ Image found: {image_url}")

    if not content and not image_url:
        print("⚠️ No text or image to process.")
        return

    try:
        print("📩 Processing new message...")
        summary = await summarize_trade(content, image_url)
        await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
        print("✅ Sent summary to Telegram.")
    except Exception as e:
        print(f"⚠️ Error processing message: {e}")

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)