import asyncio
import traceback
from discord.ext.voice_recv import BasicSink
import discord.ext.voice_recv
import discord
from discord import app_commands, FFmpegPCMAudio, AudioSource, opus
from discord.ext.voice_recv.sinks import AudioSink
from discord.ext import commands, tasks, voice_recv
from typing import Optional, Dict, Set, Any
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
import json
import google.generativeai as genai
from google.generativeai import types as genai_types
from google import genai as google_genai_module
from google.genai import types as genai_types
import requests
from bs4 import BeautifulSoup
import time
import re
import pytz
from collections import defaultdict, deque
from typing import Optional, Dict, Set, Any, List, Tuple, Union

import queue
import threading
from nana_bot import (
    bot,
    bot_name,
    WHITELISTED_SERVERS,
    TARGET_CHANNEL_ID,
    API_KEY,
    init_db, 
    gemini_model as gemini_model_name, 
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
import numpy as np
import torch
import torchaudio

import tempfile
import edge_tts
import functools
import wave
import uuid
import io

gemini_live_client: Optional[Any] = None
live_sessions: Dict[int, Dict[str, Any]] = {}


GEMINI_LIVE_MODEL_NAME = "models/gemini-2.5-flash-preview-native-audio-dialog" 


GEMINI_LIVE_CONFIG = genai_types.GenerationConfig(
)


GEMINI_LIVE_CONNECT_CONFIG = genai_types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    media_resolution="MEDIA_RESOLUTION_MEDIUM",
    speech_config=genai_types.SpeechConfig(
        voice_config=genai_types.VoiceConfig(
            prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    ),
)
GEMINI_AUDIO_INPUT_SAMPLING_RATE = 16000
GEMINI_AUDIO_INPUT_CHANNELS = 1
GEMINI_AUDIO_OUTPUT_SAMPLING_RATE = 24000
GEMINI_AUDIO_OUTPUT_CHANNELS = 1
GEMINI_AUDIO_OUTPUT_SAMPLE_WIDTH = 2


listening_guilds: Dict[int, discord.VoiceClient] = {}
voice_clients: Dict[int, discord.VoiceClient] = {}


safety_settings = {
    genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai_types.HarmBlockThreshold.BLOCK_NONE,
    genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai_types.HarmBlockThreshold.BLOCK_NONE,
    genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai_types.HarmBlockThreshold.BLOCK_NONE,
    genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai_types.HarmBlockThreshold.BLOCK_NONE,
}

DEFAULT_VOICE = "zh-TW-HsiaoYuNeural"
STT_LANGUAGE = "zh"

logging.basicConfig(level=logging.INFO if not debug else logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("bot.log", encoding='utf-8'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)


async def play_tts(voice_client: discord.VoiceClient, text: str, context: str = "TTS"):
    total_start = time.time()
    if not voice_client or not voice_client.is_connected():
        logger.warning(f"[{context}] 無效或未連接的 voice_client，無法播放 TTS: '{text}'")
        return

    logger.info(f"[{context}] 開始為文字生成 TTS: '{text[:50]}...' (Guild: {voice_client.guild.id})")
    loop = asyncio.get_running_loop()
    tmp_path = None
    source = None
    playback_started = False

    try:
        step1 = time.time()
        communicate = edge_tts.Communicate(text, DEFAULT_VOICE)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        logger.debug(f"[{context}] 暫存檔案路徑: {tmp_path}")

        await loop.run_in_executor(None, functools.partial(communicate.save_sync, tmp_path))
        logger.info(f"[{context}] 步驟 1 (生成音檔) 耗時 {time.time()-step1:.4f}s -> {tmp_path}")

        step2 = time.time()
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        if not os.path.exists(tmp_path):
             logger.error(f"[{context}] 暫存檔案 {tmp_path} 在創建音源前消失了！")
             return

        source = FFmpegPCMAudio(tmp_path, **ffmpeg_options)
        logger.info(f"[{context}] 步驟 2 (創建音源) 耗時 {time.time()-step2:.4f}s")

        if not voice_client.is_connected():
             logger.warning(f"[{context}] 創建音源後，語音客戶端已斷開連接。")
             if tmp_path and os.path.exists(tmp_path):
                 try: os.remove(tmp_path)
                 except OSError as e: logger.warning(f"Error cleaning up {tmp_path}: {e}")
             return

        if voice_client.is_playing():
            logger.info(f"[{context}] 停止當前播放以播放新的 TTS。")
            voice_client.stop()
            await asyncio.sleep(0.2)

        step3 = time.time()
        def _cleanup_tts(error, path_to_clean, guild_id_ctx):
            log_prefix = f"[{context}][Cleanup][Guild:{guild_id_ctx}]"
            if error: logger.error(f"{log_prefix} 播放器錯誤: {error}")
            else: logger.info(f"{log_prefix} TTS 播放完成。")

            if guild_id_ctx in live_sessions and live_sessions[guild_id_ctx].get("is_bot_speaking_tts"):
                logger.info(f"{log_prefix} TTS for bot turn finished. Signaling end_of_turn for Live API.")
                live_sessions[guild_id_ctx]["is_bot_speaking_tts"] = False
                gemini_session = live_sessions[guild_id_ctx].get("session")
                if gemini_session:
                    coro = gemini_session.send(input=".", end_of_turn=True)
                    asyncio.run_coroutine_threadsafe(coro, bot.loop)


            try:
                if path_to_clean and os.path.exists(path_to_clean):
                    os.remove(path_to_clean)
                    logger.info(f"{log_prefix} 已清理暫存檔案: {path_to_clean}")
            except OSError as e: logger.warning(f"{log_prefix} 清理暫存檔案 {path_to_clean} 失敗: {e}")
            except Exception as cleanup_err: logger.error(f"{log_prefix} 清理檔案時發生錯誤: {cleanup_err}")

        if voice_client.guild.id in live_sessions:
            live_sessions[voice_client.guild.id]["is_bot_speaking_tts"] = True


        voice_client.play(source, after=lambda e, p=tmp_path, gid=voice_client.guild.id: _cleanup_tts(e, p, gid))
        playback_started = True
        logger.info(f"[{context}] 步驟 3 (開始播放) 耗時 {time.time()-step3:.4f}s (背景執行)")
        logger.info(f"[{context}] 從請求到開始播放總耗時: {time.time()-total_start:.4f}s")

    except edge_tts.NoAudioReceived: logger.error(f"[{context}] Edge TTS 失敗: 未收到音檔。 文字: '{text[:50]}...'")
    except edge_tts.exceptions.UnexpectedStatusCode as e: logger.error(f"[{context}] Edge TTS 失敗: 非預期狀態碼 {e.status_code}。 文字: '{text[:50]}...'")
    except FileNotFoundError: logger.error(f"[{context}] FFmpeg 錯誤: 找不到 FFmpeg 執行檔。請確保 FFmpeg 已安裝並在系統 PATH 中。")
    except discord.errors.ClientException as e: logger.error(f"[{context}] Discord 客戶端錯誤 (播放時): {e}")
    except Exception as e: logger.exception(f"[{context}] play_tts 中發生非預期錯誤。 文字: '{text[:50]}...'")
    finally:
        if not playback_started:
            if voice_client.guild.id in live_sessions:
                live_sessions[voice_client.guild.id]["is_bot_speaking_tts"] = False
            if tmp_path and os.path.exists(tmp_path):
                logger.warning(f"[{context}][Finally] 播放未成功開始，清理暫存檔案: {tmp_path}")
                try: os.remove(tmp_path)
                except OSError as e: logger.warning(f"[{context}][Finally] 清理未播放的暫存檔案 {tmp_path} 失敗: {e}")
                except Exception as final_e: logger.error(f"[{context}][Finally] 清理未播放檔案時發生錯誤: {final_e}")


def get_current_time_utc8():
    utc8 = timezone(timedelta(hours=8))
    current_time = datetime.now(utc8)
    return current_time.strftime("%Y-%m-%d %H:%M:%S")

google_genai_module.Client(api_key=API_KEY)
text_model = None
try:
    if not API_KEY:
        raise ValueError("Gemini API key is not set for text model.")
    text_model = google_genai_module.GenerativeModel(gemini_model_name)
    logger.info(f"成功初始化 GenerativeModel (Text): {gemini_model_name}")
except Exception as e:
    logger.critical(f"初始化 GenerativeModel (Text) 失敗: {e}")

gemini_live_client_instance = None
try:
    if not API_KEY:
        raise ValueError("Gemini API key is not set for Live client.")
    gemini_live_client_instance = google_genai_module.Client(api_key=API_KEY, http_options={"api_version": "v1beta"})
    logger.info(f"Gemini Live Client initialized for use with `client.aio.live.connect`.")
except Exception as e:
    logger.critical(f"初始化 Gemini Live Client 失敗: {e}. Live chat functionality will be disabled.")
    gemini_live_client_instance = None


db_base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases")
os.makedirs(db_base_path, exist_ok=True)

def get_db_path(guild_id, db_type):
    if db_type == 'analytics': return os.path.join(db_base_path, f"analytics_server_{guild_id}.db")
    elif db_type == 'chat': return os.path.join(db_base_path, f"messages_chat_{guild_id}.db")
    elif db_type == 'points': return os.path.join(db_base_path, f"points_{guild_id}.db")
    else: raise ValueError(f"Unknown database type: {db_type}")

def init_db_for_guild(guild_id):
    logger.info(f"正在為伺服器 {guild_id} 初始化資料庫...")
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
            logger.debug(f"資料庫已初始化/檢查: {db_path}")
        except sqlite3.OperationalError as e: logger.error(f"初始化資料庫 {db_path} 時發生 OperationalError: {e}")
        except sqlite3.Error as e: logger.exception(f"初始化資料庫 {db_path} 時發生錯誤: {e}")
        finally:
            if conn: conn.close()

    _init_single_db(get_db_path(guild_id, 'analytics'), db_tables)
    _init_single_db(get_db_path(guild_id, 'points'), points_tables)
    _init_single_db(get_db_path(guild_id, 'chat'), chat_tables)
    logger.info(f"伺服器 {guild_id} 的資料庫初始化完成。")


@tasks.loop(hours=24)
async def send_daily_message():
    logger.info("開始執行每日訊息任務...")
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
                            await channel.send(f"{role.mention} 各位未審核的人，快來這邊審核喔")
                            logger.info(f"Sent daily message to channel {target_channel_id} in guild {server_id}")
                        except discord.Forbidden: logger.error(f"Permission error sending daily message to channel {target_channel_id} in guild {server_id}.")
                        except discord.HTTPException as e: logger.error(f"HTTP error sending daily message to channel {target_channel_id} in guild {server_id}: {e}")
                    else: logger.warning(f"Role {role_to_mention_id} not found in guild {server_id} for daily message.")
                else:
                    if not channel: logger.warning(f"Daily message channel {target_channel_id} not found for server index {idx} (Guild ID: {server_id}).")
                    if not guild: logger.warning(f"Guild {server_id} not found for daily message.")
            else: logger.error(f"Configuration index {idx} out of range for daily message (Guild ID: {server_id}). Lists length: send_daily={len(send_daily_channel_id_list)}, not_reviewed={len(not_reviewed_id)}")
        except Exception as e: logger.exception(f"Unexpected error in send_daily_message loop for server index {idx} (Guild ID: {server_id}): {e}")
    logger.info("每日訊息任務執行完畢。")


@send_daily_message.before_loop
async def before_send_daily_message():
    await bot.wait_until_ready()
    now = datetime.now(pytz.timezone('Asia/Taipei'))
    next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if next_run < now: next_run += timedelta(days=1)
    wait_seconds = (next_run - now).total_seconds()
    logger.info(f"每日訊息任務將在 {wait_seconds:.0f} 秒後首次執行 (於 {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')})")
    await asyncio.sleep(wait_seconds)

@bot.event
async def on_ready():
    logger.info(f"以 {bot.user.name} (ID: {bot.user.id}) 登入")
    logger.info(f"Discord.py 版本: {discord.__version__}")
    logger.info("機器人已準備就緒並連接到 Discord。")

    if text_model is None: logger.error("AI Text模型初始化失敗。文字AI 回覆功能將被禁用。")
    if gemini_live_client_instance is None: logger.error("Gemini Live Client 初始化失敗。語音AI對話功能將被禁用。")


    guild_count = 0
    for guild in bot.guilds:
        guild_count += 1
        logger.info(f"機器人所在伺服器: {guild.name} (ID: {guild.id})")
        init_db_for_guild(guild.id)

    logger.info("正在同步應用程式命令...")
    try:
        for guild in bot.guilds:
            try:
                synced_guild = await bot.tree.sync()
                logger.debug(f"已為伺服器 {guild.id} ({guild.name}) 同步 {len(synced_guild)} 個命令。")
            except discord.errors.Forbidden: logger.warning(f"無法為伺服器 {guild.id} ({guild.name}) 同步命令 (權限不足)。")
            except discord.HTTPException as e: logger.error(f"為伺服器 {guild.id} ({guild.name}) 同步命令時發生 HTTP 錯誤: {e}")
        logger.info(f"應用程式命令同步完成。")
    except Exception as e:
        logger.exception(f"同步命令時發生非預期錯誤: {e}")

    if not send_daily_message.is_running():
        send_daily_message.start()
        logger.info("已啟動每日訊息任務。")

    activity = discord.Game(name=f"在 {guild_count} 個伺服器上運作 | /help")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    logger.info(f"機器人狀態已設定。正在監看 {guild_count} 個伺服器。")


@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"機器人加入新伺服器: {guild.name} (ID: {guild.id})")
    init_db_for_guild(guild.id)
    if guild.id not in servers: logger.warning(f"伺服器 {guild.id} ({guild.name}) 不在設定檔 'servers' 列表中。")

    logger.info(f"正在為新伺服器 {guild.id} 同步命令...")
    try:
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"已為新伺服器 {guild.id} ({guild.name}) 同步 {len(synced)} 個命令。")
    except discord.errors.Forbidden: logger.error(f"為新伺服器 {guild.id} ({guild.name}) 同步命令時權限不足。")
    except Exception as e: logger.exception(f"為新伺服器 {guild.id} ({guild.name}) 同步命令時出錯: {e}")

    channel_to_send = guild.system_channel or next((tc for tc in guild.text_channels if tc.permissions_for(guild.me).send_messages), None)
    if channel_to_send:
        try:
            await channel_to_send.send(f"大家好！我是 {bot_name}。很高興加入 **{guild.name}**！\n"
                                       f"您可以使用 `/help` 來查看我的指令。\n"
                                       f"如果想與我進行即時語音對話，請先使用 `/join` 加入您的語音頻道，然後使用 `/live_chat` 開始。\n"
                                       f"請確保已根據需求設定相關頻道 ID 和權限。\n"
                                       f"我的設定檔可能需要手動更新以包含此伺服器 ID ({guild.id}) 的相關設定。")
            logger.info(f"已在伺服器 {guild.id} 的頻道 {channel_to_send.name} 發送歡迎訊息。")
        except discord.Forbidden: logger.warning(f"無法在伺服器 {guild.id} 的頻道 {channel_to_send.name} 發送歡迎訊息 (權限不足)。")
        except discord.HTTPException as e: logger.error(f"在伺服器 {guild.id} 的頻道 {channel_to_send.name} 發送歡迎訊息時發生 HTTP 錯誤: {e}")
    else: logger.warning(f"在伺服器 {guild.id} ({guild.name}) 中找不到適合發送歡迎訊息的頻道或缺少發送權限。")


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    logger.info(f"新成員加入: {member} (ID: {member.id}) 於伺服器 {guild.name} (ID: {guild.id})")

    server_index = -1
    try: server_index = servers.index(guild.id)
    except ValueError:
        logger.warning(f"No configuration found for server ID {guild.id} in on_member_join. ANALYTICS ONLY.")

        db_path_analytics = get_db_path(guild.id, 'analytics')
        conn_analytics = sqlite3.connect(db_path_analytics)
        cursor_analytics = conn_analytics.cursor()
        cursor_analytics.execute("INSERT OR IGNORE INTO users (user_id, user_name, join_date, message_count) VALUES (?, ?, ?, 0)",
                                 (str(member.id), member.name, get_current_time_utc8()))
        conn_analytics.commit()
        conn_analytics.close()
        return

    if server_index == -1:
        logger.error(f"Server index not found for guild {guild.id} in on_member_join despite being in 'servers' list. This should not happen.")
        return

    try:
        newcomer_role_id = newcomer_channel_id[server_index]
        newcomer_role = guild.get_role(newcomer_role_id)
        if newcomer_role:
            await member.add_roles(newcomer_role)
            logger.info(f"已將身分組 '{newcomer_role.name}' 指派給新成員 {member.name} ({member.id})。")
        else:
            logger.warning(f"找不到身分組 ID {newcomer_role_id}，無法指派給新成員。")
    except IndexError:
        logger.error(f"newcomer_channel_id 設定錯誤，索引 {server_index} 超出範圍。")
    except discord.Forbidden:
        logger.error(f"沒有權限指派身分組給 {member.name} ({member.id})。")
    except Exception as e:
        logger.exception(f"指派身分組給新成員時發生錯誤: {e}")

    welcome_channel_id_val = welcome_channel_id[server_index]
    welcome_channel = guild.get_channel(welcome_channel_id_val)

    db_path_analytics = get_db_path(guild.id, 'analytics')
    conn_analytics = sqlite3.connect(db_path_analytics)
    cursor_analytics = conn_analytics.cursor()
    cursor_analytics.execute("INSERT OR IGNORE INTO users (user_id, user_name, join_date, message_count) VALUES (?, ?, ?, 0)",
                             (str(member.id), member.name, get_current_time_utc8()))
    conn_analytics.commit()
    conn_analytics.close()

    if Point_deduction_system[server_index]:
        db_path_points = get_db_path(guild.id, 'points')
        conn_points = sqlite3.connect(db_path_points)
        cursor_points = conn_points.cursor()
        cursor_points.execute("INSERT OR IGNORE INTO users (user_id, user_name, join_date, points) VALUES (?, ?, ?, ?)",
                              (str(member.id), member.name, get_current_time_utc8(), default_points))
        conn_points.commit()
        conn_points.close()
        logger.info(f"已為新成員 {member.name} ({member.id}) 在點數系統中創建記錄，預設點數 {default_points}。")

    if welcome_channel:
        logger.info(f"正在為新成員 {member.name} 準備歡迎訊息...")
        welcome_prompt = f"""你是 {guild.name} 的 AI 助理 {bot_name}。
一位新成員剛剛加入了伺服器：
- 名字: {member.name}
- ID: {member.id}
- 加入時間: {get_current_time_utc8()}

你的任務是生成一段友善且吸引人的歡迎訊息。訊息內容應包括：
1. 對新成員的熱烈歡迎。
2. 簡要介紹伺服器的主要主題或特色 (例如：這是一個關於遊戲、學習、技術交流等的社群)。
3. 提及一些重要的頻道，例如規則頻道、公告頻道或新手教學頻道 (如果有的話，頻道 ID 僅供參考，請勿直接輸出 ID)。
4. 鼓勵新成員自我介紹或參與討論。
5. (可選) 加入一個與伺服器主題相關的有趣問題或小提示。

請注意：
- 語氣要親切、活潑。
- 訊息不宜過長，保持簡潔。
- 使用 Markdown 格式讓訊息更易讀 (例如粗體、斜體)。
- **不要提及你是 AI 或語言模型。**
- **直接輸出歡迎訊息內容，不要包含任何前言或註解。**

伺服器資訊 (僅供你參考，選擇性使用):
- 伺服器名稱: {guild.name}
- 伺服器 ID: {guild.id}
- (可假設一些常見的頻道名稱，如 #rules, #announcements, #general-chat, #introductions)

範例 (請根據實際情況調整):
"哈囉 @{member.name}！🎉 熱烈歡迎你加入 **{guild.name}**！我們是一個熱愛 [伺服器主題] 的大家庭。記得先看看 #rules 頻道，然後來 #introductions 跟我們打個招呼吧！期待你的加入！ 😊"
請生成適合的歡迎訊息：
"""
        if text_model:
            try:
                logger.debug(f"向 Gemini API 發送歡迎訊息生成請求。Prompt:\n{welcome_prompt[:300]}...")
                async with welcome_channel.typing():
                    responses = await text_model.generate_content_async(
                        welcome_prompt,
                        safety_settings=safety_settings,
                        generation_config=genai_types.GenerationConfig(temperature=0.7, top_p=0.9, top_k=40)
                    )
                generated_text = responses.text
                logger.info(f"從 Gemini API 收到歡迎訊息: {generated_text[:100]}...")

                final_message = f"{member.mention}\n{generated_text}"
                await welcome_channel.send(final_message)
                logger.info(f"已在頻道 #{welcome_channel.name} 發送AI生成的歡迎訊息給 {member.name}。")

            except Exception as e:
                logger.error(f"使用 Gemini API 生成歡迎訊息失敗: {e}", exc_info=debug)
                await welcome_channel.send(f"歡迎 {member.mention} 加入 **{guild.name}**！🎉 希望你在這裡玩得開心！記得查看伺服器規則並向大家問好喔！")
                logger.info(f"已在頻道 #{welcome_channel.name} 發送預設的歡迎訊息給 {member.name} (API 失敗)。")
        else:
            logger.warning("Gemini text_model 未初始化，無法生成 AI 歡迎訊息。")
            await welcome_channel.send(f"歡迎 {member.mention} 加入 **{guild.name}**！🎉 希望你在這裡玩得開心！記得查看伺服器規則並向大家問好喔！")
            logger.info(f"已在頻道 #{welcome_channel.name} 發送預設的歡迎訊息給 {member.name} (模型未加載)。")
    else:
        logger.warning(f"找不到歡迎頻道 ID {welcome_channel_id_val}，無法發送歡迎訊息。")


@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    guild_id = member.guild.id
    logger.info(f"成員離開: {member} ({member.id}) 從伺服器 {guild.name} ({guild.id})")

    if guild_id in live_sessions and live_sessions[guild_id].get("user_id") == member.id:
        logger.info(f"User {member.id} who was in a live session left guild {guild_id}. Cleaning up live session.")
        await _cleanup_live_session(guild_id, "User left server during session.")

    try:
        server_index = servers.index(guild_id)
    except ValueError:
        logger.warning(f"Guild ID {guild_id} not found in 'servers' list for on_member_remove. Skipping specific channel message.")
        return

    if server_index < 0 or server_index >= len(member_remove_channel_id):
        logger.warning(f"member_remove_channel_id configuration error for server index {server_index} (Guild ID: {guild_id}).")
        return

    target_channel_id_val = member_remove_channel_id[server_index]
    if target_channel_id_val:
        channel = guild.get_channel(target_channel_id_val)
        if channel:
            try:
                await channel.send(f"成員 **{member.name}** ({member.id}) 已經離開了伺服器。一路順風！")
                logger.info(f"Sent member leave message for {member.name} to channel {channel.id} in guild {guild.id}.")
            except discord.Forbidden:
                logger.error(f"Permission error sending member leave message to channel {channel.id} in guild {guild.id}.")
            except discord.HTTPException as e:
                logger.error(f"HTTP error sending member leave message to channel {channel.id} in guild {guild.id}: {e}")
        else:
            logger.warning(f"Member remove channel {target_channel_id_val} not found for guild {guild_id}.")
    else:
        logger.info(f"No member remove channel configured for guild {guild_id} (server index {server_index}).")

def resample_audio(pcm_data: bytes, original_sr: int, target_sr: int, num_channels: int = 2) -> bytes:
    if not pcm_data:
        return b''
    if original_sr == target_sr and num_channels == 1:
        return pcm_data

    try:
        audio_int16 = np.frombuffer(pcm_data, dtype=np.int16)

        if audio_int16.size == 0: return b''

        if num_channels == 2:
            if audio_int16.size % 2 == 0:
                try:
                    stereo_audio = audio_int16.reshape(-1, 2)
                    mono_audio = stereo_audio.mean(axis=1).astype(np.int16)
                    audio_int16 = mono_audio
                except ValueError as e:
                    logger.warning(f"[Resample] Reshape to stereo failed (size {audio_int16.size}), assuming mono. Error: {e}")
            else: 
                logger.warning(f"[Resample] Odd number of samples ({audio_int16.size}) for stereo input, processing as mono.")

        if audio_int16.size == 0: return b''

        if original_sr != target_sr:
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_float32).unsqueeze(0)

            resampler = torchaudio.transforms.Resample(orig_freq=original_sr, new_freq=target_sr)
            resampled_tensor = resampler(audio_tensor)

            resampled_audio_float = resampled_tensor.squeeze(0).numpy()
            resampled_int16 = (resampled_audio_float * 32768.0).astype(np.int16)
            return resampled_int16.tobytes()
        else: 
            return audio_int16.tobytes()

    except Exception as e:
        logger.error(f"[Resample] 音訊重取樣/轉換失敗 from {original_sr}/{num_channels}ch to {target_sr}/1ch: {e}", exc_info=debug)
        return pcm_data


class GeminiLiveSink(AudioSink):
    def __init__(self, gemini_session, guild_id: int, user_id: int, text_channel: discord.TextChannel):
        super().__init__()
        self.gemini_session = gemini_session
        self.guild_id = guild_id
        self.user_id = user_id
        self.text_channel = text_channel
        self.opus_decoder = None
        self.DISCORD_PCM_SR = 48000 
        self.DISCORD_PCM_CHANNELS = 2
        try:
            if opus.is_loaded():
                 self.opus_decoder = opus.Decoder(self.DISCORD_PCM_SR, self.DISCORD_PCM_CHANNELS)
            else:
                logger.warning("Opus library not loaded. Opus decoding in GeminiLiveSink will not be possible.")
        except Exception as e:
            logger.error(f"Failed to create Opus decoder in GeminiLiveSink: {e}")

    def write(self, ssrc: int, data: voice_recv.VoiceData):
        if not self.gemini_session or not data.user or data.user.id != self.user_id:
            return

        vc = voice_clients.get(self.guild_id)
        if vc and vc.is_playing():
            return

        if self.guild_id in live_sessions and live_sessions[self.guild_id].get("is_bot_speaking_tts", False):
            return
        
        if self.guild_id in live_sessions and live_sessions[self.guild_id].get("is_bot_speaking_live_api", False):
            return

        original_pcm = data.pcm
        source_sr = self.DISCORD_PCM_SR
        source_channels = self.DISCORD_PCM_CHANNELS

        if not original_pcm:
            if data.opus and self.opus_decoder:
                try:
                    original_pcm = self.opus_decoder.decode(data.opus, fec=False)
                    source_sr = self.DISCORD_PCM_SR 
                    source_channels = self.DISCORD_PCM_CHANNELS
                except opus.OpusError as e:
                    logger.error(f"Opus decode error: {e}")
                    return
            else:
                if not self.opus_decoder and data.opus:
                    logger.warning("Opus data received but no Opus decoder available in GeminiLiveSink.")
                return
        
        if not original_pcm:
            return


        resampled_mono_pcm = resample_audio(
            original_pcm,
            source_sr,
            GEMINI_AUDIO_INPUT_SAMPLING_RATE,
            source_channels
        )

        if resampled_mono_pcm:
            try:
                asyncio.create_task(
                    self.gemini_session.send(
                        input={"data": resampled_mono_pcm, "mime_type": "audio/pcm"}
                    )
                )
            except Exception as e:
                logger.error(f"[GeminiLiveSink] Error sending audio to Gemini Live: {e}", exc_info=debug)
                asyncio.run_coroutine_threadsafe(_cleanup_live_session(self.guild_id, f"Error sending audio: {e}"), bot.loop)


    def wants_opus(self) -> bool:
        return False 

    def cleanup(self):
        logger.info(f"[GeminiLiveSink] Cleanup called for guild {self.guild_id}, user {self.user_id}.")
        if hasattr(self, 'opus_decoder') and self.opus_decoder:
            del self.opus_decoder 
            self.opus_decoder = None


class GeminiAudioStreamSource(discord.AudioSource):
    def __init__(self, audio_queue: asyncio.Queue, guild_id: int):
        super().__init__()
        self.audio_queue = audio_queue
        self.guild_id = guild_id
        self.buffer = bytearray()
        self.SAMPLING_RATE = GEMINI_AUDIO_OUTPUT_SAMPLING_RATE
        self.CHANNELS = GEMINI_AUDIO_OUTPUT_CHANNELS
        self.SAMPLE_WIDTH = GEMINI_AUDIO_OUTPUT_SAMPLE_WIDTH
        
        self.FRAME_DURATION_MS = 20
        self.SAMPLES_PER_FRAME = int(self.SAMPLING_RATE * self.FRAME_DURATION_MS / 1000)
        self.FRAME_SIZE = self.SAMPLES_PER_FRAME * self.CHANNELS * self.SAMPLE_WIDTH
        self._finished_flag = asyncio.Event()

    def read(self) -> bytes:
        while len(self.buffer) < self.FRAME_SIZE:
            try:
                chunk = self.audio_queue.get_nowait()
                if chunk is None: 
                    self._finished_flag.set()
                    logger.info(f"[GeminiAudioStreamSource] End of stream sentinel received for guild {self.guild_id}.")
                    if self.buffer:
                        data_to_send = self.buffer
                        self.buffer = bytearray()
                        return bytes(data_to_send)
                    return b''
                self.buffer.extend(chunk)
            except asyncio.QueueEmpty:
                if self._finished_flag.is_set() and not self.buffer: 
                    return b''
                return b''

        frame_data = self.buffer[:self.FRAME_SIZE]
        self.buffer = self.buffer[self.FRAME_SIZE:]
        return bytes(frame_data)

    def is_opus(self) -> bool:
        return False

    def cleanup(self):
        logger.info(f"[GeminiAudioStreamSource] Cleanup called for guild {self.guild_id}.")
        self._finished_flag.set()
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info(f"[GeminiAudioStreamSource] Playback queue drained for guild {self.guild_id}.")
        if self.guild_id in live_sessions:
            live_sessions[self.guild_id]["is_bot_speaking_live_api"] = False


async def _receive_gemini_audio_task(guild_id: int):
    if guild_id not in live_sessions:
        logger.error(f"[_receive_gemini_audio_task] No live session for guild {guild_id}.")
        return

    session_data = live_sessions[guild_id]
    gemini_api_session = session_data["session"]
    playback_queue = session_data["playback_queue"]
    text_channel = session_data["text_channel"]
    user = session_data.get("user_object") 

    logger.info(f"[_receive_gemini_audio_task] Started for guild {guild_id}")
    full_response_text = []

    try:
        async for response in gemini_api_session.receive():
            if response.data: 
                await playback_queue.put(response.data)
            if response.text: 
                logger.info(f"[_receive_gemini_audio_task] Received text: '{response.text}' for guild {guild_id}")
                full_response_text.append(response.text)

        logger.info(f"[_receive_gemini_audio_task] Gemini stream ended for guild {guild_id}.")

    except Exception as e:
        logger.error(f"[_receive_gemini_audio_task] Error receiving from Gemini for guild {guild_id}: {e}", exc_info=debug)
        if text_channel:
            try: await text_channel.send(f"⚠️ 與AI語音助理通訊時發生錯誤: {e}")
            except discord.HTTPException: pass
    finally:
        logger.info(f"[_receive_gemini_audio_task] Finalizing for guild {guild_id}.")
        await playback_queue.put(None) 

        if full_response_text and text_channel:
            final_text = "".join(full_response_text).strip()
            if final_text:
                try:
                    user_mention = user.mention if user else "User"
                    await text_channel.send(f"🤖 **{bot_name} (Live Audio Response to {user_mention}):**\n{final_text}")
                except discord.HTTPException as e:
                    logger.error(f"Failed to send aggregated text from Live API to {text_channel.id}: {e}")
        
        if guild_id in live_sessions and "audio_output_task" in live_sessions[guild_id] and live_sessions[guild_id].get("audio_output_task") is asyncio.current_task():
             logger.info(f"Gemini receive task ended naturally for guild {guild_id}. Session might persist for user input or bot reply.")


async def _play_gemini_audio(guild_id: int):
    if guild_id not in live_sessions: return
    
    vc = voice_clients.get(guild_id)
    session_data = live_sessions[guild_id]
    playback_queue = session_data["playback_queue"]

    if not vc or not vc.is_connected():
        logger.error(f"[_play_gemini_audio] Voice client not connected for guild {guild_id}. Cannot play.")
        await _cleanup_live_session(guild_id, "VC disconnected before playback.")
        return

    audio_source = GeminiAudioStreamSource(playback_queue, guild_id)

    def after_playback(error):
        logger.info(f"[_play_gemini_audio][AfterCallback] Playback finished for guild {guild_id}. Error: {error}")
        if error: logger.error(f"Playback error in guild {guild_id}: {error}")
        
        audio_source.cleanup()

        if guild_id in live_sessions:
            live_sessions[guild_id]["is_bot_speaking_live_api"] = False
            gemini_session = live_sessions[guild_id].get("session")
            text_channel = live_sessions[guild_id].get("text_channel")
            current_bot_loop = bot.loop 
            
            if gemini_session:
                logger.info(f"[_play_gemini_audio][AfterCallback] Bot finished speaking. Signaling end_of_turn to Gemini for guild {guild_id}.")
                coro_send = gemini_session.send(input=".", end_of_turn=True)
                asyncio.run_coroutine_threadsafe(coro_send, current_bot_loop)
                
                if text_channel and "user_object" in live_sessions[guild_id] and live_sessions[guild_id]["user_object"] is not None : 
                    try: 
                        msg_content = f"🎤 {live_sessions[guild_id]['user_object'].mention}, 你可以繼續說話了，或使用 `/stop_live_chat` 結束。"
                        coro_msg = text_channel.send(msg_content)
                        asyncio.run_coroutine_threadsafe(coro_msg, current_bot_loop)
                    except Exception as e_text:
                        logger.error(f"Error sending post-playback message in after_playback: {e_text}")
            else: 
                 logger.warning(f"[_play_gemini_audio][AfterCallback] Gemini session not found for guild {guild_id} after playback.")
        else:
            logger.warning(f"[_play_gemini_audio][AfterCallback] Live session data not found for guild {guild_id} after playback.")


    logger.info(f"[_play_gemini_audio] Starting playback for guild {guild_id}")
    if guild_id in live_sessions:
        live_sessions[guild_id]["is_bot_speaking_live_api"] = True

    vc.play(audio_source, after=after_playback)


async def _cleanup_live_session(guild_id: int, reason: str = "Unknown"):
    logger.info(f"Attempting to cleanup live session for guild {guild_id}. Reason: {reason}")
    if guild_id in live_sessions:
        session_data = live_sessions.pop(guild_id)
        
        gemini_api_session = session_data.get("session")
        audio_output_task = session_data.get("audio_output_task")
        playback_queue = session_data.get("playback_queue")
        text_channel = session_data.get("text_channel")
        user_id = session_data.get("user_id")

        vc = voice_clients.get(guild_id)
        if vc and hasattr(vc, 'is_listening') and vc.is_listening():
            current_sink = getattr(vc, '_sink', None) 
            if isinstance(current_sink, GeminiLiveSink) and current_sink.user_id == user_id:
                logger.info(f"Stopping listening for GeminiLiveSink in guild {guild_id}")
                try:
                    vc.stop_listening()
                except Exception as e:
                    logger.error(f"Error stopping listening during cleanup: {e}")


        if audio_output_task and not audio_output_task.done():
            logger.info(f"Cancelling Gemini audio output task for guild {guild_id}")
            audio_output_task.cancel()
            try: await audio_output_task
            except asyncio.CancelledError: logger.info(f"Audio output task cancelled for guild {guild_id}.")
            except Exception as e: logger.error(f"Error during audio output task cancellation for guild {guild_id}: {e}")

        if playback_queue:
            logger.info(f"Cleaning up playback queue for guild {guild_id}")
            await playback_queue.put(None) 
            while not playback_queue.empty():
                try: playback_queue.get_nowait()
                except asyncio.QueueEmpty: break
        
        if gemini_api_session:
            logger.info(f"Closing Gemini Live API session for guild {guild_id}")
            try:
                 pass 
            except Exception as e:
                logger.error(f"Error trying to close Gemini Live API session for guild {guild_id}: {e}")

        logger.info(f"Live session cleanup finished for guild {guild_id}.")
        if text_channel:
            try: await text_channel.send(f"🔴 即時語音對話已結束。 ({reason})")
            except discord.HTTPException: pass
    else:
        logger.info(f"No active live session found for guild {guild_id} to cleanup.")

@bot.tree.command(name='join', description="讓機器人加入您所在的語音頻道")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ 您需要先加入一個語音頻道才能邀請我！", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    channel = interaction.user.voice.channel
    guild = interaction.guild
    guild_id = guild.id

    if guild_id in voice_clients and voice_clients[guild_id].is_connected():
        vc = voice_clients[guild_id]
        if vc.channel == channel:
            await interaction.followup.send("⚠️ 我已經在您的語音頻道中了。", ephemeral=True)
            return
        else:
            logger.info(f"Bot moving from '{vc.channel.name}' to '{channel.name}' in guild {guild_id}")
            if guild_id in live_sessions:
                await _cleanup_live_session(guild_id, "Bot moved to a new channel.")
            try:
                await vc.move_to(channel)
                voice_clients[guild_id] = vc 
                await interaction.followup.send(f"✅ 已移動到語音頻道 <#{channel.id}>。", ephemeral=True)
            except Exception as e:
                logger.exception(f"Failed to move voice channel for guild {guild_id}: {e}")
                await interaction.followup.send("❌ 移動語音頻道時發生錯誤。", ephemeral=True)
                if guild_id in voice_clients: del voice_clients[guild_id]
                return
    else:
        logger.info(f"Join request from {interaction.user.name} for channel '{channel.name}' (Guild: {guild_id})")
        if guild_id in voice_clients: 
            del voice_clients[guild_id]
        if guild_id in live_sessions: 
            await _cleanup_live_session(guild_id, "Bot joining channel, cleaning up prior session state.")
        try:
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, timeout=60.0, reconnect=True)
            voice_clients[guild_id] = vc
            await interaction.followup.send(f"✅ 已加入語音頻道 <#{channel.id}>！請使用 `/live_chat` 開始即時對話。", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error joining voice channel '{channel.name}': {e}")
            await interaction.followup.send("❌ 加入語音頻道時發生錯誤。", ephemeral=True)
            if guild_id in voice_clients: del voice_clients[guild_id]
            return

@bot.tree.command(name='leave', description="讓機器人離開語音頻道")
async def leave(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    logger.info(f"Leave request from {interaction.user.name} (Guild: {guild_id})")

    await interaction.response.defer(ephemeral=True)

    if guild_id in live_sessions:
        await _cleanup_live_session(guild_id, "Leave command issued.")

    vc = voice_clients.get(guild_id)
    if vc and vc.is_connected():
        try:
            if hasattr(vc, 'is_listening') and vc.is_listening():
                vc.stop_listening()
            await vc.disconnect(force=False) 
            logger.info(f"Successfully disconnected from voice channel in guild {guild_id}.")
            await interaction.followup.send("👋 掰掰！我已經離開語音頻道了。", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error during voice disconnect for guild {guild_id}: {e}")
            await interaction.followup.send("❌ 離開語音頻道時發生錯誤。", ephemeral=True)
        finally:
            if guild_id in voice_clients: del voice_clients[guild_id]
            if guild_id in listening_guilds: del listening_guilds[guild_id]
    else:
        logger.info(f"Leave command used but bot was not connected in guild {guild_id}.")
        await interaction.followup.send("⚠️ 我目前不在任何語音頻道中。", ephemeral=True)
        if guild_id in voice_clients: del voice_clients[guild_id]

@bot.tree.command(name="live_chat", description=f"與 {bot_name} 開始即時語音對話 (使用 Gemini Live API)")
async def live_chat(interaction: discord.Interaction):
    if gemini_live_client_instance is None:
        # Check if already responded (e.g. if defer was called before this check)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ 抱歉，AI語音對話功能目前無法使用 (Live Client 初始化失敗)。", ephemeral=True)
        else:
            await interaction.followup.send("❌ 抱歉，AI語音對話功能目前無法使用 (Live Client 初始化失敗)。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    user = interaction.user

    if guild_id in live_sessions:
        active_user_id = live_sessions[guild_id].get("user_id")
        active_user = interaction.guild.get_member(active_user_id) if active_user_id else None
        active_user_name = active_user.display_name if active_user else f"User ID {active_user_id}"
        msg = f"⚠️ 目前已經有一個即時語音對話正在進行中 (由 {active_user_name} 發起)。請等待再試或請該用戶使用 `/stop_live_chat` 結束。"
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
        return

    # Defer ONCE here if no response has been made yet.
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    vc = voice_clients.get(guild_id)
    if not vc or not vc.is_connected():
        if user.voice and user.voice.channel:
            try:
                logger.info(f"User {user.id} initiated live_chat while bot not in VC. Attempting to join {user.voice.channel.name}.")
                vc = await user.voice.channel.connect(cls=voice_recv.VoiceRecvClient, timeout=60.0, reconnect=True)
                voice_clients[guild_id] = vc
                # No message here, will be covered by "Starting session..."
            except Exception as e:
                logger.error(f"Failed to auto-join voice channel for live_chat: {e}")
                await interaction.edit_original_response(content=f"❌ 我需要先加入一個語音頻道。嘗試自動加入您的頻道失敗: {e}")
                return
        else:
            await interaction.edit_original_response(content=f"❌ 我目前不在語音頻道中，且您也需要先加入一個語音頻道。請先使用 `/join`。")
            return

    if not isinstance(vc, voice_recv.VoiceRecvClient):
        await interaction.edit_original_response(content="❌ 語音客戶端類型不正確，無法開始即時對話。請嘗試重新 `/join`。")
        logger.error(f"VoiceClient for guild {guild_id} is not VoiceRecvClient. Type: {type(vc)}")
        return

    if not user.voice or user.voice.channel != vc.channel:
        await interaction.edit_original_response(content=f"❌ 您需要和我在同一個語音頻道 (<#{vc.channel.id}>) 才能使用此指令。")
        return
    
    await interaction.edit_original_response(content=f"⏳ 正在啟動與 {bot_name} 的即時語音對話... 請等候。")

    try:
        logger.info(f"Initiating Gemini Live session for guild {guild_id}, user {user.id}")
        async with gemini_live_client_instance.aio.live.connect(
            model=GEMINI_LIVE_MODEL_NAME,
            config=GEMINI_LIVE_CONNECT_CONFIG
        ) as api_session:

            logger.info(f"Gemini Live session established for guild {guild_id}")

            playback_queue = asyncio.Queue()
            live_sessions[guild_id] = {
                "session": api_session,
                "playback_queue": playback_queue,
                "user_id": user.id,
                "user_object": user,
                "text_channel": interaction.channel,
                "audio_output_task": None,
                "is_bot_speaking_live_api": False,
                "is_bot_speaking_tts": False
            }

            recv_task = bot.loop.create_task(_receive_gemini_audio_task(guild_id))
            live_sessions[guild_id]["audio_output_task"] = recv_task
            bot.loop.create_task(_play_gemini_audio(guild_id))

            sink = GeminiLiveSink(api_session, guild_id, user.id, interaction.channel)
            vc.listen(sink)
            logger.info(f"Bot is now listening for live chat in guild {guild_id} with GeminiLiveSink.")
            
            await interaction.edit_original_response(content=f"✅ {bot_name} 正在聽你說話！請開始說話。使用 `/stop_live_chat` 結束。")

    except Exception as e:
        logger.exception(f"Error starting live_chat for guild {guild_id}: {e}")
        try:
            await interaction.edit_original_response(content=f"❌ 啟動即時語音對話失敗: {e}")
        except discord.NotFound: # Original deferred message might have expired or been dismissed
            await interaction.followup.send(f"❌ 啟動即時語音對話失敗: {e}", ephemeral=True)
        except discord.InteractionResponded: # Should not happen if logic is correct, but as a fallback
             await interaction.followup.send(f"❌ 啟動即時語音對話失敗: {e}", ephemeral=True)
        await _cleanup_live_session(guild_id, f"Failed to start: {e}")


@bot.tree.command(name="stop_live_chat", description="結束目前的即時語音對話")
async def stop_live_chat(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    await interaction.response.defer(ephemeral=True)

    if guild_id not in live_sessions:
        await interaction.followup.send("⚠️ 目前沒有進行中的即時語音對話。", ephemeral=True)
        return


    logger.info(f"User {interaction.user.id} requested to stop live chat in guild {guild_id}.")
    await _cleanup_live_session(guild_id, f"Stopped by user {interaction.user.id}")
    await interaction.followup.send("✅ 即時語音對話已結束。", ephemeral=True)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    guild_id = guild.id

    if member.id == bot.user.id:
        if before.channel and not after.channel: 
            logger.warning(f"Bot was disconnected from voice channel '{before.channel.name}' in guild {guild_id}.")
            await _cleanup_live_session(guild_id, "Bot disconnected from voice channel.")
            if guild_id in voice_clients: del voice_clients[guild_id]
            if guild_id in listening_guilds: del listening_guilds[guild_id]
        return

    if guild_id in live_sessions:
        session_data = live_sessions[guild_id]
        session_user_id = session_data.get("user_id")
        vc = voice_clients.get(guild_id)

        if member.id == session_user_id: 
            if vc and vc.channel:
                if after.channel != vc.channel: 
                    logger.info(f"User {member.id} (in live session) left bot's channel in guild {guild_id}. Cleaning up.")
                    await _cleanup_live_session(guild_id, "User left voice channel during session.")
            elif not after.channel: 
                logger.info(f"User {member.id} (in live session) disconnected from voice in guild {guild_id}. Cleaning up.")
                await _cleanup_live_session(guild_id, "User disconnected during session.")
    
    if before.channel and before.channel != after.channel: 
        vc = voice_clients.get(guild_id)
        if vc and vc.is_connected() and vc.channel == before.channel:
            await asyncio.sleep(2.0) 
            current_vc = voice_clients.get(guild_id) 
            if current_vc and current_vc.is_connected() and current_vc.channel == before.channel:
                human_members = [m for m in current_vc.channel.members if not m.bot]
                if not human_members:
                    logger.info(f"Bot is alone in channel '{current_vc.channel.name}' (Guild: {guild_id}). Auto-leaving.")
                    await _cleanup_live_session(guild_id, "Auto-leave, bot alone in channel.")
                    try:
                        await current_vc.disconnect(force=False)
                    except Exception as e: logger.error(f"Error during auto-leave disconnect: {e}")
                    finally:
                        if guild_id in voice_clients: del voice_clients[guild_id]
                        if guild_id in listening_guilds: del listening_guilds[guild_id]

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or not message.guild or message.author.bot:
        return

    guild_id = message.guild.id
    user_id = str(message.author.id)
    user_name = message.author.name
    channel = message.channel
    current_time = get_current_time_utc8()

    db_path_analytics = get_db_path(guild_id, 'analytics')
    conn_analytics = None
    try:
        conn_analytics = sqlite3.connect(db_path_analytics, timeout=10)
        cursor_analytics = conn_analytics.cursor()
        cursor_analytics.execute("INSERT OR IGNORE INTO users (user_id, user_name, join_date) VALUES (?, ?, ?)",
                                 (user_id, user_name, current_time))
        cursor_analytics.execute("UPDATE users SET message_count = message_count + 1, user_name = ? WHERE user_id = ?",
                                 (user_name, user_id))
        cursor_analytics.execute("INSERT INTO messages (user_id, user_name, channel_id, timestamp, content) VALUES (?, ?, ?, ?, ?)",
                                 (user_id, user_name, str(channel.id), current_time, message.content))
        conn_analytics.commit()
    except sqlite3.Error as e:
        logger.error(f"Analytics DB error in on_message for guild {guild_id}: {e}")
    finally:
        if conn_analytics:
            conn_analytics.close()

    if guild_id not in WHITELISTED_SERVERS:
        return

    server_index = servers.index(guild_id) if guild_id in servers else -1
    if server_index == -1:
        logger.warning(f"Guild {guild_id} is in WHITELISTED_SERVERS but not in 'servers' list. Skipping AI response.")
        return
        
    is_review_channel = (channel.id == TARGET_CHANNEL_ID[server_index])
    is_review_command = message.content.startswith(review_format)

    if is_review_channel and is_review_command:
        db_path_analytics = get_db_path(guild_id, 'analytics')
        conn_analytics_review = None
        try:
            conn_analytics_review = sqlite3.connect(db_path_analytics, timeout=10)
            cursor_review = conn_analytics_review.cursor()
            
            parts = message.content.split(" ")
            if len(parts) >= 2:
                user_to_review_mention = parts[1]
                match = re.match(r"<@!?(\d+)>", user_to_review_mention)
                if match:
                    user_to_review_id = match.group(1)
                    cursor_review.execute("SELECT user_id FROM reviews WHERE user_id = ? AND review_date = ?", 
                                          (user_to_review_id, datetime.now(pytz.timezone('Asia/Taipei')).strftime("%Y-%m-%d")))
                    if cursor_review.fetchone():
                        await message.channel.send(f"{message.author.mention} 這位成員今天已經審核過了。")
                        return
                    
                    cursor_review.execute("INSERT INTO reviews (user_id, review_date) VALUES (?, ?)",
                                          (user_to_review_id, datetime.now(pytz.timezone('Asia/Taipei')).strftime("%Y-%m-%d")))
                    conn_analytics_review.commit()
                    
                    user_to_review = message.guild.get_member(int(user_to_review_id))
                    if user_to_review:
                        try:
                            newcomer_role_id = newcomer_channel_id[server_index]
                            role_to_remove = message.guild.get_role(newcomer_role_id)
                            if role_to_remove:
                                await user_to_review.remove_roles(role_to_remove)
                                await message.channel.send(f"{user_to_review_mention} 已成功審核，並移除了 '{role_to_remove.name}' 身分組。")
                                logger.info(f"User {user_to_review_id} reviewed by {user_id}. Role {newcomer_role_id} removed.")
                            else:
                                await message.channel.send(f"{user_to_review_mention} 審核記錄已登記，但找不到要移除的身分組 '{newcomer_role_id}'。")
                                logger.warning(f"Role {newcomer_role_id} not found for removal after review for user {user_to_review_id}.")
                        except discord.Forbidden:
                            await message.channel.send(f"{user_to_review_mention} 審核記錄已登記，但我沒有權限移除其身分組。")
                            logger.error(f"Forbidden to remove role for {user_to_review_id} after review.")
                        except Exception as e:
                            await message.channel.send(f"{user_to_review_mention} 審核記錄已登記，但在操作身分組時發生錯誤。")
                            logger.exception(f"Error changing roles for {user_to_review_id} after review: {e}")
                    else:
                        await message.channel.send(f"審核記錄已登記，但找不到該成員 {user_to_review_mention}。")
                        logger.warning(f"User {user_to_review_id} not found in guild for review completion.")
                else:
                    await message.channel.send("審核指令格式錯誤，請提及要審核的成員 (例如 `@使用者`)。")
            else:
                await message.channel.send("審核指令格式錯誤，請使用 `{review_format} @使用者`。")

        except sqlite3.Error as e:
            logger.error(f"Analytics DB error during review process for guild {guild_id}: {e}")
            await message.channel.send("處理審核時資料庫發生錯誤。")
        finally:
            if conn_analytics_review:
                conn_analytics_review.close()
        return


    should_respond = (
        (bot.user.mentioned_in(message) and message.mention_everyone is False) or
        (isinstance(channel, discord.DMChannel) and message.author != bot.user)
    )

    if should_respond:
        if text_model is None:
             logger.warning(f"Ignoring mention/command in guild {guild_id} because Gemini TEXT model is not available.")
             await channel.send("抱歉，AI 功能目前暫時無法使用。")
             return

        current_points = None
        if Point_deduction_system[server_index]:
            db_path_points = get_db_path(guild_id, 'points')
            conn_points = None
            try:
                conn_points = sqlite3.connect(db_path_points, timeout=10)
                cursor_points = conn_points.cursor()
                cursor_points.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
                result = cursor_points.fetchone()
                if result:
                    current_points = result[0]
                    if current_points <= 0:
                        await channel.send(f"{message.author.mention} 您的點數不足，無法使用 AI 對話功能。")
                        logger.info(f"User {user_id} has {current_points} points, denied AI usage.")
                        return
                    
                    new_points = current_points - 1
                    cursor_points.execute("UPDATE users SET points = ? WHERE user_id = ?", (new_points, user_id))
                    cursor_points.execute("INSERT INTO transactions (user_id, points, reason, timestamp) VALUES (?, ?, ?, ?)",
                                          (user_id, -1, f"AI query: {message.content[:50]}", current_time))
                    conn_points.commit()
                    logger.info(f"User {user_id} used 1 point for AI query. New balance: {new_points}.")
                else:
                    await channel.send(f"{message.author.mention} 系統中找不到您的點數資料，請聯繫管理員。")
                    logger.warning(f"User {user_id} not found in points DB for guild {guild_id}.")
                    return 
            except sqlite3.Error as e:
                logger.error(f"Points DB error for user {user_id} in guild {guild_id}: {e}")
                await channel.send("查詢點數時發生錯誤，請稍後再試。")
                return
            finally:
                if conn_points:
                    conn_points.close()
        
        cleaned_message = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not cleaned_message:
            cleaned_message = "你好"

        async with channel.typing():
            try:
                db_path_chat = get_db_path(guild_id, 'chat')
                conn_chat = sqlite3.connect(db_path_chat, timeout=10)
                cursor_chat = conn_chat.cursor()

                cursor_chat.execute("SELECT user, content FROM message WHERE user = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
                history_data = cursor_chat.fetchall()
                
                chat_history_processed = []
                for row in reversed(history_data): 
                    role = "user" if row[0] == user_id else "model"
                    chat_history_processed.append({"role": role, "parts": [{"text": row[1]}]})
                
                logger.debug(f"Chat history for {user_id} (last {len(chat_history_processed)} turns): {chat_history_processed}")

                chat = text_model.start_chat(history=chat_history_processed)
                
                logger.info(f"Sending to Gemini (Text): '{cleaned_message[:100]}' for user {user_id} in guild {guild_id}")
                response = await chat.send_message_async(
                    cleaned_message,
                    safety_settings=safety_settings,
                    generation_config=genai_types.GenerationConfig(temperature=0.7, top_p=0.9, top_k=40)
                )
                ai_response_text = response.text
                logger.info(f"Received from Gemini (Text): '{ai_response_text[:100]}' for user {user_id}")

                cursor_chat.execute("INSERT INTO message (user, content, timestamp) VALUES (?, ?, ?)",
                                    (user_id, cleaned_message, current_time))
                cursor_chat.execute("INSERT INTO message (user, content, timestamp) VALUES (?, ?, ?)",
                                    (str(bot.user.id), ai_response_text, get_current_time_utc8())) 
                conn_chat.commit()
                conn_chat.close()

                if len(ai_response_text) > 2000:
                    parts = [ai_response_text[i:i+1990] for i in range(0, len(ai_response_text), 1990)]
                    for part_idx, part in enumerate(parts):
                        if part_idx == 0:
                            await message.reply(part)
                        else:
                            await channel.send(part)
                else:
                    await message.reply(ai_response_text)

            except Exception as e:
                logger.exception(f"Error during Gemini text interaction for user {user_id}: {e}")
                await channel.send(f"抱歉，我在處理您的請求時遇到了一些問題：{e}")
                if Point_deduction_system[server_index] and current_points is not None: 
                    conn_points_refund = None
                    try:
                        conn_points_refund = sqlite3.connect(get_db_path(guild_id, 'points'), timeout=10)
                        cursor_refund = conn_points_refund.cursor()
                        cursor_refund.execute("UPDATE users SET points = points + 1 WHERE user_id = ?", (user_id,))
                        cursor_refund.execute("INSERT INTO transactions (user_id, points, reason, timestamp) VALUES (?, ?, ?, ?)",
                                              (user_id, 1, f"Refund for AI error: {str(e)[:50]}", get_current_time_utc8()))
                        conn_points_refund.commit()
                        logger.info(f"Refunded 1 point to user {user_id} due to AI error.")
                    except sqlite3.Error as db_e:
                        logger.error(f"Failed to refund point to user {user_id}: {db_e}")
                    finally:
                        if conn_points_refund:
                            conn_points_refund.close()


def bot_run():
    if not discord_bot_token:
        logger.critical("設定檔中未設定 Discord Bot Token！機器人無法啟動。")
        return
    if not API_KEY:
        logger.warning("設定檔中未設定 Gemini API Key！AI 功能可能部分受限。")

    if not opus.is_loaded():
        try:
            opus_libs = ['opus', 'libopus-0.dll', 'libopus.so.0', 'libopus.0.dylib', 'opus.dll']
            loaded = False
            for lib_name in opus_libs:
                try:
                    opus.load_opus(lib_name)
                    logger.info(f"Opus library loaded successfully using '{lib_name}'.")
                    loaded = True
                    break
                except opus.OpusNotLoaded:
                    continue
            if not loaded:
                 logger.error("Failed to load opus library automatically. Please ensure libopus is installed and accessible.")
                 logger.warning("Voice functionality might be impaired.")

        except Exception as e:
            logger.error(f"Unexpected error loading opus: {e}")
            logger.warning("Voice functionality might be impaired.")


    logger.info("正在嘗試啟動 Discord 機器人...")
    try:
        bot.run(discord_bot_token, log_handler=None, reconnect=True)
    except discord.errors.LoginFailure: logger.critical("登入失敗: 無效的 Discord Bot Token。")
    except discord.PrivilegedIntentsRequired: logger.critical("登入失敗: 需要 Privileged Intents 但未啟用。")
    except discord.HTTPException as e: logger.critical(f"無法連接到 Discord (HTTP Exception): {e}")
    except KeyboardInterrupt: logger.info("收到關閉信號 (KeyboardInterrupt)，正在關閉機器人...")
    except Exception as e: logger.critical(f"運行機器人時發生嚴重錯誤: {e}", exc_info=True)
    finally:
        logger.info("機器人主進程已停止。")


if __name__ == "__main__":
    if init_db: 
        try:
            init_db() 
        except Exception as e:
            logger.error(f"Global init_db call failed: {e}")

    logger.info("從主執行緒啟動機器人...")
    bot_run()
    logger.info("機器人執行完畢。")

__all__ = ['bot_run', 'bot']