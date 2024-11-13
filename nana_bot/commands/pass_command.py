import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import sqlite3
from nana_bot import bot, ALLOWED_ROLE_IDS, newcomer_channel_id, not_reviewed_id, reviewed_role_id, reviewed_prompt_channel_id, pass_user_prompt_text, TARGET_CHANNEL_ID, debug
import logging
import re

@bot.tree.command(name="pass", description="審核通過")
async def pass_user(interaction: discord.Interaction, member: discord.Member):
    server_id = interaction.guild.id
    role_id_add = reviewed_role_id
    role_id_remove = not_reviewed_id
    pass_user_prompt = ""
    if debug:
        logging.info(member)
    replacements = {
    "{member.mention}": member.mention,
    "{reviewed_prompt_channel_id}": reviewed_prompt_channel_id,
    }
    i = 0
    for input in TARGET_CHANNEL_ID:
        replacements["<#{TARGET_CHANNEL_ID[" + str(i) + "]}>"] = "<#"+str(input)+"> "
        pattern = str("{TARGET_CHANNEL_ID[" + str(i) + "]}")
        if debug:
            print("Pattern:", pattern)
            print("Pass user prompt:", pass_user_prompt_text)
        if re.search(re.escape(pattern), str(pass_user_prompt_text)):
            if debug:
                logging.info("pattern "+pattern+" in :"+str(pass_user_prompt_text))
                logging.info("replace to "+str(input))
        else:
            if debug:
                logging.info("pattern "+pattern+" not in :"+pass_user_prompt_text)
        i += 1
    pass_user_prompt = multiple_replace(pass_user_prompt_text, replacements)
    embed = discord.Embed(
        title="歡迎加入",
        description=f"{pass_user_prompt}",
    )
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        embed = discord.Embed(title="ERROR錯誤!!!", description=f"你沒有權限使用此指令")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    if (
        interaction.channel.id not in newcomer_channel_id
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

    roles_to_add = [interaction.guild.get_role(role_id) for role_id in role_id_add] 
    for role in roles_to_add: 
        if role is not None: 
            await member.add_roles(role)

    roles_to_remove = [interaction.guild.get_role(role_id) for role_id in role_id_remove] 
    for role in roles_to_remove: 
        if role is not None: 
            await member.remove_roles(role)
    await interaction.response.send_message(embed=embed)




def multiple_replace(text, replacements):
    replacements = {k: str(v) for k, v in replacements.items()}
    pattern = re.compile("|".join(re.escape(key) for key in replacements.keys()))
    return pattern.sub(lambda match: replacements[match.group(0)], text)


