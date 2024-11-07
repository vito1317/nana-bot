import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import sqlite3
from nana_bot import bot ,gemini_model, get_current_time_utc8
import aiohttp
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from bs4 import BeautifulSoup
import re
model = genai.GenerativeModel(gemini_model)

@bot.tree.command(name='aibrowse', description='讓ai瀏覽並總結網站')
async def aibrowse(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    server_id = interaction.guild.id
    user_id = interaction.user.id
    db_name = f'analytics_server_{server_id}.db'

    def update_token_in_db(total_token_count, userid):
        if not total_token_count:
            print("No total_token_count provided.")
            return
        with sqlite3.connect("./databases/"+db_name) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    userid TEXT UNIQUE,
                    total_token_count INTEGER
                )
            ''')
            c.execute('''
                INSERT INTO metadata (userid, total_token_count) 
                VALUES (?, ?)
                ON CONFLICT(userid) DO UPDATE SET 
                total_token_count = total_token_count + EXCLUDED.total_token_count
            ''', (userid, total_token_count))
            conn.commit()
            print("Data updated successfully.")

    async def browse(url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        text = await response.text()
                        soup = BeautifulSoup(text, 'html.parser')
                        elements = soup.find_all(['div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'])
                        elements_str = ''.join(str(element) for element in elements)
                        return elements_str
                    else:
                        return
            except Exception as e:
                return

    content = await browse(url)
    chat = model.start_chat()
    server_id = interaction.guild.id
    timestamp = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    if (content):
        try:
            response = chat.send_message(
                get_current_time_utc8() + "請總結 瀏覽結果 " + url + ':' + content,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                })
            match = re.search(r'"total_token_count":\s*(\d+)', str(response))
            if match:
                total_token_count = int(match.group(1))
                print(total_token_count)
                update_token_in_db(total_token_count, user_id)
            else:
                print("Match not found.")
        except Exception as e:
            await interaction.followup.send(
                "發生錯誤，可能的原因: 該網站內容過長、該網站不允許瀏覽，\n錯誤訊息:\n" + str(e))
        with sqlite3.connect("./databases/"+f'messages_chat_{server_id}.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO message (user, content, timestamp) VALUES (?, ?, ?)",
                      ("奈奈", response.text, timestamp))
            conn.commit()
        await interaction.followup.send(response.text)
    else:
        await interaction.followup.send("Error發生錯誤，無法取得此連結，請換個連結後再試一次", ephemeral=True)
