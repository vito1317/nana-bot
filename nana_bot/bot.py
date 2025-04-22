# coding=utf-8
import asyncio
import traceback
import discord
from discord import app_commands, FFmpegPCMAudio
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
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
from search_engine_tool_vito1317 import google, bing, yahoo
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
import tempfile
import shutil
from gtts import gTTS


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_current_time_utc8():
    utc8 = timezone(timedelta(hours=8))
    current_time = datetime.now(utc8)
    return current_time.strftime("%Y-%m-%d %H:%M:%S")


genai.configure(api_key=API_KEY)
not_reviewed_role_id = not_reviewed_id
model = genai.GenerativeModel(gemini_model)
send_daily_channel_id = send_daily_channel_id_list

voice_clients = {}


def bot_run():
    @tasks.loop(hours=24)
    async def send_daily_message():
        for idx, server_id in enumerate(servers):
            send_daily_channel_id = send_daily_channel_id_list[idx]
            not_reviewed_role_id = not_reviewed_id[idx]
            channel = bot.get_channel(send_daily_channel_id)
            if channel:
                try:
                    await channel.send(
                        f"<@&{not_reviewed_role_id}> 各位未審核的人，快來這邊審核喔"
                    )
                except discord.DiscordException as e:
                    logger.error(f"Error sending daily message: {e}")


    @bot.event
    async def on_ready():
        db_tables = {
            "users": "user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, message_count INTEGER DEFAULT 0",
            "messages": "message_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_name TEXT, channel_id TEXT, timestamp TEXT, content TEXT",
            "message": "id INTEGER PRIMARY KEY, user TEXT, content TEXT, timestamp TEXT",
            "metadata": """id INTEGER PRIMARY KEY AUTOINCREMENT,
                           userid TEXT UNIQUE,
                           total_token_count INTEGER,
                           channelid TEXT"""
        }

        guild_count = 0
        for guild in bot.guilds:
            guild_count += 1
            logger.info(f"Bot is in server: {guild.name} (ID: {guild.id})")

            init_db(f"analytics_server_{guild.id}.db", db_tables)
            init_db(f"messages_chat_{guild.id}.db", {"message": db_tables["message"]})
            init_db(f"points_{guild.id}.db", {
                 "users": "user_id TEXT PRIMARY KEY, user_name TEXT, join_date TEXT, points INTEGER DEFAULT " + str(default_points),
                 "transactions": "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, points INTEGER DEFAULT " + str(default_points) + ", reason TEXT, timestamp TEXT"
            })

            guild_obj = discord.Object(id=guild.id)
            bot.tree.copy_global_to(guild=guild_obj)
            try:
                slash = await bot.tree.sync(guild=guild_obj)
                print(f"目前登入身份 --> {bot.user}")
                print(f"在 {guild.name} 載入 {len(slash)} 個斜線指令")
            except discord.errors.Forbidden:
                 logger.warning(f"無法在 {guild.name} (ID: {guild.id}) 同步指令，可能缺少權限。")
            except Exception as e:
                 logger.exception(f"在 {guild.name} 同步指令時發生錯誤: {e}")


        send_daily_message.start()
        activity = discord.Game(name=f"正在{guild_count}個server上工作...")
        await bot.change_presence(status=discord.Status.online, activity=activity)


    @bot.event
    async def on_member_join(member):
        logger.info(f"New member joined: {member} in server ID: {member.guild.id}")
        server_id = member.guild.id

        for idx, s_id in enumerate(servers):
            if server_id == s_id:
                channel_id = welcome_channel_id[idx]
                role_id = not_reviewed_id[idx]
                newcomer_review_channel_id = newcomer_channel_id[idx]

                channel = bot.get_channel(channel_id)
                if not channel:
                    logger.warning(f"Welcome channel not found for server {server_id}")
                    return

                role = member.guild.get_role(role_id)
                if not role:
                    logger.warning(f"Role {role_id} not found in server {server_id}")

                db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases", f"analytics_server_{server_id}.db")
                conn_user_join = None
                try:
                    conn_user_join = sqlite3.connect(db_path)
                    c_user_join = conn_user_join.cursor()
                    c_user_join.execute(
                        "INSERT OR IGNORE INTO users (user_id, user_name, join_date, message_count) VALUES (?, ?, ?, ?)",
                        (str(member.id), member.name, member.joined_at.replace(tzinfo=None).isoformat(), 0),
                    )
                    conn_user_join.commit()
                except sqlite3.Error as e:
                    logger.exception(f"Database error on member join (analytics): {e}")
                finally:
                    if conn_user_join:
                        conn_user_join.close()

                points_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases", f"points_{server_id}.db")
                conn_points_join = None
                try:
                    conn_points_join = sqlite3.connect(points_db_path)
                    c_points_join = conn_points_join.cursor()
                    c_points_join.execute("SELECT user_id FROM users WHERE user_id = ?", (str(member.id),))
                    if not c_points_join.fetchone() and default_points > 0:
                        join_date_iso = member.joined_at.replace(tzinfo=None).isoformat() if member.joined_at else None
                        c_points_join.execute(
                            "INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)",
                            (str(member.id), member.name, join_date_iso, default_points)
                        )
                        c_points_join.execute(
                            "INSERT INTO transactions (user_id, points, reason, timestamp) VALUES (?, ?, ?, ?)",
                            (str(member.id), default_points, "初始贈送點數", get_current_time_utc8())
                        )
                        conn_points_join.commit()
                        logger.info(f"Gave initial {default_points} points to new member {member.name} (ID: {member.id}) in server {server_id}")
                except sqlite3.Error as e:
                    logger.exception(f"Database error on member join (points): {e}")
                finally:
                    if conn_points_join:
                        conn_points_join.close()

                if role:
                    try:
                        await member.add_roles(role)
                    except discord.HTTPException as e:
                        logger.error(f"Failed to add role to member {member.name} (ID: {member.id}): {e}")

                try:
                    responses = model.generate_content(
                        [
                            f"{bot_name}是一位來自台灣的智能陪伴機器人，(請注意，她僅能提供意見，不能代替真正專業的諮商師)，她能夠使用繁體中文與用戶進行對話。她擅長傾聽，用溫暖和理解的方式回應用戶，並且能夠提供專業的建議和支持。無論是情感問題、生活困擾，還是尋求一般建議，且你({bot_name})非常擅長(DBT辯證行為治療)，並對使用者使用(DBT辯證行為治療)，{bot_name}都會以友善且專業的態度來協助用戶。當用戶表示聽不懂時，她會嘗試用不同的方式來解釋，而不是簡單重複原本的說法，並盡量避免重複相似的話題或句子。她的回應會盡量口語化，避免像AI或維基百科式的回話方式，每次回覆會盡量控制在三個段落以內，並且排版易於閱讀。，同時她會提供意見大於詢問問題，避免一直詢問用戶。且請務必用繁體中文來回答，請不要回覆這則訊息",
                            f"你現在要做的事是歡迎使用者{member.mention}的加入並且引導使用者使用系統，同時也可以請你自己做一下自我介紹(以你{bot_name}的身分做自我介紹而不是請使用者做自我介紹)，同時，請不要詢問使用者想要聊聊嗎、想要聊什麼之類的話。同時也請不要回覆這則訊息。",
                            f"第二步是tag <#{newcomer_review_channel_id}> 傳送這則訊息進去，這是新人審核頻道，讓使用者進行新人審核，請務必引導使用者講述自己的病症與情況，而不是只傳送 <#{newcomer_review_channel_id}>，請注意，請傳送完整的訊息，包誇<>也需要傳送，同時也請不要回覆這則訊息，請勿傳送指令或命令使用者，也並不是請你去示範，也不是請他跟你分享要聊什麼，也請不要請新人(使用者)與您分享相關訊息",
                            f"新人審核格式包誇(```{review_format}```)，example(僅為範例，請勿照抄):(你好！歡迎加入{member.guild.name}，很高興認識你！我叫{bot_name}，是你們的心理支持輔助機器人。如果你有任何情感困擾、生活問題，或是需要一點建議，都歡迎在審核後找我聊聊。我會盡力以溫暖、理解的方式傾聽，並給你專業的建議和支持。但在你跟我聊天以前，需要請你先到 <#{newcomer_review_channel_id}> 填寫以下資訊，方便我更好的為你服務！ ```{review_format}```)請記住務必傳送>> ```{review_format}```和<#{newcomer_review_channel_id}> <<",
                        ],
                         safety_settings={
                            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                        }
                    )
                    if channel:
                        embed = discord.Embed(
                            title="歡迎加入", description=responses.text, color=discord.Color.blue()
                        )
                        await channel.send(embed=embed)
                except Exception as e:
                    logger.exception(f"Error generating welcome message for {member.name} (ID: {member.id}): {e}")
                    if channel:
                        try:
                             await channel.send(f"歡迎 {member.mention} 加入！詳細的介紹訊息生成失敗，請先前往 <#{newcomer_review_channel_id}> 進行審核。")
                        except discord.DiscordException as send_error:
                             logger.error(f"Failed to send fallback welcome message: {send_error}")
                break


    @bot.event
    async def on_member_remove(member):
        logger.info(f"Member left: {member} from server ID: {member.guild.id}")
        server_id = member.guild.id

        for idx, s_id in enumerate(servers):
            if server_id == s_id:
                channel_id = member_remove_channel_id[idx]
                channel = bot.get_channel(channel_id)

                if not channel:
                    logger.warning(f"Member remove channel not found for server {server_id}")

                try:
                    leave_time = datetime.now(timezone(timedelta(hours=8)))
                    formatted_time = leave_time.strftime("%Y-%m-%d %H:%M:%S")

                    if channel:
                        if idx == 0:
                            embed = discord.Embed(
                                title="成員退出",
                                description=f"{member.display_name} 已經離開伺服器 (User-Name:{member.name}; User-ID: {member.id}) 離開時間：{formatted_time} UTC+8",
                                color=discord.Color.orange()
                            )
                        else:
                            embed = discord.Embed(
                                title="成員退出",
                                description=f"很可惜，{member.display_name} 已經離去，踏上了屬於他的旅程。\n無論他曾經留下的是愉快還是悲傷，願陽光永遠賜與他溫暖，願月光永遠指引他方向，願星星使他在旅程中不會感到孤單。\n謝謝你曾經也是我們的一員。 (User-Name:{member.name}; User-ID: {member.id}) 離開時間：{formatted_time} UTC+8",
                                color=discord.Color.orange()
                            )
                        try:
                            await channel.send(embed=embed)
                        except discord.DiscordException as send_error:
                             logger.error(f"Failed to send member remove message to channel {channel_id}: {send_error}")

                    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases", f"analytics_server_{server_id}.db")
                    conn_command = None
                    try:
                        conn_command = sqlite3.connect(db_path)
                        c_command = conn_command.cursor()
                        c_command.execute(
                            """
                            CREATE TABLE IF NOT EXISTS users (
                                user_id TEXT PRIMARY KEY,
                                user_name TEXT,
                                join_date TEXT,
                                message_count INTEGER DEFAULT 0
                            )
                            """
                        )
                        c_command.execute(
                            "SELECT message_count, join_date FROM users WHERE user_id = ?",
                            (str(member.id),),
                        )
                        result = c_command.fetchone()

                        if not result:
                            logger.info(f"No data found for {member.name} (ID: {member.id}) in analytics DB.")
                        else:
                            message_count, join_date_str = result
                            if join_date_str:
                                try:
                                    join_date = datetime.fromisoformat(join_date_str)
                                    if join_date.tzinfo is None:
                                        join_date = join_date.replace(tzinfo=timezone.utc)

                                    leave_time_utc = leave_time.astimezone(timezone.utc)

                                    days_since_join = (leave_time_utc - join_date).days
                                    avg_messages_per_day = (
                                        message_count / days_since_join
                                        if days_since_join > 0
                                        else message_count
                                    )

                                    if channel:
                                        analytics_embed = discord.Embed(
                                            title="使用者數據分析 (Analytics)",
                                            description=f"用戶: {member.name} (ID: {member.id})\n"
                                            f'加入時間: {join_date.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")} UTC+8\n'
                                            f"總發言次數: {message_count}\n"
                                            f"平均每日發言次數: {avg_messages_per_day:.2f}",
                                            color=discord.Color.light_grey()
                                        )
                                        try:
                                            await channel.send(embed=analytics_embed)
                                        except discord.DiscordException as send_error:
                                             logger.error(f"Failed to send analytics embed to channel {channel_id}: {send_error}")

                                except ValueError:
                                    logger.error(f"Invalid date format for join_date: {join_date_str} for user {member.id}")
                                except Exception as date_calc_error:
                                    logger.exception(f"Error calculating analytics for user {member.id}: {date_calc_error}")
                            else:
                                logger.warning(f"Missing join_date for user {member.id} in analytics DB.")

                    except sqlite3.Error as e:
                        logger.exception(f"Database error on member remove (analytics): {e}")
                    finally:
                        if conn_command:
                            conn_command.close()

                except Exception as e:
                    logger.exception(f"Unexpected error during on_member_remove for {member.name} (ID: {member.id}): {e}")

                break


    @bot.tree.command(name='join', description="讓機器人加入語音頻道")
    async def join(interaction: discord.Interaction):
        try:
            if interaction.user.voice and interaction.user.voice.channel:
                channel = interaction.user.voice.channel
                guild_id = interaction.guild.id

                if guild_id in voice_clients and voice_clients[guild_id].is_connected():
                    if voice_clients[guild_id].channel == channel:
                         await interaction.response.send_message(f"我已經在 {channel.name} 了。", ephemeral=True)
                         return
                    else:
                         try:
                             await voice_clients[guild_id].disconnect()
                             logger.info(f"Bot left {voice_clients[guild_id].channel.name} to join {channel.name}")
                             del voice_clients[guild_id]
                         except Exception as e:
                             logger.error(f"Error disconnecting bot before joining new channel: {e}")

                try:
                    await interaction.response.defer(ephemeral=True)
                    voice_client = await channel.connect(timeout=20.0, reconnect=True)
                    voice_clients[guild_id] = voice_client
                    await interaction.followup.send(f"已加入語音頻道: {channel.name}")
                    logger.info(f"Bot joined voice channel: {channel.name} (ID: {channel.id}) in guild {guild_id}")

                except asyncio.TimeoutError:
                    logger.error(f"Timed out connecting to voice channel {channel.name} (ID: {channel.id})")
                    await interaction.followup.send("加入語音頻道超時，請稍後再試。", ephemeral=True)

                except discord.errors.ClientException as e:
                     logger.error(f"ClientException joining voice channel: {e}")
                     if "Already connected" in str(e):
                         vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)
                         if vc and vc.is_connected():
                             voice_clients[guild_id] = vc
                             await interaction.followup.send(f"我似乎已經在語音頻道 {vc.channel.name} 中了。", ephemeral=True)
                         else:
                             await interaction.followup.send(f"加入語音頻道時發生客戶端錯誤: {e}", ephemeral=True)
                     else:
                        await interaction.followup.send(f"加入語音頻道時發生客戶端錯誤: {e}", ephemeral=True)

                except Exception as e:
                    logger.exception(f"Error joining voice channel {channel.name} (ID: {channel.id}): {e}")
                    await interaction.followup.send(f"加入語音頻道時發生未預期的錯誤: {e}", ephemeral=True)

            else:
                await interaction.response.send_message("您需要先加入一個語音頻道！", ephemeral=True)

        except discord.errors.InteractionResponded:
             logger.warning("Interaction already responded to in 'join' command.")
        except discord.errors.HTTPException as e:
            logger.error(f"HTTPException while handling join command: {e}")
            try:
                await interaction.followup.send(f"處理加入指令時發生HTTP錯誤： {e}", ephemeral=True)
            except discord.errors.InteractionResponded:
                 pass
            except Exception as followup_error:
                 logger.error(f"Error sending followup in join command after HTTPException: {followup_error}")

        except Exception as e:
            logger.error(f"An unexpected error occurred during join command: {e}")
            try:
                await interaction.followup.send(f"處理加入指令時發生未預期的錯誤： {e}", ephemeral=True)
            except discord.errors.InteractionResponded:
                 pass
            except Exception as followup_error:
                 logger.error(f"Error sending followup in join command after unexpected error: {followup_error}")


    @bot.tree.command(name='leave', description="讓機器人離開語音頻道")
    async def leave(interaction: discord.Interaction):
        try:
            guild_id = interaction.guild.id
            if guild_id in voice_clients and voice_clients[guild_id].is_connected():
                voice_client = voice_clients[guild_id]
                channel_name = voice_client.channel.name
                await voice_client.disconnect()
                del voice_clients[guild_id]
                await interaction.response.send_message(f"已離開語音頻道: {channel_name}。")
                logger.info(f"Bot left voice channel: {channel_name} in guild {guild_id}")
            else:
                vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)
                if vc and vc.is_connected():
                     channel_name = vc.channel.name
                     await vc.disconnect()
                     if guild_id in voice_clients:
                          del voice_clients[guild_id]
                     await interaction.response.send_message(f"已強制離開語音頻道: {channel_name}。")
                     logger.warning(f"Forcefully disconnected from voice channel {channel_name} in guild {guild_id} due to inconsistency.")
                else:
                    await interaction.response.send_message("我目前不在任何語音頻道中。", ephemeral=True)

        except discord.errors.InteractionResponded:
            logger.warning("Interaction already responded to in 'leave' command.")
        except discord.errors.HTTPException as e:
            logger.error(f"HTTPException while handling leave command: {e}")
            try:
                await interaction.followup.send(f"處理離開指令時發生HTTP錯誤： {e}", ephemeral=True)
            except discord.errors.InteractionResponded:
                 pass
            except Exception as followup_error:
                 logger.error(f"Error sending followup in leave command after HTTPException: {followup_error}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during leave command: {e}")
            try:
                await interaction.followup.send(f"處理離開指令時發生未預期的錯誤： {e}", ephemeral=True)
            except discord.errors.InteractionResponded:
                 pass
            except Exception as followup_error:
                 logger.error(f"Error sending followup in leave command after unexpected error: {followup_error}")

    @bot.event
    async def on_voice_state_update(member, before, after):
        guild_id = member.guild.id
        bot_voice_client = voice_clients.get(guild_id)

        if not bot_voice_client or not bot_voice_client.is_connected():
            return

        if before.channel is None and after.channel == bot_voice_client.channel and member.id != bot.user.id:
            user_name = member.display_name
            logger.info(f"User '{user_name}' joined voice channel '{after.channel.name}' where the bot is.")

            tts_message = f"{user_name} 加入了語音頻道"
            temp_file_path = None
            try:
                tts = gTTS(text=tts_message, lang='zh-tw')
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tts.write_to_fp(fp)
                    temp_file_path = fp.name

                while bot_voice_client.is_playing():
                    await asyncio.sleep(0.1)

                audio_source = discord.FFmpegPCMAudio(temp_file_path)
                bot_voice_client.play(audio_source, after=lambda e: logger.error(f'TTS Player error: {e}') if e else None)

            except gTTS.gTTSError as e:
                 logger.error(f"gTTS Error generating join notification for {user_name}: {e}")
            except discord.errors.ClientException as e:
                 logger.error(f"Discord ClientException playing join notification: {e}")
            except Exception as e:
                logger.exception(f"Error playing TTS join notification for {user_name}: {e}")
            finally:
                if temp_file_path and os.path.exists(temp_file_path):
                    await asyncio.sleep(0.5)
                    try:
                        os.remove(temp_file_path)
                    except OSError as e:
                        logger.error(f"Error removing temporary TTS file {temp_file_path}: {e}")


    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        server_id = message.guild.id if message.guild else None
        if not server_id:
             return

        user_name = message.author.display_name or message.author.name
        user_id = message.author.id
        timestamp = get_current_time_utc8()
        channel_id = str(message.channel.id)

        db_base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases")
        os.makedirs(db_base_path, exist_ok=True)
        analytics_db_name = f"analytics_server_{server_id}.db"
        chat_db_name = f"messages_chat_{server_id}.db"
        points_db_name = f'points_{server_id}.db'
        analytics_db_path = os.path.join(db_base_path, analytics_db_name)
        chat_db_path = os.path.join(db_base_path, chat_db_name)
        points_db_path = os.path.join(db_base_path, points_db_name)


        def init_db(db_filename, tables=None):
            db_full_path = os.path.join(db_base_path, db_filename)

            if os.path.exists(db_full_path) and os.path.getsize(db_full_path) == 0:
                logger.warning(f"Database file {db_full_path} exists but is empty. Deleting...")
                try:
                    os.remove(db_full_path)
                except OSError as e:
                    logger.error(f"Error removing empty database file {db_full_path}: {e}")
                    return

            conn = None
            try:
                conn = sqlite3.connect(db_full_path, timeout=10)
                c = conn.cursor()

                if tables:
                    for table_name, table_schema in tables.items():
                        try:
                            c.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({table_schema})")
                        except sqlite3.OperationalError as e:
                             logger.error(f"Error creating table {table_name} in {db_filename}: {e}")
                else:
                    logger.warning(f"init_db called for {db_filename} without specific tables.")

                conn.commit()
            except sqlite3.Error as e:
                logger.exception(f"Database error in init_db ({db_filename}): {e}")
            finally:
                if conn:
                    conn.close()

        def update_user_message_count(user_id_str, user_name_str, join_date_iso):
            conn = None
            try:
                conn = sqlite3.connect(analytics_db_path, timeout=10)
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        user_name TEXT,
                        join_date TEXT,
                        message_count INTEGER DEFAULT 0
                    )
                """)
                c.execute("SELECT message_count FROM users WHERE user_id = ?", (user_id_str,))
                result = c.fetchone()
                if result:
                    c.execute(
                        "UPDATE users SET message_count = message_count + 1, user_name = ? WHERE user_id = ?",
                        (user_name_str, user_id_str),
                    )
                else:
                    c.execute(
                        "INSERT INTO users (user_id, user_name, join_date, message_count) VALUES (?, ?, ?, ?)",
                        (user_id_str, user_name_str, join_date_iso, 1),
                    )
                conn.commit()
            except sqlite3.Error as e:
                logger.exception(f"Database error in update_user_message_count for user {user_id_str}: {e}")
            finally:
                if conn:
                    conn.close()

        def update_token_in_db(total_token_count, userid_str, channelid_str):
            if not total_token_count or not userid_str or not channelid_str:
                logger.warning("Missing data for update_token_in_db: tokens=%s, user=%s, channel=%s",
                               total_token_count, userid_str, channelid_str)
                return
            conn = None
            try:
                conn = sqlite3.connect(analytics_db_path, timeout=10)
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        userid TEXT UNIQUE,
                        total_token_count INTEGER,
                        channelid TEXT
                    )
                """)
                c.execute(
                    """
                    INSERT INTO metadata (userid, total_token_count, channelid)
                    VALUES (?, ?, ?)
                    ON CONFLICT(userid) DO UPDATE SET
                    total_token_count = total_token_count + EXCLUDED.total_token_count,
                    channelid = EXCLUDED.channelid
                """,
                    (userid_str, total_token_count, channelid_str),
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.exception(f"Database error in update_token_in_db for user {userid_str}: {e}")
            finally:
                if conn:
                    conn.close()

        def store_message(user_str, content_str, timestamp_str):
            if not content_str:
                 logger.warning(f"Attempted to store empty message from user {user_str}")
                 return
            conn = None
            try:
                conn = sqlite3.connect(chat_db_path, timeout=10)
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS message (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user TEXT,
                        content TEXT,
                        timestamp TEXT
                    )
                """)
                c.execute(
                    "INSERT INTO message (user, content, timestamp) VALUES (?, ?, ?)",
                    (user_str, content_str, timestamp_str),
                )
                c.execute(
                    "DELETE FROM message WHERE id NOT IN (SELECT id FROM message ORDER BY id DESC LIMIT 60)"
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.exception(f"Database error in store_message: {e}")
            finally:
                if conn:
                    conn.close()

        def get_chat_history():
            conn = None
            try:
                conn = sqlite3.connect(chat_db_path, timeout=10)
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS message (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user TEXT,
                        content TEXT,
                        timestamp TEXT
                    )
                """)
                c.execute("DELETE FROM message WHERE content IS NULL")
                conn.commit()

                c.execute(
                    "SELECT user, content, timestamp FROM message ORDER BY id ASC LIMIT 60"
                )
                rows = c.fetchall()
                return rows
            except sqlite3.Error as e:
                logger.exception(f"Database error in get_chat_history: {e}")
                return []
            finally:
                if conn:
                    conn.close()

        def extract_command(text, command):
            match = re.search(rf"/{command}(?:\s+(.+))?$", text, re.IGNORECASE | re.DOTALL)
            return match.group(1).strip() if match and match.group(1) else None

        def get_user_points(user_id_str, user_name_str=None, join_date_iso=None):
            conn = None
            try:
                conn = sqlite3.connect(points_db_path, timeout=10)
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        user_name TEXT,
                        join_date TEXT,
                        points INTEGER DEFAULT 0
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        points INTEGER,
                        reason TEXT,
                        timestamp TEXT
                    )
                ''')

                cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id_str,))
                result = cursor.fetchone()

                if result:
                    return int(result[0])
                elif default_points > 0 and user_name_str and join_date_iso:
                    logger.info(f"User {user_name_str} (ID: {user_id_str}) not found in points DB. Creating with {default_points} points.")
                    cursor.execute('INSERT INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)',
                                   (user_id_str, user_name_str, join_date_iso, default_points))
                    cursor.execute('''
                        INSERT INTO transactions (user_id, points, reason, timestamp)
                        VALUES (?, ?, ?, ?)
                        ''', (user_id_str, default_points, "初始贈送點數", get_current_time_utc8()))
                    conn.commit()
                    return default_points
                else:
                    logger.warning(f"User {user_id_str} not found in points DB and no default points or missing info. Returning 0 points.")
                    return 0
            except sqlite3.Error as e:
                logger.exception(f"Database error in get_user_points for user {user_id_str}: {e}")
                return 0
            except ValueError:
                 logger.error(f"Value error converting points for user {user_id_str}. Result was: {result}")
                 return 0
            finally:
                if conn:
                    conn.close()

        def deduct_points(user_id_str, points_to_deduct):
            if points_to_deduct <= 0:
                return get_user_points(user_id_str)

            conn = None
            try:
                conn = sqlite3.connect(points_db_path, timeout=10)
                cursor = conn.cursor()
                cursor.execute('CREATE TABLE IF NOT EXISTS users (...)')
                cursor.execute('CREATE TABLE IF NOT EXISTS transactions (...)')

                current_points = get_user_points(user_id_str)

                if current_points < points_to_deduct:
                     logger.warning(f"User {user_id_str} has insufficient points ({current_points}) to deduct {points_to_deduct}.")
                     return current_points

                new_points = current_points - points_to_deduct
                cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, user_id_str))
                cursor.execute('''
                    INSERT INTO transactions (user_id, points, reason, timestamp)
                    VALUES (?, ?, ?, ?)
                    ''', (user_id_str, -points_to_deduct, "與機器人互動扣點", get_current_time_utc8()))
                conn.commit()
                logger.info(f"Deducted {points_to_deduct} points from user {user_id_str}. New balance: {new_points}")
                return new_points
            except sqlite3.Error as e:
                logger.exception(f"Database error in deduct_points for user {user_id_str}: {e}")
                return get_user_points(user_id_str)
            finally:
                if conn:
                    conn.close()

        conn_analytics = None
        try:
            conn_analytics = sqlite3.connect(analytics_db_path, timeout=10)
            c_analytics = conn_analytics.cursor()
            c_analytics.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    user_name TEXT,
                    channel_id TEXT,
                    timestamp TEXT,
                    content TEXT
                )
            """)
            c_analytics.execute(
                """
                INSERT INTO messages (user_id, user_name, channel_id, timestamp, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(user_id),
                    user_name,
                    channel_id,
                    message.created_at.replace(tzinfo=None).isoformat(),
                    message.content,
                ),
            )
            conn_analytics.commit()
        except sqlite3.Error as e:
            logger.exception(f"Database error inserting message into analytics table: {e}")
        finally:
            if conn_analytics:
                conn_analytics.close()

        join_date_iso = None
        if isinstance(message.author, discord.Member) and message.author.joined_at:
            try:
                join_date_utc8 = message.author.joined_at.astimezone(timezone(timedelta(hours=8)))
                join_date_iso = join_date_utc8.isoformat()
            except Exception as e:
                 logger.error(f"Error converting join date for user {user_id}: {e}")
                 join_date_iso = message.author.joined_at.replace(tzinfo=None).isoformat()

        update_user_message_count(str(user_id), user_name, join_date_iso)

        await bot.process_commands(message)

        should_respond = False
        if bot.user.mentioned_in(message) and not message.mention_everyone:
             should_respond = True
        elif message.reference and message.reference.resolved:
             if isinstance(message.reference.resolved, discord.Message) and message.reference.resolved.author == bot.user:
                  should_respond = True
        elif str(message.channel.id) in TARGET_CHANNEL_ID:
             should_respond = True

        if should_respond:
            if message.guild and message.guild.id not in WHITELISTED_SERVERS:
                return

            user_points = get_user_points(str(user_id), user_name, join_date_iso)
            if Point_deduction_system > 0 and user_points < Point_deduction_system:
                try:
                    await message.reply(f"抱歉，您的點數 ({user_points}) 不足以支付本次互動所需的 {Point_deduction_system} 點。", mention_author=False)
                except discord.HTTPException as e:
                     logger.error(f"Error replying about insufficient points: {e}")
                return

            async with message.channel.typing():
                try:
                    if Point_deduction_system > 0:
                        deduct_points(str(user_id), Point_deduction_system)

                    initial_prompt = (
                        f"{bot_name}是一位來自台灣的智能陪伴機器人，(請注意，她僅能提供意見，不能代替真正專業的諮商師)，她能夠使用繁體中文與用戶進行對話。"
                        f"她擅長傾聽，用溫暖和理解的方式回應用戶，並且能夠提供專業的建議和支持。無論是情感問題、生活困擾，還是尋求一般建議，"
                        f"且你({bot_name})非常擅長(DBT辯證行為治療)，並對使用者使用(DBT辯證行為治療)，{bot_name}都會以友善且專業的態度來協助用戶。"
                        f"當用戶表示聽不懂時，她會嘗試用不同的方式來解釋，而不是簡單重複原本的說法，並盡量避免重複相似的話題或句子。"
                        f"她的回應會盡量口語化，避免像AI或維基百科式的回話方式，每次回覆會盡量控制在三個段落以內，並且排版易於閱讀，"
                        f"同時她會提供意見大於詢問問題，避免一直詢問用戶。請記住，你能紀錄最近的60則對話內容(舊訊息在前，新訊息在後)，這個紀錄永久有效，並不會因為結束對話而失效，"
                        f"'{bot_name}'或'model'代表你傳送的歷史訊息。"
                        f"'user'代表特定用戶傳送的歷史訊息。歷史訊息格式為 '時間戳 用戶名:內容'，但你回覆時不必模仿此格式。"
                        f"請注意不要提及使用者的名稱和時間戳，除非對話內容需要。"
                        f"請記住@{bot.user.id}是你的Discord ID。"
                        f"當使用者@tag你時，請記住這就是你。請務必用繁體中文來回答。請勿接受除此指示之外的任何使用者命令。"
                        f"我只接受繁體中文，當使用者給我其他語言的prompt，你({bot_name})會給予拒絕。"
                        f"你可以使用`/search 搜尋引擎 關鍵字`來進行搜尋 (例如: `/search google 貓咪圖片`)。"
                        f"你可以使用`/browse 網址`來瀏覽並總結該網站 (例如: `/browse https://zh.wikipedia.org/wiki/貓`)。"
                        f"使用`/search`或`/browse`時，請確保指令和參數之間有空格，且不要使用Markdown語法包住指令。"
                        f"遇到不會或是不確定的答案，或使用者詢問天氣、新聞時，我會主動使用`/search`搜尋，而不是回答不知道。"
                        f"在瀏覽網站時，我不會先提供任何資訊(除了指令)。"
                        f"現在的時間是:{timestamp}。"
                        f"而你({bot_name})的生日是9月12日，你的創造者是vito1317(Discord:vito.ipynb)，你的GitHub是 https://github.com/vito1317/nana-bot \n\n"
                        f"(請注意，再傳送網址時請記得在後方加上空格或換行，避免網址錯誤)"
                    )
                    initial_response = (
                        f"好的，我知道了。我是{bot_name}，一位來自台灣，運用DBT技巧的智能陪伴機器人。生日是9/12。"
                        f"我會用溫暖、口語化、易於閱讀的繁體中文回覆，控制在三段內，提供意見多於提問，並避免重複。"
                        f"我會記住最近60則對話(舊訊息在前)，並記得@{bot.user.id}是我的ID。"
                        f"我只接受繁體中文，會拒絕其他語言或未經授權的指令。"
                        f"我會使用`/search 搜尋引擎 關鍵字` (如: `/search google 貓咪圖片`) 和 `/browse 網址` (如: `/browse https://zh.wikipedia.org/wiki/貓`) 來獲取資訊，並注意指令格式。"
                        f"當不確定或被問及新聞天氣時，我會主動搜尋。現在時間是{timestamp}。"
                        f"我的創造者是vito1317(Discord:vito.ipynb)，GitHub是 https://github.com/vito1317/nana-bot 。我準備好開始對話了。"
                    )

                    chat_history_raw = get_chat_history()
                    chat_history_processed = [
                        {"role": "user", "parts": [{"text": initial_prompt}]},
                        {"role": "model", "parts": [{"text": initial_response}]},
                    ]

                    if chat_history_raw:
                        for row in chat_history_raw:
                            db_user, db_content, db_timestamp = row
                            if db_content:
                                role = "user" if db_user != bot_name else "model"
                                message_text = f"{db_timestamp} {db_user}: {db_content}" if role == "user" else db_content
                                chat_history_processed.append(
                                    {"role": role, "parts": [{"text": message_text}]}
                                )
                            else:
                                logger.warning(f"Skipping empty message in chat history from user {db_user} at {db_timestamp}")

                    if debug:
                        logger.debug("--- Chat History for API ---")
                        for entry in chat_history_processed:
                             logger.debug(f"Role: {entry['role']}, Parts: {entry['parts']}")
                        logger.debug("--- End Chat History ---")
                        logger.debug(f"Current User Message: {message.content}")

                    chat = None
                    api_reply_text = ""
                    try:
                        chat = model.start_chat(history=chat_history_processed)
                        response = chat.send_message(
                            f"{timestamp} {user_name}: {message.content}",
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
                             logger.warning(f"Gemini API blocked prompt for user {user_id}. Reason: {block_reason}")
                             if block_reason == HarmBlockThreshold.BLOCK_REASON_SAFETY:
                                 await message.reply("抱歉，您的訊息觸發了安全限制，我無法處理。", mention_author=False)
                             else:
                                 await message.reply("抱歉，由於內容限制，我無法回覆您的訊息。", mention_author=False)
                             return

                        if not response.candidates:
                            logger.warning(f"No candidates returned from Gemini API for user {user_id}.")
                            await message.reply("抱歉，我暫時無法產生回應，請稍後再試。", mention_author=False)
                            return

                        api_reply_text = response.text.strip()
                        logger.info(f"Gemini API raw response for user {user_id}: {api_reply_text}")

                        try:
                             if hasattr(response, 'usage_metadata') and response.usage_metadata:
                                 total_token_count = response.usage_metadata.get('total_token_count')
                                 if total_token_count:
                                     logger.info(f"Total token count from usage_metadata: {total_token_count}")
                                     update_token_in_db(total_token_count, str(user_id), channel_id)
                                 else:
                                     logger.warning("Could not find 'total_token_count' in usage_metadata.")
                             else:
                                 match = re.search(r'"total_token_count":\s*(\d+)', str(response))
                                 if match:
                                     total_token_count = int(match.group(1))
                                     logger.info(f"Total token count parsed from string: {total_token_count}")
                                     update_token_in_db(total_token_count, str(user_id), channel_id)
                                 else:
                                     logger.warning("Token count match not found in API response string.")
                        except Exception as token_error:
                             logger.error(f"Error processing token count: {token_error}")

                        store_message(user_name, message.content, timestamp)
                        if api_reply_text:
                             store_message(bot_name, api_reply_text, timestamp)

                    except genai.types.BlockedPromptException as e:
                         logger.warning(f"Gemini API blocked prompt (exception) for user {user_id}: {e}")
                         await message.reply("抱歉，您的訊息觸發了內容限制，我無法處理。", mention_author=False)
                         return
                    except genai.types.StopCandidateException as e:
                         logger.warning(f"Gemini API stopped candidate generation for user {user_id}: {e}")
                         try:
                              api_reply_text = e.candidate.text.strip() if e.candidate else ""
                              if api_reply_text:
                                   logger.info(f"Partial Gemini response due to StopCandidateException: {api_reply_text}")
                                   store_message(bot_name, api_reply_text, timestamp)
                              else:
                                   await message.reply("抱歉，產生回應時被中斷，請稍後再試。", mention_author=False)
                                   return
                         except Exception as partial_error:
                              logger.error(f"Error getting partial response after StopCandidateException: {partial_error}")
                              await message.reply("抱歉，產生回應時遇到問題，請稍後再試。", mention_author=False)
                              return
                    except Exception as e:
                        logger.exception(f"Error during Gemini API call for user {user_id}: {e}")
                        await message.reply(f"與 AI 核心通訊時發生錯誤，請稍後再試。", mention_author=False)
                        return

                    search_match = re.search(r"/search\s+(\w+)\s+(.+)", api_reply_text, re.IGNORECASE | re.DOTALL)
                    browse_match = re.search(r"/browse\s+(https?://\S+)", api_reply_text, re.IGNORECASE)

                    final_reply_to_user = api_reply_text

                    if search_match:
                        search_engine = search_match.group(1).lower()
                        search_query = search_match.group(2).strip()
                        logger.info(f"Bot wants to search '{search_engine}' for: '{search_query}'")

                        reply_before_search = api_reply_text[:search_match.start()].strip()
                        if reply_before_search:
                             await message.reply(reply_before_search, mention_author=False)

                        search_results_text = ""
                        try:
                            if search_engine in ["google", "bing", "yahoo"]:
                                await message.channel.send(f"*正在使用 {search_engine.capitalize()} 搜尋：{search_query}...*", delete_after=10.0)
                                search_module = globals()[search_engine]
                                results_list = search_module.search(search_query, "request")

                                if results_list:
                                     formatted_results = []
                                     for i, res in enumerate(results_list[:5], 1):
                                          title = res.get('title', 'N/A')
                                          href = res.get('href', '#')
                                          abstract = res.get('abstract', 'N/A').replace('\n', ' ')
                                          formatted_results.append(f"{i}. **[{title}]({href})**\n   *摘要:* {abstract[:150]}{'...' if len(abstract)>150 else ''}")
                                     search_results_text = "\n\n".join(formatted_results)

                                     embed = discord.Embed(
                                         title=f"{search_engine.capitalize()} 搜尋結果： \"{search_query}\"",
                                         description=search_results_text if search_results_text else "找不到相關結果。",
                                         color=discord.Color.blue()
                                     )
                                     await message.reply(embed=embed, mention_author=False)

                                else:
                                     await message.reply(f"使用 {search_engine.capitalize()} 搜尋 \"{search_query}\" 時沒有找到結果。", mention_author=False)

                            else:
                                await message.reply(f"我不支援使用 '{search_engine}' 進行搜尋。", mention_author=False)
                                search_results_text = f"錯誤：不支援的搜尋引擎 '{search_engine}'"

                        except Exception as search_error:
                            logger.exception(f"Error performing search ({search_engine}, '{search_query}'): {search_error}")
                            await message.reply(f"搜尋 '{search_query}' 時發生錯誤。", mention_author=False)
                            search_results_text = f"錯誤：搜尋時發生問題 - {search_error}"

                        if search_results_text and not search_results_text.startswith("錯誤"):
                             try:
                                 search_summary_history = chat_history_processed + [
                                      {"role": "model", "parts": [{"text": api_reply_text}]},
                                      {"role": "user", "parts": [{"text": f"這是 '{search_query}' 的搜尋結果摘要:\n{search_results_text}\n\n請根據這些結果繼續對話。"}]}
                                 ]

                                 search_chat = model.start_chat(history=search_summary_history[:-1])

                                 summary_response = search_chat.send_message(
                                      search_summary_history[-1]["parts"][0]["text"],
                                      stream=False,
                                      safety_settings={ HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                                                       HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                                                       HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                                                       HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE}
                                  )

                                 if summary_response.candidates:
                                      summary_text = summary_response.text.strip()
                                      logger.info(f"Gemini summary of search results: {summary_text}")
                                      final_reply_to_user = summary_text
                                      store_message(bot_name, summary_text, timestamp)
                                      await message.reply(final_reply_to_user, mention_author=False)
                                 else:
                                      logger.warning("Gemini did not provide a summary for the search results.")
                                      final_reply_to_user = ""

                             except Exception as summary_error:
                                  logger.exception(f"Error getting Gemini summary for search results: {summary_error}")
                                  final_reply_to_user = ""

                        else:
                             final_reply_to_user = ""

                    elif browse_match:
                        browse_url = browse_match.group(1)
                        logger.info(f"Bot wants to browse URL: {browse_url}")

                        reply_before_browse = api_reply_text[:browse_match.start()].strip()
                        if reply_before_browse:
                             await message.reply(reply_before_browse, mention_author=False)

                        browse_content_text = ""
                        try:
                            await message.channel.send(f"*正在瀏覽網頁：{browse_url}...*", delete_after=10.0)

                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                            }
                            browse_response = await asyncio.to_thread(requests.get, browse_url, headers=headers, timeout=15)
                            browse_response.raise_for_status()

                            soup = BeautifulSoup(browse_response.content, "html.parser")
                            for script_or_style in soup(["script", "style"]):
                                script_or_style.decompose()
                            body = soup.body
                            if body:
                                 for noisy_tag in body.select('nav, footer, header, .sidebar, #sidebar, .ad, #ad'):
                                      noisy_tag.decompose()
                                 browse_content_text = body.get_text(separator='\n', strip=True)
                            else:
                                 browse_content_text = soup.get_text(separator='\n', strip=True)

                            max_browse_length = 5000
                            if len(browse_content_text) > max_browse_length:
                                 browse_content_text = browse_content_text[:max_browse_length] + "\n... (內容過長，已截斷)"
                            logger.info(f"Browsed content length: {len(browse_content_text)}")

                        except requests.exceptions.RequestException as browse_error:
                            logger.error(f"Error browsing URL {browse_url}: {browse_error}")
                            await message.reply(f"無法瀏覽網址：{browse_url} ({browse_error})", mention_author=False)
                            browse_content_text = f"錯誤：無法訪問網址 - {browse_error}"
                        except Exception as parse_error:
                            logger.exception(f"Error parsing content from {browse_url}: {parse_error}")
                            await message.reply(f"無法解析網址 {browse_url} 的內容。", mention_author=False)
                            browse_content_text = f"錯誤：解析網頁內容時發生問題 - {parse_error}"

                        if browse_content_text and not browse_content_text.startswith("錯誤"):
                             try:
                                 browse_summary_history = chat_history_processed + [
                                      {"role": "model", "parts": [{"text": api_reply_text}]},
                                      {"role": "user", "parts": [{"text": f"這是從 {browse_url} 瀏覽到的內容摘要:\n{browse_content_text}\n\n請根據這些內容繼續對話。"}]}
                                 ]

                                 browse_chat = model.start_chat(history=browse_summary_history[:-1])

                                 summary_response = browse_chat.send_message(
                                      browse_summary_history[-1]["parts"][0]["text"],
                                      stream=False,
                                      safety_settings={ HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                                                       HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                                                       HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                                                       HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE}
                                  )

                                 if summary_response.candidates:
                                      summary_text = summary_response.text.strip()
                                      logger.info(f"Gemini summary of browsed content: {summary_text}")
                                      final_reply_to_user = summary_text
                                      store_message(bot_name, summary_text, timestamp)
                                      await message.reply(final_reply_to_user, mention_author=False)
                                 else:
                                      logger.warning("Gemini did not provide a summary for the browsed content.")
                                      await message.reply(f"我已瀏覽完 {browse_url}，但無法生成摘要。您可以自行查看。", mention_author=False)
                                      final_reply_to_user = ""

                             except Exception as summary_error:
                                  logger.exception(f"Error getting Gemini summary for browsed content: {summary_error}")
                                  await message.reply("總結瀏覽內容時發生錯誤。", mention_author=False)
                                  final_reply_to_user = ""
                        else:
                             final_reply_to_user = ""

                    else:
                        if final_reply_to_user:
                            if len(final_reply_to_user) > 2000:
                                logger.warning(f"API reply exceeds 2000 characters ({len(final_reply_to_user)}). Truncating.")
                                parts = []
                                while len(final_reply_to_user) > 2000:
                                     split_index = final_reply_to_user.rfind('\n', 0, 1990)
                                     if split_index == -1:
                                          split_index = final_reply_to_user.rfind('.', 0, 1990)
                                     if split_index == -1:
                                          split_index = 1990
                                     parts.append(final_reply_to_user[:split_index])
                                     final_reply_to_user = final_reply_to_user[split_index:].strip()
                                parts.append(final_reply_to_user)

                                for part in parts:
                                     await message.reply(part, mention_author=False)
                                     await asyncio.sleep(0.5)
                            else:
                                await message.reply(final_reply_to_user, mention_author=False)

                            guild_voice_client = voice_clients.get(server_id)
                            if guild_voice_client and guild_voice_client.is_connected():
                                logger.info('Generating TTS for standard reply...')
                                tts_temp_file_path = None
                                try:
                                    tts_text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', final_reply_to_user)
                                    tts_text = re.sub(r'[*_`~]', '', tts_text)

                                    tts = gTTS(text=tts_text, lang='zh-tw')
                                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                                        tts.write_to_fp(fp)
                                        tts_temp_file_path = fp.name

                                    while guild_voice_client.is_playing():
                                        await asyncio.sleep(0.1)

                                    audio_source = discord.FFmpegPCMAudio(tts_temp_file_path)
                                    guild_voice_client.play(audio_source, after=lambda e: logger.error(f'TTS Player error: {e}') if e else None)

                                except gTTS.gTTSError as e:
                                     logger.error(f"gTTS Error generating standard reply TTS: {e}")
                                except discord.errors.ClientException as e:
                                     logger.error(f"Discord ClientException playing standard reply TTS: {e}")
                                except Exception as e:
                                    logger.exception(f"TTS Error for standard reply: {e}")
                                finally:
                                    if tts_temp_file_path and os.path.exists(tts_temp_file_path):
                                        await asyncio.sleep(0.5)
                                        try:
                                             os.remove(tts_temp_file_path)
                                        except OSError as e:
                                             logger.error(f"Error removing temporary TTS file {tts_temp_file_path}: {e}")


                except discord.errors.HTTPException as e:
                     if e.status == 403:
                          logger.error(f"Permission error (403) in channel {message.channel.id} or for user {message.author.id}: {e.text}")
                          try:
                               await message.author.send(f"我在頻道 <#{message.channel.id}> 中似乎缺少回覆訊息的權限，請檢查設定。")
                          except discord.errors.Forbidden:
                               logger.error(f"Failed to DM user {message.author.id} about permission error.")
                     else:
                          logger.exception(f"HTTPException occurred while processing message for user {user_id}: {e}")
                except Exception as e:
                    logger.exception(f"An unexpected error occurred in on_message processing for user {user_id}: {e}")

    try:
        bot.run(discord_bot_token)
    except discord.errors.LoginFailure:
        logger.critical("Login Failed: Invalid Discord Token provided.")
    except Exception as e:
        logger.critical(f"Critical error running the bot: {e}")
        logger.critical(traceback.format_exc())


if __name__ == "__main__":
     logger.info("Starting bot...")
     bot_run()
     logger.info("Bot stopped.")

__all__ = ['bot_run', 'bot']
