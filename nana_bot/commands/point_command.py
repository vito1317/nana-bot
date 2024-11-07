import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import sqlite3
from nana_bot import bot, ALLOWED_ROLE_IDS, init_db_points
import logging

@bot.tree.command(name='add', description='增加使用者的點數')
async def add_points(interaction: discord.Interaction, member: discord.Member, points: int, *, reason: str):
    init_db_points(str(interaction.guild.id))
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        embed = discord.Embed(title="ERROR錯誤!!!",
                              description=f'你沒有權限使用此指令')
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    db_name = 'points_' + str(interaction.guild.id) + '.db'
    conn = sqlite3.connect("./databases/"+db_name)
    cursor = conn.cursor()

    cursor.execute('SELECT points FROM users WHERE user_id = ?', (str(member.id),))
    result = cursor.fetchone()

    if result is None:
        new_points = points
        cursor.execute('INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)',
                       (str(member.id), member.name, member.joined_at.isoformat(), new_points))
    else:
        current_points = result[0]
        new_points = current_points + points
        cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, str(member.id)))
    conn.commit()

    cursor.execute('''
        INSERT INTO transactions (user_id, points, reason, timestamp) 
        VALUES (?, ?, ?, ?)
        ''', (str(member.id), points, reason, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()
    conn.close()
    await interaction.response.defer()
    embed = discord.Embed(title="點數增加",
                          description=f'{member.mention} 的點數已增加 {points} 點，理由: {reason}。目前總點數為 {new_points} 點。',
                          color=discord.Color.green())
    await interaction.followup.send(embed=embed)


@bot.tree.command(name='subtract', description='減少使用者的點數')
async def subtract_points(interaction: discord.Interaction, member: discord.Member, points: int, *, reason: str):
    init_db_points(str(interaction.guild.id))
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        embed = discord.Embed(title="ERROR錯誤!!!",
                              description=f'你沒有權限使用此指令')
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    db_name = 'points_' + str(interaction.guild.id) + '.db'
    conn = sqlite3.connect("./databases/"+db_name)
    cursor = conn.cursor()
    cursor.execute('SELECT points FROM users WHERE user_id = ?', (str(member.id),))
    result = cursor.fetchone()
    await interaction.response.defer()
    if result:
        new_points = max(0, result[0] - points)  # 確保點數不會變成負數
        cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, str(member.id)))
        cursor.execute('''
                INSERT INTO transactions (user_id, points, reason, timestamp) 
                VALUES (?, ?, ?, ?)
                ''', (str(member.id), -points, reason, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        embed = discord.Embed(title="點數減少",
                              description=f'{member.mention} 的點數已減少 {points} 點，理由: {reason}。目前總點數為 {new_points} 點。',
                              color=discord.Color.red())
        await interaction.followup.send(embed=embed)
    else:
        conn.close()
        embed = discord.Embed(title="錯誤",
                              description=f'{member.mention} 尚未有任何點數記錄。',
                              color=discord.Color.red())
        await interaction.followup.send(embed=embed)


@bot.tree.command(name='points', description='查詢使用者的點數')
async def check_points(interaction: discord.Interaction, member: discord.Member):
    init_db_points(str(interaction.guild.id))
    db_name = 'points_' + str(interaction.guild.id) + '.db'
    conn = sqlite3.connect("./databases/"+db_name)
    cursor = conn.cursor()
    cursor.execute('SELECT points FROM users WHERE user_id = ?', (str(member.id),))
    result = cursor.fetchone()
    conn.close()
    await interaction.response.defer()

    if result:
        embed = discord.Embed(title="查詢點數",
                              description=f'{member.mention} 目前有 {result[0]} 點。',
                              color=discord.Color.blue())
        await interaction.followup.send(embed=embed)
    else:
        embed = discord.Embed(title="查詢點數",
                              description=f'{member.mention} 尚未有任何點數記錄。',
                              color=discord.Color.blue())
        await interaction.followup.send(embed=embed)