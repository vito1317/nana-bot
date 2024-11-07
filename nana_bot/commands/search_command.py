import discord
from search_engine_tool_vito1317 import google, bing, yahoo
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import sqlite3
from nana_bot import bot
import logging
engines = [
    app_commands.Choice(name='Google', value='google'),
    app_commands.Choice(name='yahoo', value='yahoo')
]
@bot.tree.command(name='search', description='搜尋網路上的酷東西')
@app_commands.describe(engine='選擇搜索引擎', text='輸入搜索內容')
@app_commands.choices(engine=engines)
async def search(interaction: discord.Interaction, engine: str, text: str):
    allowed_engines = ['google', 'bing', 'yahoo']
    await interaction.response.defer()
    if engine not in allowed_engines:
        await interaction.followup.send(f"無效的搜尋引擎：{engine}。請使用以下之一：{', '.join(allowed_engines)}")
        return
    server_id = interaction.guild.id
    timestamp = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

    def search(engine, query):
        try:
            if engine == 'google':
                results = google.search(query, 'request')
            elif engine == 'bing':
                results = bing.search(query)
            elif engine == 'yahoo':
                results = yahoo.search(query, 'request')

        except Exception as e:
            print(e)
            return []

        content = ""
        for result in results:
            content += f"標題: {result['title']}\n"
            content += f"鏈接: {result['href']}\n"
            content += f"摘要: {result['abstract']}\n\n"
        return content

    content = search(engine, text)

    with sqlite3.connect("./databases/"+f'messages_chat_{server_id}.db') as conn:
        c = conn.cursor()
        c.execute("INSERT INTO message (user, content, timestamp) VALUES (?, ?, ?)",
                  ("奈奈", content, timestamp))
        conn.commit()
    max_length = 2000
    chunks = [content[i:i + max_length] for i in range(0, len(content), max_length)]

    for chunk in chunks:
        embed = discord.Embed(title="查詢結果: " + text, description=chunk,
                              color=discord.Color.green())
        await interaction.followup.send(embed=embed)