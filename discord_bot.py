import discord
import os
from openai import OpenAI
from telegram import Bot

# GPT + Telegram Bot setup
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
telegram_bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
chat_id = int(os.getenv("CHAT_ID"))

intents = discord.Intents.default()
intents.message_content = True

class DiscordListener(discord.Client):
    async def on_ready(self):
        print(f"🎧 Discord bot logged in as {self.user}")

    async def on_message(self, message):
        if message.author.bot:
            return

        try:
            print(f"💬 Discord message: {message.content[:50]}...")
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Summarize and explain this trading alert in simple English."},
                    {"role": "user", "content": message.content}
                ]
            )
            gpt_reply = response.choices[0].message.content
            await telegram_bot.send_message(chat_id=chat_id, text=f"📢 Discord: {gpt_reply}")
            print("✅ Sent GPT summary to Telegram.")

        except Exception as e:
            print(f"⚠️ Error in Discord handler: {e}")

client = DiscordListener(intents=intents)
client.run(os.getenv("DISCORD_BOT_TOKEN"))
