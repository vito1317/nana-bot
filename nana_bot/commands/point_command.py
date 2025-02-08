import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import pytz
import sqlite3
from nana_bot import bot, ALLOWED_ROLE_IDS, init_db_points, default_points
import logging
import os

utc8 = timezone(timedelta(hours=8))


@bot.tree.command(name='add', description='增加使用者的點數')
async def add_points(interaction: discord.Interaction, member: discord.Member, points: int, *, reason: str):
    init_db_points(str(interaction.guild.id))
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        embed = discord.Embed(title="ERROR錯誤!!!",
                              description=f'你沒有權限使用此指令')
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    db_name = 'points_' + str(interaction.guild.id) + '.db'
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../databases", db_name)
    logging.info(f"Database path: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT points FROM users WHERE user_id = ?', (str(member.id),))
    result = cursor.fetchone()

    if result is None:
        new_points = points
        joined_date = member.joined_at

        utc_zone = pytz.utc

        taipei_zone = pytz.timezone('Asia/Taipei')

        joined_date = joined_date.replace(tzinfo=utc_zone)

        joined_date_taipei = joined_date.astimezone(taipei_zone)

        iso_format_date_taipei = joined_date_taipei.isoformat()
        
        cursor.execute('INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)',
                (str(member.id), member.name, iso_format_date_taipei, 100))
        conn.commit()

        cursor.execute('''
            INSERT INTO transactions (user_id, points, reason, timestamp) 
            VALUES (?, ?, ?, ?)
            ''', (str(member.id), str(default_points), "初始贈送"+str(default_points)+"點數", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        new_points = max(0, result[0] - points) 
        cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, str(member.id)))
        cursor.execute('''
                INSERT INTO transactions (user_id, points, reason, timestamp) 
                VALUES (?, ?, ?, ?)
                ''', (str(member.id), -points, reason, datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
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
        ''', (str(member.id), points, reason, datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S')))

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
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../databases", db_name)
    conn = sqlite3.connect(db_path)
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
                ''', (str(member.id), -points, reason, datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        embed = discord.Embed(title="點數減少",
                              description=f'{member.mention} 的點數已減少 {points} 點，理由: {reason}。目前總點數為 {new_points} 點。',
                              color=discord.Color.red())
        await interaction.followup.send(embed=embed)
    else:
        joined_date = member.joined_at

        utc_zone = pytz.utc

        taipei_zone = pytz.timezone('Asia/Taipei')

        joined_date = joined_date.replace(tzinfo=utc_zone)

        joined_date_taipei = joined_date.astimezone(taipei_zone)

        iso_format_date_taipei = joined_date_taipei.isoformat()
        
        cursor.execute('INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)',
                (str(member.id), member.name, iso_format_date_taipei, 100))
        conn.commit()

        cursor.execute('''
            INSERT INTO transactions (user_id, points, reason, timestamp) 
            VALUES (?, ?, ?, ?)
            ''', (str(member.id), str(default_points), "初始贈送"+str(default_points)+"點數", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        new_points = max(0, result[0] - points)  # 確保點數不會變成負數
        cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, str(member.id)))
        cursor.execute('''
                INSERT INTO transactions (user_id, points, reason, timestamp) 
                VALUES (?, ?, ?, ?)
                ''', (str(member.id), -points, reason, datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        embed = discord.Embed(title="點數減少",
                              description=f'{member.mention} 的點數已減少 {points} 點，理由: {reason}。目前總點數為 {new_points} 點。',
                              color=discord.Color.red())
        await interaction.followup.send(embed=embed)


@bot.tree.command(name='points', description='查詢使用者的點數')
async def check_points(interaction: discord.Interaction, member: discord.Member):
    init_db_points(str(interaction.guild.id))
    db_name = 'points_' + str(interaction.guild.id) + '.db'
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../databases", db_name)
    logging.info(f"Database path: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT points FROM users WHERE user_id = ?', (str(member.id),))
    result = cursor.fetchone()
    
    if result:
        current_points = result[0]
        cursor.execute('SELECT points, reason, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp DESC', (str(member.id),))
        transactions = cursor.fetchall()
        conn.close()
        await interaction.response.defer()


        embed = discord.Embed(title="查詢點數",
                            description=f'{member.mention} 目前有 {current_points} 點。',
                            color=discord.Color.blue())
        
        if transactions:
            transaction_text = ""
            # 只顯示最近 10 筆交易記錄
            for points, reason, timestamp in transactions[:10]:
                timestamp_utc = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                timestamp_utc8 = timestamp_utc.replace(tzinfo=timezone.utc).astimezone(utc8)
                timestamp_str = timestamp_utc8.strftime('%Y-%m-%d %H:%M:%S')
                transaction_text += f"```{timestamp_str} | {'+' if points > 0 else ''}{points} | {reason}```\n"

            # 增加一個提示，告訴使用者還有更多記錄
            if len(transactions) > 10:
                transaction_text += "...\n(僅顯示最近 10 筆交易記錄)"

            embed.add_field(name="點數紀錄", value=transaction_text, inline=False)

        await interaction.followup.send(embed=embed)
    else:
        # ... (其餘程式碼不變) ...
        joined_date = member.joined_at

        utc_zone = pytz.utc

        taipei_zone = pytz.timezone('Asia/Taipei')

        joined_date = joined_date.replace(tzinfo=utc_zone)

        joined_date_taipei = joined_date.astimezone(taipei_zone)

        iso_format_date_taipei = joined_date_taipei.isoformat()
        
        cursor.execute('INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)',
                (str(member.id), member.name, iso_format_date_taipei, 100))
        conn.commit()

        cursor.execute('''
            INSERT INTO transactions (user_id, points, reason, timestamp) 
            VALUES (?, ?, ?, ?)
            ''', (str(member.id), str(default_points), "初始贈送"+str(default_points)+"點數", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        await interaction.response.defer()
        embed = discord.Embed(title="查詢點數",
                            description=f'{member.mention} 目前有 100 點，已給予初始點數。',
                            color=discord.Color.blue())
        await interaction.followup.send(embed=embed)