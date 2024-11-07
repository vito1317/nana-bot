import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import sqlite3
from nana_bot import bot, ALLOWED_ROLE_IDS
import logging


@bot.tree.command(name="pass", description="審核通過")
async def pass_user(interaction: discord.Interaction, member: discord.Member):
    server_id = interaction.guild.id
    if server_id == 1212105433943117844:
        role_id_add = 1212117045890523256
        role_id_remove = 1275643437823168624
        embed = discord.Embed(
            title="歡迎加入",
            description=f"{member.mention} 已通過審核，可以先到 <#1212130394548473927> 打聲招呼，也歡迎到 <#1282901299624677448> 或 <#1282901518265225277> 找Wen或是我(奈奈)聊聊喔!",
        )
    elif server_id == 1283632521661124701:
        role_id_add = 1283638437634773072
        role_id_remove = 1284023837692002345
        embed = discord.Embed(
            title="歡迎加入",
            description=f"{member.mention} 已通過審核，可以先到 <#1283649384311164999> 打聲招呼，也歡迎到 <#1285403233916948491> 或 <#1283653144760287252>  找媛媛或是我聊聊喔!",
        )
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        embed = discord.Embed(title="ERROR錯誤!!!", description=f"你沒有權限使用此指令")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    if (
        interaction.channel.id != 1212120624122826812
        and interaction.channel.id != 1283646860409573387
    ):
        embed = discord.Embed(
            title="睜大妳的眼睛看看這是啥頻道吧你",
            description=f"此指令只能在指定的頻道中使用，睜大你的眼睛看看這裡是啥頻道。",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    db_name = "analytics_server_" + str(interaction.guild.id) + ".db"
    conn = sqlite3.connect("./databases/" + db_name)
    cursor = conn.cursor()
    cursor.execute(
        """
       CREATE TABLE IF NOT EXISTS reviews (
           review_id INTEGER PRIMARY KEY AUTOINCREMENT,
           user_id TEXT,
           review_date TEXT
       )
       """
    )
    cursor.execute(
        """
       INSERT INTO reviews (user_id, review_date) 
       VALUES (?, ?)
       """,
        (str(member.id), datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

    role_add = interaction.guild.get_role(role_id_add)
    await member.add_roles(role_add)

    role_remove = interaction.guild.get_role(role_id_remove)
    await member.remove_roles(role_remove)
    await interaction.response.send_message(embed=embed)
