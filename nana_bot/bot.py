# -*- coding: utf-8 -*-
import asyncio
import traceback
import discord
from discord import app_commands, FFmpegPCMAudio
from discord.ext import commands, tasks
from typing import Optional
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
import json
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import requests
from bs4 import BeautifulSoup
import time
import re
import pytz
from .commands import *
from nana_bot import (
    bot,
    bot_name,
    WHITELISTED_SERVERS,
    TARGET_CHANNEL_ID,
    API_KEY,
    init_db,
    gemini_model,
    servers,
    send_daily_channel_id_list,
    not_reviewed_id,
    newcomer_channel_id,
    welcome_channel_id,
    member_remove_channel_id,
    discord_bot_token,
    review_format,
    debug,
    Point_deduction_system,
    default_points
)
import os
import pyttsx3
import threading
import torch, os, io
from typing import Union, IO, Any
if not hasattr(torch.serialization, "FILE_LIKE"):
    file_like_type = getattr(torch.serialization, "FileLike", Union[str, os.PathLike, IO[bytes]])
    setattr(torch.serialization, "FILE_LIKE", file_like_type)

import asyncio, tempfile, os
import edge_tts
import torch, torchaudio
from discord import FFmpegPCMAudio



DEFAULT_VOICE = "zh-TW-HsiaoYuNeural"

logging.basicConfig(level=logging.INFO if not debug else logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("bot.log", encoding='utf-8'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

'''
tts_engine = None
tts_lock = asyncio.Lock()

def init_tts_engine():
    global tts_engine
    logger.info("Initializing pyttsx3 engine (fallback/alternative)...")
    try:
        engine = pyttsx3.init(driverName='espeak')
        selected_voice_id = None
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
                 selected_voice_id = voice.id
                 logger.info(f"Found potential Chinese voice (pyttsx3): {voice.name} (ID: {voice.id})")
                 break

        if selected_voice_id:
            engine.setProperty('voice', selected_voice_id)
            logger.info(f"Set pyttsx3 voice to: {selected_voice_id}")
        else:
            logger.warning("No suitable Chinese voice found for pyttsx3, using default.")

        rate = engine.getProperty('rate')
        engine.setProperty('rate', rate + 50)
        tts_engine = engine
        logger.info("pyttsx3 engine initialized successfully.")
        return tts_engine
    except Exception as e:
        logger.error(f"Failed to initialize pyttsx3 engine: {e}", exc_info=True)
        tts_engine = None
        return None
'''
def get_current_time_utc8():
    utc8 = timezone(timedelta(hours=8))
    current_time = datetime.now(utc8)
    return current_time.strftime("%Y-%m-%d %H:%M:%S")

genai.configure(api_key=API_KEY)
not_reviewed_role_id = not_reviewed_id
try:
    if not API_KEY:
        raise ValueError("Gemini API key is not set.")
    model = genai.GenerativeModel(gemini_model)
    logger.info(f"Successfully initialized GenerativeModel: {gemini_model}")
except Exception as e:
    logger.critical(f"Failed to initialize GenerativeModel: {e}")
    model = None

voice_clients = {}
db_base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases")
os.makedirs(db_base_path, exist_ok=True)

def get_db_path(guild_id, db_type):
    """取得特定伺服器和類型的資料庫路徑"""
    if db_type == 'analytics':
        return os.path.join(db_base_path, f"analytics_server_{guild_id}.db")
    elif db_type == 'chat':
        return os.path.join(db_base_path, f"messages_chat_{guild_id}.db")
    elif db_type == 'points':
        return os.path.join(db_base_path, f"points_{guild_id}.db")
    else:
        raise ValueError(f"Unknown database type: {db_type}")

def init_db_for_guild(guild_id):
    """為特定伺服器初始化所有資料庫"""
    logger.info(f"Initializing databases for guild {guild_id}...")
    db_tables = {
        "users": "user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, message_count INTEGER DEFAULT 0",
        "messages": "message_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_name TEXT, channel_id TEXT, timestamp TEXT, content TEXT",
        "metadata": """id INTEGER PRIMARY KEY AUTOINCREMENT,
                    userid TEXT UNIQUE,
                    total_token_count INTEGER,
                    channelid TEXT""",
        "reviews": """review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    review_date TEXT"""
    }
    points_tables = {
        "users": f"user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, points INTEGER DEFAULT {default_points}",
        "transactions": f"id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, points INTEGER, reason TEXT, timestamp TEXT"
    }
    chat_tables = {
         "message": "id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, content TEXT, timestamp TEXT"
    }

    def _init_single_db(db_path, tables_dict):
        conn = None
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            cursor = conn.cursor()
            for table_name, table_schema in tables_dict.items():
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({table_schema})")
            conn.commit()
            logger.debug(f"Database initialized/checked: {db_path}")
        except sqlite3.Error as e:
            logger.exception(f"Database error initializing {db_path}: {e}")
        finally:
            if conn:
                conn.close()

    _init_single_db(get_db_path(guild_id, 'analytics'), db_tables)
    _init_single_db(get_db_path(guild_id, 'points'), points_tables)
    _init_single_db(get_db_path(guild_id, 'chat'), chat_tables)


@tasks.loop(hours=24)
async def send_daily_message():
    logger.info("Starting daily message task...")
    for idx, server_id in enumerate(servers):
        try:
            if idx < len(send_daily_channel_id_list) and idx < len(not_reviewed_id):
                target_channel_id = send_daily_channel_id_list[idx]
                role_to_mention_id = not_reviewed_id[idx]
                channel = bot.get_channel(target_channel_id)
                guild = bot.get_guild(server_id)

                if channel and guild:
                    role = guild.get_role(role_to_mention_id)
                    if role:
                        try:
                            await channel.send(
                                f"{role.mention} 各位未審核的人，快來這邊審核喔"
                            )
                            logger.info(f"Sent daily message to channel {target_channel_id} in guild {server_id}")
                        except discord.Forbidden:
                            logger.error(f"Permission error sending daily message to channel {target_channel_id} in guild {server_id}.")
                        except discord.HTTPException as e:
                            logger.error(f"HTTP error sending daily message to channel {target_channel_id} in guild {server_id}: {e}")
                    else:
                        logger.warning(f"Role {role_to_mention_id} not found in guild {server_id} for daily message.")
                else:
                    if not channel:
                        logger.warning(f"Daily message channel {target_channel_id} not found for server index {idx} (Guild ID: {server_id}).")
                    if not guild:
                         logger.warning(f"Guild {server_id} not found for daily message.")
            else:
                logger.error(f"Configuration index {idx} out of range for daily message (Guild ID: {server_id}). Lists length: send_daily={len(send_daily_channel_id_list)}, not_reviewed={len(not_reviewed_id)}")
        except Exception as e:
            logger.exception(f"Unexpected error in send_daily_message loop for server index {idx} (Guild ID: {server_id}): {e}")
    logger.info("Finished daily message task.")


@send_daily_message.before_loop
async def before_send_daily_message():
    await bot.wait_until_ready()
    now = datetime.now(pytz.timezone('Asia/Taipei'))
    next_run = now.replace(hour=9, minute=0, second=0)
    if next_run < now:
        next_run += timedelta(days=1)
    await asyncio.sleep((next_run - now).total_seconds())


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"Discord.py version: {discord.__version__}")
    logger.info("Bot is ready and connected to Discord.")

    if model is None:
        logger.error("AI Model failed to initialize. AI reply functionality will be disabled.")

    guild_count = 0
    for guild in bot.guilds:
        guild_count += 1
        logger.info(f"Bot is in server: {guild.name} (ID: {guild.id})")
        init_db_for_guild(guild.id)

    try:


        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} application commands globally or across guilds.")

    except discord.errors.Forbidden as e:
        logger.warning(f"Could not sync commands due to permissions: {e}")
    except discord.HTTPException as e:
        logger.error(f"HTTP error during command sync: {e}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during command sync: {e}")

    if not send_daily_message.is_running():
        send_daily_message.start()
        logger.info("Started daily message task.")

    activity = discord.Game(name=f"在 {guild_count} 個伺服器上運作 | /help")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    logger.info(f"Bot presence set. Watching {guild_count} servers.")


@bot.event
async def on_guild_join(guild):
    """當機器人加入新伺服器時觸發"""
    logger.info(f"Bot joined a new guild: {guild.name} (ID: {guild.id})")
    init_db_for_guild(guild.id)
    if guild.id not in servers:
        logger.warning(f"Guild {guild.id} not found in the 'servers' list in config. Manual configuration might be needed.")

    try:
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} commands for the new guild {guild.id}.")
    except discord.errors.Forbidden:
         logger.error(f"Permission error syncing commands for the new guild {guild.id}.")
    except Exception as e:
         logger.exception(f"Error syncing commands for the new guild {guild.id}: {e}")

    channel_to_send = guild.system_channel or guild.text_channels[0]
    if channel_to_send and channel_to_send.permissions_for(guild.me).send_messages:
        try:
            await channel_to_send.send(f"大家好！我是 {bot_name}。很高興加入 **{guild.name}**！\n"
                                       f"您可以使用 `/help` 來查看我的指令。\n"
                                       f"請確保已根據需求設定相關頻道 ID 和權限。\n"
                                       f"我的設定檔需要手動更新以包含此伺服器 ID ({guild.id}) 的相關設定 (例如審核頻道、歡迎頻道等)。")
            logger.info(f"Sent welcome message to {channel_to_send.name} in guild {guild.id}")
        except discord.Forbidden:
            logger.warning(f"Could not send welcome message to {channel_to_send.name} in guild {guild.id} due to permissions.")
        except discord.HTTPException as e:
            logger.error(f"HTTP error sending welcome message to {channel_to_send.name} in guild {guild.id}: {e}")
    else:
        logger.warning(f"Could not find a suitable channel to send a welcome message in guild {guild.id} or missing send permissions.")


@bot.event
async def on_member_join(member):
    guild = member.guild
    logger.info(f"New member joined: {member} (ID: {member.id}) in server {guild.name} (ID: {guild.id})")

    server_index = -1
    for idx, s_id in enumerate(servers):
        if guild.id == s_id:
            server_index = idx
            break

    if server_index == -1:
        logger.warning(f"No configuration found for server ID {guild.id} in on_member_join. Skipping role/welcome message.")
        return

    try:
        current_welcome_channel_id = welcome_channel_id[server_index]
        current_role_id = not_reviewed_id[server_index]
        current_newcomer_channel_id = newcomer_channel_id[server_index]
    except IndexError:
        logger.error(f"Configuration index {server_index} out of range for server ID {guild.id}. Check config lists length.")
        return

    analytics_db_path = get_db_path(guild.id, 'analytics')
    conn_user_join = None
    try:
        conn_user_join = sqlite3.connect(analytics_db_path, timeout=10)
        c_user_join = conn_user_join.cursor()
        join_utc = member.joined_at.astimezone(timezone.utc) if member.joined_at else datetime.now(timezone.utc)
        join_iso = join_utc.isoformat()
        c_user_join.execute(
            "INSERT OR IGNORE INTO users (user_id, user_name, join_date, message_count) VALUES (?, ?, ?, ?)",
            (str(member.id), member.name, join_iso, 0),
        )
        conn_user_join.commit()
        logger.debug(f"User {member.id} added/ignored in analytics DB for guild {guild.id}")
    except sqlite3.Error as e:
        logger.exception(f"Database error on member join (analytics) for guild {guild.id}: {e}")
    finally:
        if conn_user_join:
            conn_user_join.close()

    points_db_path = get_db_path(guild.id, 'points')
    conn_points_join = None
    try:
        conn_points_join = sqlite3.connect(points_db_path, timeout=10)
        c_points_join = conn_points_join.cursor()
        c_points_join.execute("SELECT user_id FROM users WHERE user_id = ?", (str(member.id),))
        if not c_points_join.fetchone():
            if default_points >= 0:
                join_utc_points = member.joined_at.astimezone(timezone.utc) if member.joined_at else datetime.now(timezone.utc)
                join_date_iso_points = join_utc_points.isoformat()
                c_points_join.execute(
                    "INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)",
                    (str(member.id), member.name, join_date_iso_points, default_points)
                )
                if default_points > 0:
                    c_points_join.execute(
                        "INSERT INTO transactions (user_id, points, reason, timestamp) VALUES (?, ?, ?, ?)",
                        (str(member.id), default_points, "初始贈送點數", get_current_time_utc8())
                    )
                conn_points_join.commit()
                logger.info(f"Gave initial {default_points} points to new member {member.name} (ID: {member.id}) in server {guild.id}")
            else:
                 logger.info(f"Initial points set to {default_points}, not adding user {member.id} to points table automatically.")
        else:
            logger.debug(f"User {member.id} already exists in points DB for guild {guild.id}")

    except sqlite3.Error as e:
        logger.exception(f"Database error on member join (points) for guild {guild.id}: {e}")
    finally:
        if conn_points_join:
            conn_points_join.close()

    role = guild.get_role(current_role_id)
    if role:
        try:
            await member.add_roles(role, reason="新成員加入，分配未審核角色")
            logger.info(f"Added role '{role.name}' to member {member.name} (ID: {member.id}) in guild {guild.id}")
        except discord.Forbidden:
            logger.error(f"Permission error: Cannot add role '{role.name}' to {member.name} (ID: {member.id}) in guild {guild.id}. Check bot permissions and role hierarchy.")
        except discord.HTTPException as e:
            logger.error(f"Failed to add role '{role.name}' to member {member.name} (ID: {member.id}) in guild {guild.id}: {e}")
    else:
        logger.warning(f"Role {current_role_id} (not_reviewed_id) not found in server {guild.id}. Cannot assign role.")

    welcome_channel = bot.get_channel(current_welcome_channel_id)
    if not welcome_channel:
        logger.warning(f"Welcome channel {current_welcome_channel_id} not found for server {guild.id}. Cannot send welcome message.")
        return

    if not welcome_channel.permissions_for(guild.me).send_messages:
        logger.error(f"Bot does not have permission to send messages in the welcome channel {current_welcome_channel_id} for guild {guild.id}.")
        return

    newcomer_channel_mention = f"<#{current_newcomer_channel_id}>" if bot.get_channel(current_newcomer_channel_id) else f"頻道 ID {current_newcomer_channel_id} (未找到)"

    if model:
        try:
            welcome_prompt = [
                f"{bot_name}是一位來自台灣的智能陪伴機器人...",
                f"你現在要做的事是歡迎使用者{member.mention}的加入...",
                f"第二步是tag {newcomer_channel_mention} 傳送這則訊息進去...",
                f"新人審核格式包誇(```{review_format}```)...",
            ]
            async with welcome_channel.typing():
                responses = await model.generate_content_async(
                    welcome_prompt,
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                )
            if responses.candidates and responses.text:
                embed = discord.Embed(
                    title=f"🎉 歡迎 {member.display_name} 加入 {guild.name}！",
                    description=responses.text,
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"加入時間: {get_current_time_utc8()} (UTC+8)")
                await welcome_channel.send(embed=embed)
                logger.info(f"Sent AI-generated welcome message for {member.id} in guild {guild.id}")
            else:
                logger.warning(f"AI failed to generate a valid welcome message for {member.id}. Reason: {responses.prompt_feedback if responses.prompt_feedback else 'No text in response'}. Sending fallback.")
                fallback_message = (
                    f"歡迎 {member.mention} 加入 **{guild.name}**！我是 {bot_name}。\n"
                    f"很高興見到你！請先前往 {newcomer_channel_mention} 頻道進行新人審核。\n"
                    f"審核格式如下：\n```{review_format}```"
                )
                await welcome_channel.send(fallback_message)

        except Exception as e:
            logger.exception(f"Error generating or sending AI welcome message for {member.id} in guild {guild.id}: {e}")
            try:
                fallback_message = (
                    f"歡迎 {member.mention} 加入 **{guild.name}**！我是 {bot_name}。\n"
                    f"發生了一些錯誤，無法生成個人化歡迎詞。\n"
                    f"請先前往 {newcomer_channel_mention} 頻道進行新人審核。\n"
                    f"審核格式如下：\n```{review_format}```"
                )
                await welcome_channel.send(fallback_message)
            except discord.DiscordException as send_error:
                logger.error(f"Failed to send fallback welcome message after AI error: {send_error}")
    else:
        try:
            simple_message = (
                f"歡迎 {member.mention} 加入 **{guild.name}**！我是 {bot_name}。\n"
                f"請前往 {newcomer_channel_mention} 頻道進行新人審核。\n"
                f"審核格式如下：\n```{review_format}```"
            )
            await welcome_channel.send(simple_message)
            logger.info(f"Sent simple welcome message for {member.id} in guild {guild.id} (AI unavailable).")
        except discord.DiscordException as send_error:
            logger.error(f"Failed to send simple welcome message (AI unavailable): {send_error}")


@bot.event
async def on_member_remove(member):
    guild = member.guild
    logger.info(f"Member left: {member} (ID: {member.id}) from server {guild.name} (ID: {guild.id})")

    server_index = -1
    for idx, s_id in enumerate(servers):
        if guild.id == s_id:
            server_index = idx
            break

    if server_index == -1:
        logger.warning(f"No configuration found for server ID {guild.id} in on_member_remove. Skipping leave message/analytics.")
        return

    try:
        current_remove_channel_id = member_remove_channel_id[server_index]
    except IndexError:
        logger.error(f"Configuration index {server_index} out of range for member_remove_channel_id (Guild ID: {guild.id}).")
        return

    remove_channel = bot.get_channel(current_remove_channel_id)
    if not remove_channel:
        logger.warning(f"Member remove channel {current_remove_channel_id} not found for server {guild.id}")

    if remove_channel and not remove_channel.permissions_for(guild.me).send_messages:
        logger.error(f"Bot does not have permission to send messages in the member remove channel {current_remove_channel_id} for guild {guild.id}.")
        remove_channel = None

    try:
        leave_time_utc8 = datetime.now(timezone(timedelta(hours=8)))
        formatted_time = leave_time_utc8.strftime("%Y-%m-%d %H:%M:%S")

        if remove_channel:
            embed = discord.Embed(
                title="成員離開",
                description=f"**{member.display_name}** ({member.name}#{member.discriminator}) 已經離開伺服器。\n"
                            f"User ID: {member.id}\n"
                            f"離開時間: {formatted_time} (UTC+8)",
                color=discord.Color.orange()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await remove_channel.send(embed=embed)
                logger.info(f"Sent member remove message for {member.id} to channel {current_remove_channel_id}")
            except discord.Forbidden:
                logger.error(f"Permission error: Cannot send message to member remove channel {current_remove_channel_id}.")
            except discord.DiscordException as send_error:
                logger.error(f"Failed to send member remove message to channel {current_remove_channel_id}: {send_error}")

        analytics_db_path = get_db_path(guild.id, 'analytics')
        conn_analytics = None
        try:
            conn_analytics = sqlite3.connect(analytics_db_path, timeout=10)
            c_analytics = conn_analytics.cursor()
            c_analytics.execute(
                "SELECT user_name, message_count, join_date FROM users WHERE user_id = ?",
                (str(member.id),),
            )
            result = c_analytics.fetchone()

            if not result:
                logger.info(f"No analytics data found for leaving member {member.name} (ID: {member.id}) in guild {guild.id}.")
                if remove_channel:
                     await remove_channel.send(f"找不到使用者 {member.name} (ID: {member.id}) 的歷史分析數據。")
            else:
                db_user_name, message_count, join_date_str = result
                join_date_utc = None
                days_in_server = "未知"
                avg_messages_per_day = "未知"

                if join_date_str:
                    try:
                        join_date_utc = datetime.fromisoformat(join_date_str)
                        if join_date_utc.tzinfo is None:
                             join_date_utc = join_date_utc.replace(tzinfo=timezone.utc)

                        leave_time_utc = leave_time_utc8.astimezone(timezone.utc)
                        time_difference = leave_time_utc - join_date_utc
                        days_in_server = max(1, time_difference.days)
                        avg_messages_per_day = f"{message_count / days_in_server:.2f}" if days_in_server > 0 else "N/A"

                        join_date_local_str = join_date_utc.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)"

                    except ValueError:
                        logger.error(f"Invalid date format for join_date: {join_date_str} for user {member.id}")
                        join_date_local_str = f"無法解析 ({join_date_str})"
                    except Exception as date_calc_error:
                        logger.exception(f"Error calculating analytics for user {member.id}: {date_calc_error}")
                        join_date_local_str = "計算錯誤"
                else:
                    logger.warning(f"Missing join_date for user {member.id} in analytics DB.")
                    join_date_local_str = "未知"

                if remove_channel:
                    analytics_embed = discord.Embed(
                        title=f"使用者數據分析 - {db_user_name or member.name}",
                        description=f"User ID: {member.id}\n"
                                    f"加入時間: {join_date_local_str}\n"
                                    f"總發言次數: {message_count}\n"
                                    f"在伺服器天數: {days_in_server}\n"
                                    f"平均每日發言: {avg_messages_per_day}",
                        color=discord.Color.light_grey()
                    )
                    try:
                        await remove_channel.send(embed=analytics_embed)
                        logger.info(f"Sent analytics summary for leaving member {member.id} to channel {current_remove_channel_id}")
                    except discord.Forbidden:
                        logger.error(f"Permission error: Cannot send analytics embed to channel {current_remove_channel_id}.")
                    except discord.DiscordException as send_error:
                        logger.error(f"Failed to send analytics embed to channel {current_remove_channel_id}: {send_error}")


        except sqlite3.Error as e:
            logger.exception(f"Database error on member remove (analytics) for guild {guild.id}: {e}")
        finally:
            if conn_analytics:
                conn_analytics.close()

        points_db_path = get_db_path(guild.id, 'points')
        conn_points = None
        try:
            conn_points = sqlite3.connect(points_db_path, timeout=10)
            c_points = conn_points.cursor()
            c_points.execute("SELECT points FROM users WHERE user_id = ?", (str(member.id),))
            points_result = c_points.fetchone()
            if points_result:
                logger.info(f"User {member.id} left guild {guild.id} with {points_result[0]} points.")
            else:
                logger.info(f"User {member.id} left guild {guild.id}, no points record found.")

        except sqlite3.Error as e:
            logger.exception(f"Database error on member remove (points) for guild {guild.id}: {e}")
        finally:
            if conn_points:
                conn_points.close()

    except Exception as e:
        logger.exception(f"Unexpected error during on_member_remove for {member.name} (ID: {member.id}) in guild {guild.id}: {e}")


@bot.tree.command(name='join', description="讓機器人加入您所在的語音頻道")
@app_commands.guild_only()
async def join(interaction: discord.Interaction):
    """讓機器人加入使用者所在的語音頻道"""
    guild = interaction.guild
    user = interaction.user

    if user.voice and user.voice.channel:
        channel = user.voice.channel
        logger.info(f"User {user.id} requested join in guild {guild.id}, user is in channel {channel.id}")
    else:
        await interaction.response.send_message("您需要先加入一個語音頻道才能邀請我！", ephemeral=True)
        logger.debug(f"User {user.id} tried to use /join without being in a voice channel in guild {guild.id}")
        return

    vc = voice_clients.get(guild.id)
    if vc and vc.is_connected():
        if vc.channel == channel:
            await interaction.response.send_message(f"我已經在 {channel.mention} 頻道裡了。", ephemeral=True)
            logger.debug(f"Bot already in the target channel {channel.id} for guild {guild.id}")
            return
        else:
            logger.info(f"Bot moving from {vc.channel.name} to {channel.name} in guild {guild.id}")
            try:
                await vc.move_to(channel)
                voice_clients[guild.id] = guild.voice_client
                await interaction.response.send_message(f"已移動到您的頻道: {channel.mention}")
                logger.info(f"Bot successfully moved to channel {channel.id} in guild {guild.id}")
                return
            except asyncio.TimeoutError:
                 logger.error(f"Timeout moving bot to channel {channel.id} in guild {guild.id}")
                 await interaction.response.send_message("移動頻道超時，請稍後再試。", ephemeral=True)
                 return
            except Exception as e:
                 logger.exception(f"Error moving bot to channel {channel.id} in guild {guild.id}: {e}")
                 try:
                     await vc.disconnect(force=True)
                     logger.info(f"Force disconnected bot from {vc.channel.name} before joining {channel.name}")
                     del voice_clients[guild.id]
                 except Exception as disconnect_e:
                     logger.error(f"Error force disconnecting bot: {disconnect_e}")

    logger.info(f"Attempting to connect to voice channel {channel.id} in guild {guild.id}")
    try:
        await interaction.response.defer(ephemeral=False)
        voice_client = await channel.connect(timeout=60.0, reconnect=True)
        voice_clients[guild.id] = voice_client
        await interaction.followup.send(f"成功加入語音頻道: {channel.mention}")
        logger.info(f"Bot successfully joined voice channel: {channel.name} (ID: {channel.id}) in guild {guild.id}")

    except asyncio.TimeoutError:
        logger.error(f"Timed out connecting to voice channel {channel.name} (ID: {channel.id}) in guild {guild.id}")
        try:
            await interaction.followup.send("加入語音頻道超時，請檢查我的權限或稍後再試。", ephemeral=True)
        except discord.NotFound:
             await interaction.channel.send("加入語音頻道超時。")
    except discord.errors.ClientException as e:
        logger.error(f"ClientException joining voice channel {channel.id} in guild {guild.id}: {e}")
        if "Already connected" in str(e):
             existing_vc = discord.utils.get(bot.voice_clients, guild=guild)
             if existing_vc and existing_vc.is_connected():
                 voice_clients[guild.id] = existing_vc
                 await interaction.followup.send(f"我似乎已經在語音頻道 {existing_vc.channel.mention} 中了。", ephemeral=True)
             else:
                 await interaction.followup.send(f"加入語音頻道時發生客戶端錯誤 (可能已連接但狀態未同步): {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"加入語音頻道時發生客戶端錯誤: {e}", ephemeral=True)
    except discord.errors.Forbidden:
         logger.error(f"Permission error: Cannot join voice channel {channel.id} in guild {guild.id}. Check permissions (Connect, Speak).")
         await interaction.followup.send(f"我沒有權限加入頻道 {channel.mention}。請檢查我的「連接」和「說話」權限。", ephemeral=True)
    except Exception as e:
        logger.exception(f"Unexpected error joining voice channel {channel.name} (ID: {channel.id}) in guild {guild.id}: {e}")
        try:
            await interaction.followup.send(f"加入語音頻道時發生未預期的錯誤。", ephemeral=True)
        except discord.NotFound:
            await interaction.channel.send("加入語音頻道時發生未預期的錯誤。")


@bot.tree.command(name='leave', description="讓機器人離開目前的語音頻道")
@app_commands.guild_only()
async def leave(interaction: discord.Interaction):
    """讓機器人離開語音頻道"""
    guild = interaction.guild
    guild_id = guild.id
    logger.info(f"User {interaction.user.id} requested leave in guild {guild_id}")

    voice_client = voice_clients.get(guild_id)

    if voice_client and voice_client.is_connected():
        channel_name = voice_client.channel.name
        logger.info(f"Bot is connected to {channel_name} in guild {guild_id}. Attempting to disconnect.")
        await interaction.response.defer(ephemeral=False)
        try:
            if voice_client.is_playing():
                voice_client.stop()
                logger.info(f"Stopped playback before leaving channel {channel_name}")
            await voice_client.disconnect(force=False)
            logger.info(f"Bot successfully disconnected from voice channel: {channel_name} in guild {guild_id}")
            await interaction.followup.send(f"已離開語音頻道: {channel_name}。")
        except Exception as e:
            logger.exception(f"Error during disconnecting from {channel_name} in guild {guild_id}: {e}")
            await interaction.followup.send(f"離開頻道時發生錯誤，但我會盡力斷開。", ephemeral=True)
            try:
                await voice_client.disconnect(force=True)
            except Exception as force_e:
                 logger.error(f"Error force disconnecting: {force_e}")
        finally:
             if guild_id in voice_clients:
                 del voice_clients[guild_id]
                 logger.debug(f"Removed voice client entry for guild {guild_id}")

    else:
        vc = discord.utils.get(bot.voice_clients, guild=guild)
        if vc and vc.is_connected():
            channel_name = vc.channel.name
            logger.warning(f"Voice client for guild {guild_id} not in local dict, but found active connection in discord.py's list (Channel: {channel_name}). Forcing disconnect.")
            await interaction.response.defer(ephemeral=False)
            try:
                if vc.is_playing():
                    vc.stop()
                await vc.disconnect(force=True)
                logger.info(f"Forcefully disconnected bot from voice channel {channel_name} in guild {guild_id} due to inconsistency.")
                await interaction.followup.send(f"已強制離開語音頻道: {channel_name} (狀態同步可能有點問題)。")
            except Exception as e:
                 logger.exception(f"Error force disconnecting inconsistent VC from {channel_name}: {e}")
                 await interaction.followup.send(f"嘗試強制離開頻道 {channel_name} 時發生錯誤。", ephemeral=True)
            finally:
                 if guild_id in voice_clients:
                     del voice_clients[guild_id]
        else:
            logger.info(f"User {interaction.user.id} used /leave, but bot was not in a voice channel in guild {guild_id}.")
            await interaction.response.send_message("我目前不在任何語音頻道中。", ephemeral=True)


async def play_tts(voice_client: discord.VoiceClient, text: str, context: str = "Unknown"):
    """使用 edge-tts 生成語音並在語音頻道中播放，同時記錄時間"""
    if not voice_client or not voice_client.is_connected():
        logger.warning(f"play_tts called but voice_client is invalid or not connected (Context: {context}).")
        return

    guild_id = voice_client.guild.id
    logger.info(f"[TTS-{guild_id}-{context}] Starting TTS playback for text: '{text[:50]}...'")
    start_time = time.time()

    tmp_path = None
    source = None
    step1_duration = 0
    step2_duration = 0
    step3_call_duration = 0
    time_between_1_and_2 = 0
    time_between_2_and_3 = 0

    try:
        step1_start = time.time()
        communicate = edge_tts.Communicate(text, DEFAULT_VOICE)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file_obj:
            tmp_path = tmp_file_obj.name

        await communicate.save(tmp_path)

        step1_end = time.time()
        step1_duration = step1_end - step1_start
        logger.info(f"[TTS-{guild_id}-{context}] Step 1 (Generate & Save) took: {step1_duration:.4f} seconds. File: {tmp_path}")

        step2_start = time.time()
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
             logger.error(f"[TTS-{guild_id}-{context}] Error: Temporary TTS file is missing or empty at {tmp_path}")
             if tmp_path and os.path.exists(tmp_path):
                 try: os.remove(tmp_path)
                 except OSError as e: logger.error(f"Error removing empty temp file {tmp_path}: {e}")
             return

        ffmpeg_options = {
            'options': '-vn',
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }
        source = FFmpegPCMAudio(tmp_path, **ffmpeg_options)
        step2_end = time.time()
        step2_duration = step2_end - step2_start
        logger.info(f"[TTS-{guild_id}-{context}] Step 2 (Create Source) took: {step2_duration:.4f} seconds.")

        step3_start = time.time()

        def after_playing(error, path_to_delete=tmp_path, start_time_cb=start_time, step3_start_cb=step3_start):
            callback_end_time = time.time()
            playback_duration = callback_end_time - step3_start_cb
            total_duration = callback_end_time - start_time_cb

            if error:
                logger.error(f"[TTS-{guild_id}-{context}] Playback error: {error}")
            else:
                logger.info(f"[TTS-{guild_id}-{context}] Playback finished successfully.")

            logger.info(f"[TTS-{guild_id}-{context}] Step 3 (Playback Duration) approx: {playback_duration:.4f} seconds.")
            logger.info(f"[TTS-{guild_id}-{context}] Total time (Start to Playback End): {total_duration:.4f} seconds.")

            if path_to_delete and os.path.exists(path_to_delete):
                step4_start = time.time()
                try:
                    os.remove(path_to_delete)
                    step4_end = time.time()
                    step4_duration = step4_end - step4_start
                    logger.info(f"[TTS-{guild_id}-{context}] Step 4 (Cleanup) took: {step4_duration:.4f} seconds. Removed: {path_to_delete}")
                except OSError as e:
                    logger.error(f"[TTS-{guild_id}-{context}] Error removing temporary file {path_to_delete}: {e}")
            elif path_to_delete:
                 logger.warning(f"[TTS-{guild_id}-{context}] Temporary file {path_to_delete} was already removed or not found during cleanup.")

        if voice_client.is_playing():
            logger.warning(f"[TTS-{guild_id}-{context}] Voice client is already playing. Stopping previous playback.")
            voice_client.stop()
            await asyncio.sleep(0.2)

        voice_client.play(source, after=after_playing)
        step3_end_call = time.time()
        step3_call_duration = step3_end_call - step3_start
        logger.info(f"[TTS-{guild_id}-{context}] Step 3 (Initiate Playback) call took: {step3_call_duration:.4f} seconds. Playback started in background.")

        time_between_1_and_2 = step2_start - step1_end
        time_between_2_and_3 = step3_start - step2_end
        logger.info(f"[TTS-{guild_id}-{context}] Time between Step 1 and 2: {time_between_1_and_2:.4f} seconds.")
        logger.info(f"[TTS-{guild_id}-{context}] Time between Step 2 and 3: {time_between_2_and_3:.4f} seconds.")

    except FileNotFoundError:
         logger.error(f"[TTS-{guild_id}-{context}] FFmpeg executable not found. Please ensure FFmpeg is installed and in the system's PATH.")
         if tmp_path and os.path.exists(tmp_path):
             try: os.remove(tmp_path)
             except OSError as e: logger.error(f"Error removing temp file after FileNotFoundError: {e}")
    except Exception as e:
        logger.exception(f"[TTS-{guild_id}-{context}] Unexpected error during TTS playback: {e}")
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except OSError as e: logger.error(f"Error removing temp file after unexpected error: {e}")


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """監聽成員語音狀態變化，用於播放加入/離開提示音"""
    guild = member.guild
    guild_id = guild.id

    bot_voice_client = voice_clients.get(guild_id)
    if member.id == bot.user.id or not bot_voice_client or not bot_voice_client.is_connected():
        return

    bot_channel = bot_voice_client.channel

    if before.channel != bot_channel and after.channel == bot_channel:
        user_name = member.display_name
        logger.info(f"User '{user_name}' (ID: {member.id}) joined voice channel '{after.channel.name}' (ID: {after.channel.id}) where the bot is in guild {guild_id}.")
        if len(bot_channel.members) > 1:
            tts_message = f"{user_name} 加入了頻道"
            await asyncio.sleep(0.5)
            await play_tts(bot_voice_client, tts_message, context="User Join Notification")
        else:
            logger.info(f"Skipping join notification for {user_name} as they are the first user with the bot.")

    elif before.channel == bot_channel and after.channel != bot_channel:
        user_name = member.display_name
        logger.info(f"User '{user_name}' (ID: {member.id}) left voice channel '{before.channel.name}' (ID: {before.channel.id}) where the bot was in guild {guild_id}.")
        if bot.user in before.channel.members and len(before.channel.members) > 0:
             tts_message = f"{user_name} 離開了頻道"
             await asyncio.sleep(0.5)
             await play_tts(bot_voice_client, tts_message, context="User Leave Notification")
        else:
             logger.info(f"Skipping leave notification for {user_name} as they might be the last user or bot is no longer in the channel.")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if not message.guild:
        return

    guild = message.guild
    guild_id = guild.id
    channel = message.channel
    author = message.author
    user_id = author.id
    user_name = author.display_name

    if WHITELISTED_SERVERS and guild_id not in WHITELISTED_SERVERS:
        return

    analytics_db_path = get_db_path(guild_id, 'analytics')
    chat_db_path = get_db_path(guild_id, 'chat')
    points_db_path = get_db_path(guild_id, 'points')


    def update_user_message_count(user_id_str, user_name_str, join_date_iso):
        conn = None
        try:
            conn = sqlite3.connect(analytics_db_path, timeout=10)
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, message_count INTEGER DEFAULT 0)")
            c.execute("SELECT message_count FROM users WHERE user_id = ?", (user_id_str,))
            result = c.fetchone()
            if result:
                c.execute("UPDATE users SET message_count = message_count + 1, user_name = ? WHERE user_id = ?", (user_name_str, user_id_str))
            else:
                join_date_to_insert = join_date_iso if join_date_iso else datetime.now(timezone.utc).isoformat()
                c.execute("INSERT OR IGNORE INTO users (user_id, user_name, join_date, message_count) VALUES (?, ?, ?, ?)", (user_id_str, user_name_str, join_date_to_insert, 1))
            conn.commit()
        except sqlite3.Error as e: logger.exception(f"DB error in update_user_message_count for user {user_id_str} in guild {guild_id}: {e}")
        finally:
            if conn: conn.close()

    def update_token_in_db(total_token_count, userid_str, channelid_str):
        if not total_token_count or not userid_str or not channelid_str:
            logger.warning(f"Missing data for update_token_in_db (guild {guild_id}): tokens={total_token_count}, user={userid_str}, channel={channelid_str}")
            return
        conn = None
        try:
            conn = sqlite3.connect(analytics_db_path, timeout=10)
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        userid TEXT UNIQUE,
                        total_token_count INTEGER,
                        channelid TEXT)""")
            c.execute("""INSERT INTO metadata (userid, total_token_count, channelid)
                         VALUES (?, ?, ?)
                         ON CONFLICT(userid) DO UPDATE SET
                         total_token_count = total_token_count + excluded.total_token_count,
                         channelid = excluded.channelid""",
                      (userid_str, total_token_count, channelid_str))
            conn.commit()
            logger.debug(f"Updated token count for user {userid_str} in guild {guild_id}. Added: {total_token_count}")
        except sqlite3.Error as e: logger.exception(f"DB error in update_token_in_db for user {userid_str} in guild {guild_id}: {e}")
        finally:
            if conn: conn.close()

    def store_message(user_str, content_str, timestamp_str):
        if not content_str: return
        conn = None
        try:
            conn = sqlite3.connect(chat_db_path, timeout=10)
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS message (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, content TEXT, timestamp TEXT)")
            c.execute("INSERT INTO message (user, content, timestamp) VALUES (?, ?, ?)", (user_str, content_str, timestamp_str))
            c.execute("DELETE FROM message WHERE id NOT IN (SELECT id FROM message ORDER BY id DESC LIMIT 60)")
            conn.commit()
            logger.debug(f"Stored message from '{user_str}' in chat history for guild {guild_id}")
        except sqlite3.Error as e: logger.exception(f"DB error in store_message for guild {guild_id}: {e}")
        finally:
            if conn: conn.close()

    def get_chat_history():
        conn = None
        history = []
        try:
            conn = sqlite3.connect(chat_db_path, timeout=10)
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS message (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, content TEXT, timestamp TEXT)")
            c.execute("SELECT user, content, timestamp FROM message ORDER BY id ASC LIMIT 60")
            rows = c.fetchall()
            history = rows
            logger.debug(f"Retrieved {len(history)} messages from chat history for guild {guild_id}")
        except sqlite3.Error as e: logger.exception(f"DB error in get_chat_history for guild {guild_id}: {e}")
        finally:
            if conn: conn.close()
        return history

    def get_user_points(user_id_str, user_name_str=None, join_date_iso=None):
        conn = None
        points = 0
        try:
            conn = sqlite3.connect(points_db_path, timeout=10)
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, points INTEGER DEFAULT {default_points})")
            cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id_str,))
            result = cursor.fetchone()
            if result:
                points = int(result[0])
            elif default_points >= 0 and user_name_str:
                join_date_to_insert = join_date_iso if join_date_iso else datetime.now(timezone.utc).isoformat()
                logger.info(f"User {user_name_str} (ID: {user_id_str}) not found in points DB (guild {guild_id}). Creating with {default_points} points.")
                cursor.execute('INSERT OR IGNORE INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)', (user_id_str, user_name_str, join_date_to_insert, default_points))
                cursor.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, points INTEGER, reason TEXT, timestamp TEXT)")
                if default_points > 0:
                    cursor.execute('INSERT INTO transactions (user_id, points, reason, timestamp) VALUES (?, ?, ?, ?)', (user_id_str, default_points, "初始贈送點數", get_current_time_utc8()))
                conn.commit()
                points = default_points
            else:
                 logger.debug(f"User {user_id_str} not found in points DB (guild {guild_id}) and default points are negative. Returning 0 points.")

        except sqlite3.Error as e: logger.exception(f"DB error in get_user_points for user {user_id_str} in guild {guild_id}: {e}")
        except ValueError: logger.error(f"Value error converting points for user {user_id_str} in guild {guild_id}.")
        finally:
            if conn: conn.close()
        return points

    def deduct_points(user_id_str, points_to_deduct, reason="與機器人互動扣點"):
        if points_to_deduct <= 0: return get_user_points(user_id_str)
        conn = None
        current_points = get_user_points(user_id_str)
        try:
            conn = sqlite3.connect(points_db_path, timeout=10)
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, points INTEGER DEFAULT {default_points})")
            cursor.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, points INTEGER, reason TEXT, timestamp TEXT)")

            cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id_str,))
            result = cursor.fetchone()
            if not result:
                logger.warning(f"User {user_id_str} not found in points DB for deduction (guild {guild_id}). Cannot deduct points.")
                return 0

            current_points_db = int(result[0])
            if current_points_db < points_to_deduct:
                logger.warning(f"User {user_id_str} has insufficient points ({current_points_db}) to deduct {points_to_deduct} in guild {guild_id}.")
                return current_points_db

            new_points = current_points_db - points_to_deduct
            cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, user_id_str))
            cursor.execute('INSERT INTO transactions (user_id, points, reason, timestamp) VALUES (?, ?, ?, ?)', (user_id_str, -points_to_deduct, reason, get_current_time_utc8()))
            conn.commit()
            logger.info(f"Deducted {points_to_deduct} points from user {user_id_str} for '{reason}' in guild {guild_id}. New balance: {new_points}")
            return new_points
        except sqlite3.Error as e: logger.exception(f"DB error in deduct_points for user {user_id_str} in guild {guild_id}: {e}")
        finally:
            if conn: conn.close()
        return current_points


    conn_analytics_msg = None
    try:
        conn_analytics_msg = sqlite3.connect(analytics_db_path, timeout=10)
        c_analytics_msg = conn_analytics_msg.cursor()
        c_analytics_msg.execute("CREATE TABLE IF NOT EXISTS messages (message_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_name TEXT, channel_id TEXT, timestamp TEXT, content TEXT)")
        msg_time_utc = message.created_at.astimezone(timezone.utc).isoformat()
        c_analytics_msg.execute("INSERT INTO messages (user_id, user_name, channel_id, timestamp, content) VALUES (?, ?, ?, ?, ?)",
                                (str(user_id), user_name, str(channel.id), msg_time_utc, message.content))
        conn_analytics_msg.commit()
    except sqlite3.Error as e: logger.exception(f"DB error inserting message into analytics table for guild {guild_id}: {e}")
    finally:
        if conn_analytics_msg: conn_analytics_msg.close()

    join_date_iso = None
    if isinstance(author, discord.Member) and author.joined_at:
        try:
            join_date_iso = author.joined_at.astimezone(timezone.utc).isoformat()
        except Exception as e: logger.error(f"Error converting join date for user {user_id} in guild {guild_id}: {e}")
    update_user_message_count(str(user_id), user_name, join_date_iso)


    should_respond = False
    target_channel_ids = []

    if isinstance(TARGET_CHANNEL_ID, (list, tuple)):
        target_channel_ids = [str(cid) for cid in TARGET_CHANNEL_ID]
    elif isinstance(TARGET_CHANNEL_ID, (str, int)):
        target_channel_ids = [str(TARGET_CHANNEL_ID)]
    elif isinstance(TARGET_CHANNEL_ID, dict):
        target_channel_ids = [str(cid) for cid in TARGET_CHANNEL_ID.get(guild_id, [])]

    if bot.user.mentioned_in(message) and not message.mention_everyone:
        should_respond = True
        logger.debug(f"Responding in guild {guild_id}: Bot mentioned by {user_name} ({user_id})")
    elif message.reference and message.reference.resolved:
        if isinstance(message.reference.resolved, discord.Message) and message.reference.resolved.author == bot.user:
            should_respond = True
            logger.debug(f"Responding in guild {guild_id}: User {user_id} replied to bot's message")
    elif bot_name and bot_name in message.content:
        should_respond = True
        logger.debug(f"Responding in guild {guild_id}: Bot name '{bot_name}' mentioned by {user_id}")
    elif str(channel.id) in target_channel_ids:
        should_respond = True
        logger.debug(f"Responding in guild {guild_id}: Message in target channel {channel.id} by {user_id}")

    if should_respond:
        if model is None:
            logger.warning(f"AI model is not available. Cannot respond to message from {user_id} in guild {guild_id}.")
            return

        if Point_deduction_system > 0:
            user_points = get_user_points(str(user_id), user_name, join_date_iso)
            if user_points < Point_deduction_system:
                try:
                    await message.reply(f"抱歉，您的點數 ({user_points}) 不足本次互動所需的 {Point_deduction_system} 點。", mention_author=False)
                    logger.info(f"User {user_name} ({user_id}) in guild {guild_id} has insufficient points ({user_points}/{Point_deduction_system})")
                except discord.HTTPException as e: logger.error(f"Error replying about insufficient points to {user_id}: {e}")
                return
            else:
                deduct_points(str(user_id), Point_deduction_system)

        async with channel.typing():
            try:
                current_timestamp_utc8 = get_current_time_utc8()
                initial_prompt = (
                    f"{bot_name}是一位來自台灣的智能陪伴機器人..."
                    f"現在的時間是:{current_timestamp_utc8} (UTC+8)。"
                    f"請記住@{bot.user.id}是你的Discord ID。"
                    f"當使用者 @{bot.user.display_name} 或提及其名稱 '{bot_name}' 時，就是在跟你說話。"
                    f"請務必用 **繁體中文** 回答。"
                    f"如果使用者想搜尋網路或瀏覽網頁，請建議他們使用 `/search` 或 `/aibrowse` 指令。"
                )
                initial_response = (
                    f"好的，我知道了。我是{bot_name}，一位來自台灣，運用DBT技巧的智能陪伴機器人..."
                )

                chat_history_raw = get_chat_history()
                chat_history_processed = [
                    {"role": "user", "parts": [{"text": initial_prompt}]},
                    {"role": "model", "parts": [{"text": initial_response}]},
                ]

                for row in chat_history_raw:
                    db_user, db_content, db_timestamp = row
                    if db_content:
                        role = "user" if db_user != bot_name else "model"
                        message_text = f"[{db_timestamp}] {db_user}: {db_content}" if role == 'user' else db_content

                        chat_history_processed.append({"role": role, "parts": [{"text": message_text}]})
                    else:
                        logger.warning(f"Skipping empty message in chat history (guild {guild_id}) from user {db_user} at {db_timestamp}")

                if debug:
                    logger.debug(f"--- Chat History for API (Guild: {guild_id}) ---")
                    for entry in chat_history_processed[-5:]:
                         logger.debug(f"Role: {entry['role']}, Parts: {str(entry['parts'])[:100]}...")
                    logger.debug("--- End Chat History ---")
                    logger.debug(f"Current User Message (Guild: {guild_id}): {message.content}")

                chat = model.start_chat(history=chat_history_processed)
                current_user_message_formatted = message.content

                api_response_text = ""
                total_token_count = None

                try:
                    response = await chat.send_message_async(
                        current_user_message_formatted,
                        stream=False,
                        safety_settings={
                            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                        },
                    )

                    if response.prompt_feedback and response.prompt_feedback.block_reason:
                        block_reason = response.prompt_feedback.block_reason
                        logger.warning(f"Gemini API blocked prompt for user {user_id} in guild {guild_id}. Reason: {block_reason}")
                        await message.reply("抱歉，您的訊息可能包含不當內容，我無法處理。", mention_author=False)
                        return

                    if not response.candidates:
                        finish_reason = 'UNKNOWN'
                        safety_ratings = 'N/A'
                        try:
                            if hasattr(response, 'candidates') and response.candidates:
                                candidate = response.candidates[0]
                                finish_reason = getattr(candidate, 'finish_reason', 'UNKNOWN')
                                if hasattr(candidate, 'safety_ratings'):
                                     safety_ratings = [(r.category, r.probability) for r in candidate.safety_ratings]
                            else:
                                finish_reason = getattr(response.prompt_feedback, 'block_reason', 'NO_CANDIDATES')
                                if hasattr(response.prompt_feedback, 'safety_ratings'):
                                     safety_ratings = [(r.category, r.probability) for r in response.prompt_feedback.safety_ratings]

                        except Exception as fr_err:
                            logger.error(f"Error accessing finish_reason/safety_ratings: {fr_err}")

                        logger.warning(f"No candidates returned from Gemini API for user {user_id} in guild {guild_id}. Finish Reason: {finish_reason}, Safety Ratings: {safety_ratings}")
                        reply_message = "抱歉，我暫時無法產生回應"
                        if finish_reason == 'SAFETY':
                            reply_message += "，因為可能觸發了安全限制。"
                        elif finish_reason == 'RECITATION':
                             reply_message += "，因為回應可能包含受版權保護的內容。"
                        elif finish_reason == 'MAX_TOKENS':
                             reply_message = "呃，我好像說得太多了，無法產生完整的的回應。"
                        else:
                            reply_message += "，請稍後再試。"
                        await message.reply(reply_message, mention_author=False)
                        return

                    api_response_text = response.text.strip()
                    logger.info(f"Gemini API response received for user {user_id} in guild {guild_id}. Length: {len(api_response_text)}")
                    if debug: logger.debug(f"Gemini Response Text (Guild {guild_id}): {api_response_text[:200]}...")

                    try:
                        usage_metadata = getattr(response, 'usage_metadata', None)
                        if usage_metadata:
                             prompt_token_count = getattr(usage_metadata, 'prompt_token_count', 0)
                             candidates_token_count = getattr(usage_metadata, 'candidates_token_count', 0)
                             total_token_count = getattr(usage_metadata, 'total_token_count', None)
                             if total_token_count is None:
                                 total_token_count = prompt_token_count + candidates_token_count
                             logger.info(f"Token usage (Guild {guild_id}): Prompt={prompt_token_count}, Candidates={candidates_token_count}, Total={total_token_count}")
                        else:
                            if response.candidates and hasattr(response.candidates[0], 'token_count') and response.candidates[0].token_count:
                                total_token_count = response.candidates[0].token_count
                                logger.info(f"Total token count from candidate (fallback, Guild {guild_id}): {total_token_count}")
                            else:
                                logger.warning(f"Could not find token count in API response (Guild {guild_id}).")

                        if total_token_count is not None and total_token_count > 0:
                            update_token_in_db(total_token_count, str(user_id), str(channel.id))
                        else:
                             logger.warning(f"Token count is {total_token_count}, not updating DB for user {user_id} in guild {guild_id}.")

                    except AttributeError as attr_err:
                        logger.error(f"Attribute error processing token count (Guild {guild_id}): {attr_err}. Response structure might have changed.")
                    except Exception as token_error:
                        logger.error(f"Error processing token count (Guild {guild_id}): {token_error}")

                    store_message(user_name, message.content, current_timestamp_utc8)
                    if api_response_text:
                        store_message(bot_name, api_response_text, get_current_time_utc8())

                    if api_response_text:
                        if len(api_response_text) > 2000:
                            logger.warning(f"API reply exceeds 2000 characters ({len(api_response_text)}) for guild {guild_id}. Splitting.")
                            parts = []
                            current_part = ""
                            lines = api_response_text.split('\n')
                            for line in lines:
                                if len(current_part) + len(line) + 1 > 1990:
                                    if current_part:
                                        parts.append(current_part)
                                    if len(line) > 1990:
                                         for i in range(0, len(line), 1990):
                                             parts.append(line[i:i+1990])
                                         current_part = ""
                                    else:
                                         current_part = line
                                else:
                                     if current_part:
                                         current_part += "\n" + line
                                     else:
                                         current_part = line
                            if current_part:
                                parts.append(current_part)

                            first_part = True
                            for i, part in enumerate(parts):
                                part_to_send = part.strip()
                                if not part_to_send: continue
                                try:
                                    if first_part:
                                        await message.reply(part_to_send, mention_author=False)
                                        first_part = False
                                    else:
                                        await channel.send(part_to_send)
                                    logger.info(f"Sent part {i+1}/{len(parts)} of long reply to guild {guild_id}.")
                                    await asyncio.sleep(0.5)
                                except discord.HTTPException as send_e:
                                     logger.error(f"Error sending part {i+1} of long reply in guild {guild_id}: {send_e}")
                                     break
                        else:
                            await message.reply(api_response_text, mention_author=False)
                            logger.info(f"Sent reply to user {user_id} in guild {guild_id}.")

                        guild_voice_client = voice_clients.get(guild_id)
                        if guild_voice_client and guild_voice_client.is_connected():
                            tts_text_cleaned = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', api_response_text)
                            tts_text_cleaned = re.sub(r'[*_`~]', '', tts_text_cleaned)
                            tts_text_cleaned = re.sub(r'<@!?\d+>', '', tts_text_cleaned)
                            tts_text_cleaned = re.sub(r'<#\d+>', '', tts_text_cleaned)
                            tts_text_cleaned = re.sub(r'http[s]?://\S+', '網址', tts_text_cleaned)
                            tts_text_cleaned = re.sub(r'\s+', ' ', tts_text_cleaned).strip()

                            if tts_text_cleaned:
                                logger.info(f"Queueing TTS playback for AI reply in guild {guild_id}.")
                                await play_tts(guild_voice_client, tts_text_cleaned, context="AI Reply")
                            else:
                                logger.info(f"Skipping TTS for AI reply in guild {guild_id} after cleaning resulted in empty text.")
                    else:
                        logger.warning(f"Gemini API returned empty text response for user {user_id} in guild {guild_id}.")
                        await message.reply("嗯...我好像不知道該說什麼。", mention_author=False)

                except genai.types.BlockedPromptException as e:
                    logger.warning(f"Gemini API blocked prompt (send_message) for user {user_id} in guild {guild_id}: {e}")
                    await message.reply("抱歉，您的訊息觸發了內容限制，我無法處理。", mention_author=False)
                except genai.types.StopCandidateException as e:
                    logger.warning(f"Gemini API stopped candidate generation (send_message) for user {user_id} in guild {guild_id}: {e}")
                    await message.reply("抱歉，產生回應時似乎被中斷了，請稍後再試。", mention_author=False)
                except Exception as api_call_e:
                    logger.exception(f"Error during Gemini API interaction for user {user_id} in guild {guild_id}: {api_call_e}")
                    await message.reply(f"與 AI 核心通訊時發生錯誤，請稍後再試。", mention_author=False)

            except discord.errors.HTTPException as e:
                if e.status == 403:
                    logger.error(f"Permission error (403) in channel {channel.id} (guild {guild_id}) or for user {user_id}: {e.text}")
                    try:
                        await author.send(f"我在頻道 <#{channel.id}> 中似乎缺少回覆訊息的權限，請檢查設定。")
                    except discord.errors.Forbidden:
                        logger.error(f"Failed to DM user {user_id} about permission error in guild {guild_id}.")
                else:
                    logger.exception(f"HTTPException occurred while processing message for user {user_id} in guild {guild_id}: {e}")
            except Exception as e:
                logger.exception(f"An unexpected error occurred in on_message processing for user {user_id} in guild {guild_id}: {e}")
                try:
                    await message.reply("處理您的訊息時發生未預期的錯誤。", mention_author=False)
                except Exception as reply_err:
                    logger.error(f"Failed to send error reply message in guild {guild_id}: {reply_err}")


def bot_run():
    """包含啟動機器人所需的主要邏輯"""
    if not discord_bot_token:
        logger.critical("Discord bot token is not configured in nana_bot.py! Bot cannot start.")
        return
    if not API_KEY:
        logger.warning("Gemini API key is not set in nana_bot.py! AI features will be disabled.")


    logger.info("Attempting to start the bot...")
    try:
        bot.run(discord_bot_token, log_handler=None, reconnect=True)
    except discord.errors.LoginFailure:
        logger.critical("Login Failed: Invalid Discord Token provided.")
    except discord.PrivilegedIntentsRequired:
         logger.critical("Privileged Intents (like Members or Presence) are required but not enabled in the Discord Developer Portal.")
    except discord.HTTPException as e:
        logger.critical(f"Failed to connect to Discord due to HTTP error: {e}")
    except Exception as e:
        logger.critical(f"Critical error running the bot: {e}", exc_info=True)
    finally:
        logger.info("Bot process has stopped.")


if __name__ == "__main__":
    logger.info("Starting bot from main execution block...")
    bot_run()
    logger.info("Bot execution finished.")

__all__ = ['bot_run', 'bot']
