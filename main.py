import os
import discord
import requests
import base64
import asyncio
from openai import OpenAI
from telegram import Bot

# 🔐 Load secrets from Railway environment
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)

def extract_image_url(message):
    for attachment in message.attachments:
        if attachment.content_type and 'image' in attachment.content_type:
            return attachment.url
    return None

def format_gpt_prompt(text):
    return [
        {"role": "system", "content": (
            "You are a trading assistant. Read the message carefully and return:"
            "\n1. Key support and resistance levels"
            "\n2. Breakout/breakdown zones"
            "\n3. Directional bias (bullish/bearish/rangebound)"
            "\n4. Summarize in simple terms for a retail trader."
        )},
        {"role": "user", "content": text}
    ]

async def send_to_telegram(msg):
    await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    try:
        if message.author.bot:
            return  # Skip other bots

        content = message.content.strip()
        image_url = extract_image_url(message)

        if not content and not image_url:
            print("⚠️ No content or image to process.")
            return

        if content:
            print(f"📩 New message: {content[:60]}...")
            gpt_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=format_gpt_prompt(content)
            )
            summary = gpt_response.choices[0].message.content
            await send_to_telegram(summary)
            print("✅ Sent GPT text summary to Telegram.")

        if image_url:
            print(f"🖼️ Found image: {image_url}")
            gpt_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": (
                        "Analyze this trading chart image and explain key patterns, support/resistance levels, "
                        "and directional bias for a trader." 
                    )},
                    {"role": "user", "content": image_url}
                ]
            )
            image_summary = gpt_response.choices[0].message.content
            await send_to_telegram(f"📊 Image Summary:\n{image_summary}")
            print("✅ Sent GPT image summary to Telegram.")

    except Exception as e:
        print(f"❌ Error processing message: {e}")

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)