# -*- coding: utf-8 -*-
import asyncio
import traceback
from discord.ext.voice_recv import BasicSink # Kept for reference, but new sink will be used for Live API
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
from google.generativeai import types as types # Renamed to avoid conflict
from google import genai
from google.genai import types
import requests
from bs4 import BeautifulSoup
import time
import re
import pytz
from collections import defaultdict, deque
from typing import Optional, Dict, Set, Any, List, Tuple, Union

import queue # Standard queue, asyncio.Queue will be used for async tasks
import threading # Less used with asyncio, but good to be aware of
from nana_bot import (
    bot,
    bot_name,
    WHITELISTED_SERVERS,
    TARGET_CHANNEL_ID,
    API_KEY,
    init_db, # This function might need to be defined or imported if it's not part of this snippet
    gemini_model as gemini_model_name, # Renamed to avoid conflict with the model instance
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
# import whisper # Whisper will be less used if Live API is the primary voice interaction

import tempfile
import edge_tts
import functools
import wave
import uuid
import io

# --- Global Variables for STT/VAD (Original Bot) ---
# These are for the original Whisper-based STT.
# whisper_model = None # This would be loaded in bot_run
# vad_model = None     # This would be loaded in bot_run

# VAD_SAMPLE_RATE = 16000
# VAD_EXPECTED_SAMPLES = 512
# VAD_CHUNK_SIZE_BYTES = VAD_EXPECTED_SAMPLES * 2
# VAD_THRESHOLD = 0.5
# VAD_MIN_SILENCE_DURATION_MS = 700
# VAD_SPEECH_PAD_MS = 200

# audio_buffers = defaultdict(lambda: {
#     'buffer': bytearray(),
#     'pre_buffer': bytearray(),
#     'last_speech_time': time.time(),
#     'is_speaking': False
# })
# --- End Original STT/VAD Globals ---


# --- NEW: Gemini Live API Specific Globals & Config ---
gemini_live_client: Optional[Any] = None # Will be the Live API client
live_sessions: Dict[int, Dict[str, Any]] = {} # Stores active live session info per guild_id
# Example: live_sessions[guild_id] = {
#    "session": <Gemini Live Session>,
#    "audio_input_task": <asyncio.Task>, # No longer needed if sink sends directly
#    "audio_output_task": <asyncio.Task>,
#    "playback_queue": <asyncio.Queue>,
#    "user_id": <int>, # User who initiated
#    "text_channel": <discord.TextChannel>
# }

GEMINI_LIVE_MODEL_NAME = "models/gemini-2.5-flash-preview-native-audio-dialog" # Or your preferred streaming model like "gemini-1.5-pro-latest" with "audio" tool.
                                                         # For true native audio dialog: "models/gemini-X-Y-native-audio-dialog" if available
                                                         # The example used "gemini-2.5-flash-preview-native-audio-dialog" - check availability

# Configuration for Gemini Live API
# This config is for models that take audio as part of a multimodal turn.
# For native audio dialog models, the config might be simpler or implicit.
GEMINI_LIVE_CONFIG = types.GenerationConfig(
    # For multimodal models, you might need to specify tools if you want function calling along with audio.
    # For native audio dialog models, this might not be needed or configured differently.
    # The `response_mime_type="audio/wav"` or similar is key if supported.
    # If the model inherently produces audio, this is simpler.
    # The example `LiveConnectConfig` is more for the `client.aio.live.connect` specific API.
    # Let's assume we'll use a model that can take audio in `generate_content` and respond with audio.
    # If using `client.aio.live.connect`, then `LiveConnectConfig` is the way.
)

# If using the `client.aio.live.connect` pattern from the Gemini example:
# Note: "Zephyr" might not be a standard Google voice. Check available prebuilt voices.
# Common voices: "eleven_multilingual_v2" (if using ElevenLabs integration via API features),
# or specific Google voices if listed in their TTS documentation.
# For "native-audio-dialog" models, the voice might be part of the model itself.
# Let's assume a generic placeholder or that the model handles it.
GEMINI_LIVE_CONNECT_CONFIG = types.LiveConnectConfig(
    response_modalities=[
        "AUDIO"
                         ], # Request audio response
    media_resolution="MEDIA_RESOLUTION_MEDIUM",
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    ),
    # context_window_compression=types.ContextWindowCompressionConfig( # Optional
    #     trigger_tokens=25600,
    #     sliding_window=types.SlidingWindow(target_tokens=12800),
    # ),
)
# Use 16kHz for sending to Gemini, as it's common for STT
GEMINI_AUDIO_INPUT_SAMPLING_RATE = 16000
GEMINI_AUDIO_INPUT_CHANNELS = 1
# Gemini Live API typically outputs 24kHz audio
GEMINI_AUDIO_OUTPUT_SAMPLING_RATE = 24000
GEMINI_AUDIO_OUTPUT_CHANNELS = 1
GEMINI_AUDIO_OUTPUT_SAMPLE_WIDTH = 2 # 16-bit
# --- End NEW Gemini Live API Globals ---


# General bot state
listening_guilds: Dict[int, discord.VoiceClient] = {} # Keep this if you have other listening modes
voice_clients: Dict[int, discord.VoiceClient] = {} # Stores current voice client for each guild
# expecting_voice_query_from: Set[int] = set() # Original STT flow
# QUERY_TIMEOUT_SECONDS = 30

safety_settings = {
    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: types.HarmBlockThreshold.BLOCK_NONE,
    types.HarmCategory.HARM_CATEGORY_HARASSMENT: types.HarmBlockThreshold.BLOCK_NONE,
    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: types.HarmBlockThreshold.BLOCK_NONE,
    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: types.HarmBlockThreshold.BLOCK_NONE,
}

DEFAULT_VOICE = "zh-TW-HsiaoYuNeural" # For EdgeTTS
STT_LANGUAGE = "zh" # For Whisper (if used)

logging.basicConfig(level=logging.INFO if not debug else logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("bot.log", encoding='utf-8'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)

# Opus decoder for Discord audio (if needed, usually handled by VoiceData.pcm)
# try:
#     if not opus.is_loaded():
#         opus.load_opus('opus') # Or path to your libopus library
#         logger.info("Opus library loaded successfully.")
# except Exception as e:
#     logger.error(f"Failed to load opus library: {e}. Voice receive might not work.")


async def play_tts(voice_client: discord.VoiceClient, text: str, context: str = "TTS"):
    # This is your original EdgeTTS function. It can remain for non-live text-to-speech needs.
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
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', # For robustness
            'options': '-vn'
        }
        if not os.path.exists(tmp_path):
             logger.error(f"[{context}] 暫存檔案 {tmp_path} 在創建音源前消失了！")
             return

        source = FFmpegPCMAudio(tmp_path, **ffmpeg_options) # FFmpegPCMAudio can be created in main thread
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
            await asyncio.sleep(0.2) # Give a moment for stop to take effect

        step3 = time.time()
        def _cleanup_tts(error, path_to_clean, guild_id_ctx):
            log_prefix = f"[{context}][Cleanup][Guild:{guild_id_ctx}]"
            if error: logger.error(f"{log_prefix} 播放器錯誤: {error}")
            else: logger.info(f"{log_prefix} TTS 播放完成。")

            # NEW: If part of a live session, signal bot's turn is over
            if guild_id_ctx in live_sessions and live_sessions[guild_id_ctx].get("is_bot_speaking_tts"):
                logger.info(f"{log_prefix} TTS for bot turn finished. Signaling end_of_turn for Live API.")
                live_sessions[guild_id_ctx]["is_bot_speaking_tts"] = False
                gemini_session = live_sessions[guild_id_ctx].get("session")
                if gemini_session:
                    asyncio.create_task(gemini_session.send(input=".", end_of_turn=True)) # Send dummy text to signify end of bot's audio turn

            try:
                if path_to_clean and os.path.exists(path_to_clean):
                    os.remove(path_to_clean)
                    logger.info(f"{log_prefix} 已清理暫存檔案: {path_to_clean}")
            except OSError as e: logger.warning(f"{log_prefix} 清理暫存檔案 {path_to_clean} 失敗: {e}")
            except Exception as cleanup_err: logger.error(f"{log_prefix} 清理檔案時發生錯誤: {cleanup_err}")

        # Mark that bot is speaking (for Live API sink to pause sending user audio)
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
                live_sessions[voice_client.guild.id]["is_bot_speaking_tts"] = False # Reset flag
            if tmp_path and os.path.exists(tmp_path):
                logger.warning(f"[{context}][Finally] 播放未成功開始，清理暫存檔案: {tmp_path}")
                try: os.remove(tmp_path)
                except OSError as e: logger.warning(f"[{context}][Finally] 清理未播放的暫存檔案 {tmp_path} 失敗: {e}")
                except Exception as final_e: logger.error(f"[{context}][Finally] 清理未播放檔案時發生錯誤: {final_e}")


def get_current_time_utc8():
    utc8 = timezone(timedelta(hours=8))
    current_time = datetime.now(utc8)
    return current_time.strftime("%Y-%m-%d %H:%M:%S")

# Initialize Gemini Text Model (original)
genai.Client(api_key=API_KEY)
text_model = None # For standard text chat
try:
    if not API_KEY:
        raise ValueError("Gemini API key is not set for text model.")
    text_model = genai_client.get_model(gemini_model_name) # Using the renamed config variable
    logger.info(f"成功初始化 GenerativeModel (Text): {gemini_model_name}")
except Exception as e:
    logger.critical(f"初始化 GenerativeModel (Text) 失敗: {e}")

# Initialize Gemini Live Client (NEW)
try:
    if not API_KEY:
        raise ValueError("Gemini API key is not set for Live client.")
    gemini_live_client_instance = genai.Client(api_key=API_KEY, http_options={"api_version": "v1beta"})
    # Test connection or list models if possible to verify
    # models_list = [m.name for m in gemini_live_client_instance.list_models() if GEMINI_LIVE_MODEL_NAME in m.name]
    # if not models_list:
    #     logger.warning(f"Gemini Live model '{GEMINI_LIVE_MODEL_NAME}' might not be available or client init failed.")
    # else:
    #     logger.info(f"Gemini Live Client initialized. Target model {GEMINI_LIVE_MODEL_NAME} seems available.")
    logger.info(f"Gemini Live Client initialized for use with `client.aio.live.connect`.")
except Exception as e:
    logger.critical(f"初始化 Gemini Live Client 失敗: {e}. Live chat functionality will be disabled.")
    gemini_live_client_instance = None


db_base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "databases")
os.makedirs(db_base_path, exist_ok=True)

def get_db_path(guild_id, db_type):
    # ... (your existing db path logic)
    if db_type == 'analytics': return os.path.join(db_base_path, f"analytics_server_{guild_id}.db")
    elif db_type == 'chat': return os.path.join(db_base_path, f"messages_chat_{guild_id}.db")
    elif db_type == 'points': return os.path.join(db_base_path, f"points_{guild_id}.db")
    else: raise ValueError(f"Unknown database type: {db_type}")

def init_db_for_guild(guild_id):
    # ... (your existing db init logic)
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
    # ... (your existing daily message task)
    logger.info("開始執行每日訊息任務...")
    for idx, server_id in enumerate(servers):
        try:
            if idx < len(send_daily_channel_id_list) and idx < len(not_reviewed_id): # Ensure not_reviewed_id is also checked
                target_channel_id = send_daily_channel_id_list[idx]
                role_to_mention_id = not_reviewed_id[idx] # Assuming this is the role ID list
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
    # ... (your existing before loop logic)
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
        init_db_for_guild(guild.id) # Initialize DB for each guild

    logger.info("正在同步應用程式命令...")
    try:
        # Sync globally first (optional, can also sync per guild)
        # synced_global = await bot.tree.sync()
        # logger.info(f"已全域同步 {len(synced_global)} 個命令。")
        # Sync for each guild (often more reliable for immediate updates)
        for guild in bot.guilds:
            try:
                # bot.tree.copy_global_to(guild=guild) # If you want global commands on specific guilds
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
    # ... (your existing guild join logic)
    logger.info(f"機器人加入新伺服器: {guild.name} (ID: {guild.id})")
    init_db_for_guild(guild.id)
    if guild.id not in servers: logger.warning(f"伺服器 {guild.id} ({guild.name}) 不在設定檔 'servers' 列表中。")

    logger.info(f"正在為新伺服器 {guild.id} 同步命令...")
    try:
        # bot.tree.copy_global_to(guild=guild) # If needed
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
    # This function is very long. I'm assuming its internal logic is mostly correct
    # and it doesn't directly conflict with the new voice chat.
    # I will keep it as is for brevity in this integration example.
    # Ensure `model` is replaced by `text_model` if it refers to the text Gemini model.
    guild = member.guild
    logger.info(f"新成員加入: {member} (ID: {member.id}) 於伺服器 {guild.name} (ID: {guild.id})")

    server_index = -1
    try: server_index = servers.index(guild.id)
    except ValueError:
        logger.warning(f"No configuration found for server ID {guild.id} in on_member_join. ANALYTICS ONLY.")
        # ... (rest of your analytics only path)
        return

    # ... (The rest of your on_member_join logic, ensure `model` is `text_model` if used for text generation)
    # Example modification for Gemini text model usage:
    # if text_model:
    #    try:
    #        # ... your prompt setup
    #        async with welcome_channel.typing():
    #             responses = await text_model.generate_content_async(
    #                 welcome_prompt, safety_settings=safety_settings
    #             )
    #        # ... rest of handling responses
    #    except Exception as e:
    #        # ... error handling
    # else:
    #     # ... fallback if text_model is None
    pass # Placeholder for your extensive on_member_join logic

@bot.event
async def on_member_remove(member: discord.Member):
    # Similar to on_member_join, this is extensive. Assuming it's mostly okay.
    # Key thing for voice: If user was in a live session, clean it up.
    # This is partially handled by on_voice_state_update too.

    # global expecting_voice_query_from # Original STT
    # if member.id in expecting_voice_query_from:
    #     expecting_voice_query_from.remove(member.id)
    #     logger.info(f"Removed user {member.id} from expecting_voice_query_from (left server).")

    # NEW: If user leaving was in a live session, try to clean that session.
    guild_id = member.guild.id
    if guild_id in live_sessions and live_sessions[guild_id].get("user_id") == member.id:
        logger.info(f"User {member.id} who was in a live session left guild {guild_id}. Cleaning up live session.")
        await _cleanup_live_session(guild_id, "User left server during session.")

    # ... (The rest of your on_member_remove logic)
    pass # Placeholder


# --- Audio Processing and STT (Original Bot - Kept for reference or other commands) ---
def resample_audio(pcm_data: bytes, original_sr: int, target_sr: int, num_channels: int = 2) -> bytes:
    """Resamples PCM audio data and converts to mono if stereo."""
    if not pcm_data:
        return b''
    if original_sr == target_sr and num_channels == 1: # Already target format
        return pcm_data

    try:
        audio_int16 = np.frombuffer(pcm_data, dtype=np.int16)

        if audio_int16.size == 0: return b''

        # Convert to mono if stereo
        if num_channels == 2:
            if audio_int16.size % 2 == 0:
                try:
                    stereo_audio = audio_int16.reshape(-1, 2)
                    mono_audio = stereo_audio.mean(axis=1).astype(np.int16)
                    audio_int16 = mono_audio
                except ValueError as e:
                    logger.warning(f"[Resample] Reshape to stereo failed (size {audio_int16.size}), assuming mono. Error: {e}")
                    # If reshape fails, but we were told it's stereo, it's problematic.
                    # Forcing it to be 1 channel for resampler.
                    pass # continue with audio_int16 as is, resampler will handle 1 channel
            else: # Odd number of samples for stereo data is weird
                logger.warning(f"[Resample] Odd number of samples ({audio_int16.size}) for stereo input, processing as mono.")
                # Treat as mono for safety, or take first channel if reshaping is too risky.

        if audio_int16.size == 0: return b'' # Check again after potential mono conversion

        # Resample if necessary
        if original_sr != target_sr:
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_float32).unsqueeze(0) # Add batch dim

            resampler = torchaudio.transforms.Resample(orig_freq=original_sr, new_freq=target_sr)
            resampled_tensor = resampler(audio_tensor)

            resampled_audio_float = resampled_tensor.squeeze(0).numpy()
            resampled_int16 = (resampled_audio_float * 32768.0).astype(np.int16)
            return resampled_int16.tobytes()
        else: # No resampling needed, but was stereo, so return mono version
            return audio_int16.tobytes()

    except Exception as e:
        logger.error(f"[Resample] 音訊重取樣/轉換失敗 from {original_sr}/{num_channels}ch to {target_sr}/1ch: {e}", exc_info=debug)
        return pcm_data # Return original on failure to prevent crash, though it might be wrong format


# async def handle_stt_result(text: str, user: discord.Member, channel: discord.TextChannel):
    # This was for the Whisper STT -> Text Model -> EdgeTTS flow.
    # The new Live API flow handles this differently.
    # It can be kept if you have other commands that use the old Whisper STT.
    # pass

# def process_audio_chunk(...):
    # This was for VAD + feeding Whisper. Not directly used by Gemini Live API flow.
    # pass

# async def run_whisper_transcription(...):
    # This was for Whisper. Not directly used by Gemini Live API flow.
    # pass
# --- End Original Audio Processing ---


# --- NEW: Gemini Live API Audio Handling ---
class GeminiLiveSink(AudioSink):
    """Sends audio data from Discord to an active Gemini Live session."""
    def __init__(self, gemini_session, guild_id: int, user_id: int, text_channel: discord.TextChannel):
        super().__init__()
        self.gemini_session = gemini_session
        self.guild_id = guild_id
        self.user_id = user_id
        self.text_channel = text_channel
        self.opus_decoder = opus.Decoder(discord.opus.SAMPLING_RATE, discord.opus.CHANNELS)

    def write(self, data: voice_recv.VoiceData, user: discord.User):
        if not self.gemini_session or user.id != self.user_id:
            return

        vc = voice_clients.get(self.guild_id)
        if vc and vc.is_playing():
            return

        if self.guild_id in live_sessions and live_sessions[self.guild_id].get("is_bot_speaking_tts", False):
            return

        original_pcm = data.pcm
        if not original_pcm:
            if data.opus:
                try:
                    original_pcm = self.opus_decoder.decode(data.opus, fec=False)
                except opus.OpusError as e:
                    logger.error(f"Opus decode error: {e}")
                    return
            else:
                return

        resampled_mono_pcm = resample_audio(
            original_pcm,
            discord.opus.SAMPLING_RATE,
            GEMINI_AUDIO_INPUT_SAMPLING_RATE,
            discord.opus.CHANNELS
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
                asyncio.create_task(_cleanup_live_session(self.guild_id, f"Error sending audio: {e}"))

    def wants_opus(self) -> bool:
        return False

    def cleanup(self):
        logger.info(f"[GeminiLiveSink] Cleanup called for guild {self.guild_id}, user {self.user_id}.")
        if self.opus_decoder:
            del self.opus_decoder



class GeminiAudioStreamSource(discord.AudioSource):
    """Plays audio from an asyncio.Queue fed by Gemini Live responses."""
    def __init__(self, audio_queue: asyncio.Queue, guild_id: int):
        super().__init__()
        self.audio_queue = audio_queue
        self.guild_id = guild_id
        self.buffer = bytearray()
        # Gemini Live API typically outputs 24kHz, 1-channel, 16-bit PCM
        self.SAMPLING_RATE = GEMINI_AUDIO_OUTPUT_SAMPLING_RATE
        self.CHANNELS = GEMINI_AUDIO_OUTPUT_CHANNELS
        self.SAMPLE_WIDTH = GEMINI_AUDIO_OUTPUT_SAMPLE_WIDTH # Bytes per sample (16-bit = 2 bytes)
        
        # Discord expects audio in 20ms chunks
        self.FRAME_DURATION_MS = 20
        self.SAMPLES_PER_FRAME = int(self.SAMPLING_RATE * self.FRAME_DURATION_MS / 1000)
        self.FRAME_SIZE = self.SAMPLES_PER_FRAME * self.CHANNELS * self.SAMPLE_WIDTH
        self._finished_flag = asyncio.Event() # To signal end of stream

    def read(self) -> bytes:
        # logger.debug(f"[GeminiAudioStreamSource][Read] Buffer size: {len(self.buffer)}, Queue size: {self.audio_queue.qsize()}")
        while len(self.buffer) < self.FRAME_SIZE:
            try:
                # Non-blocking get. If queue is empty, we'll handle it.
                chunk = self.audio_queue.get_nowait()
                if chunk is None: # Sentinel value indicating end of stream
                    self._finished_flag.set()
                    logger.info(f"[GeminiAudioStreamSource] End of stream sentinel received for guild {self.guild_id}.")
                    # If buffer has partial data, send it. Otherwise, send empty.
                    if self.buffer:
                        data_to_send = self.buffer
                        self.buffer = bytearray()
                        return bytes(data_to_send)
                    return b''
                self.buffer.extend(chunk)
                # logger.debug(f"[GeminiAudioStreamSource] Got chunk of {len(chunk)} from queue. Buffer now {len(self.buffer)}")
            except asyncio.QueueEmpty:
                # If queue is empty and buffer doesn't have a full frame,
                # AND we haven't received the finish signal, it means we are waiting for more data.
                # Return empty bytes for now, Discord will call read() again.
                if self._finished_flag.is_set() and not self.buffer: # Truly finished and buffer drained
                    return b''
                # logger.debug(f"[GeminiAudioStreamSource] Queue empty, buffer has {len(self.buffer)}/{self.FRAME_SIZE}. Waiting.")
                return b'' # Not enough data for a frame, and not finished

        frame_data = self.buffer[:self.FRAME_SIZE]
        self.buffer = self.buffer[self.FRAME_SIZE:]
        # logger.debug(f"[GeminiAudioStreamSource] Read {len(frame_data)} bytes. Remaining buffer: {len(self.buffer)}")
        return bytes(frame_data)

    def is_opus(self) -> bool:
        return False # We are providing raw PCM

    def cleanup(self):
        logger.info(f"[GeminiAudioStreamSource] Cleanup called for guild {self.guild_id}.")
        self._finished_flag.set() # Ensure it's set so read() can terminate
        # Drain the queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info(f"[GeminiAudioStreamSource] Playback queue drained for guild {self.guild_id}.")
        # Reset bot speaking state for this guild
        if self.guild_id in live_sessions:
            live_sessions[self.guild_id]["is_bot_speaking_live_api"] = False


async def _receive_gemini_audio_task(guild_id: int):
    """Task to receive audio and text from Gemini Live and manage playback."""
    if guild_id not in live_sessions:
        logger.error(f"[_receive_gemini_audio_task] No live session for guild {guild_id}.")
        return

    session_data = live_sessions[guild_id]
    gemini_api_session = session_data["session"]
    playback_queue = session_data["playback_queue"]
    text_channel = session_data["text_channel"]
    user = session_data.get("user_object") # User who initiated

    logger.info(f"[_receive_gemini_audio_task] Started for guild {guild_id}")
    full_response_text = []

    try:
        async for response in gemini_api_session.receive():
            if response.data: # Audio data
                # logger.debug(f"[_receive_gemini_audio_task] Received {len(response.data)} audio bytes for guild {guild_id}")
                await playback_queue.put(response.data)
            if response.text: # Text data
                logger.info(f"[_receive_gemini_audio_task] Received text: '{response.text}' for guild {guild_id}")
                full_response_text.append(response.text)
                # Optionally send text to channel immediately or aggregate it
                # For now, aggregate and send at end of turn (or when audio starts playing if interleaved)

            # Example of how the provided Gemini Live API example handles end of turn/interaction:
            # if response.turn_complete:
            # logger.info(f"[_receive_gemini_audio_task] Turn complete signal from Gemini for guild {guild_id}")
            # This might be where you finalize sending text and prepare for next user input.

            # If using a model that signals interaction end:
            # if response.interaction_metadata and response.interaction_metadata.interaction_finished:
            #     logger.info(f"[_receive_gemini_audio_task] Gemini indicated interaction finished for guild {guild_id}")
            #     await _cleanup_live_session(guild_id, "Gemini finished interaction.")
            #     return # End this task

        # Loop finished, meaning Gemini closed the stream from its end or an error occurred.
        logger.info(f"[_receive_gemini_audio_task] Gemini stream ended for guild {guild_id}.")

    except Exception as e:
        logger.error(f"[_receive_gemini_audio_task] Error receiving from Gemini for guild {guild_id}: {e}", exc_info=debug)
        if text_channel:
            try: await text_channel.send(f"⚠️ 與AI語音助理通訊時發生錯誤: {e}")
            except discord.HTTPException: pass
    finally:
        logger.info(f"[_receive_gemini_audio_task] Finalizing for guild {guild_id}.")
        await playback_queue.put(None) # Sentinel to signal end of audio stream to player

        if full_response_text and text_channel:
            final_text = "".join(full_response_text).strip()
            if final_text:
                try:
                    user_mention = user.mention if user else "User"
                    await text_channel.send(f"🤖 **{bot_name} (Live Audio Response to {user_mention}):**\n{final_text}")
                except discord.HTTPException as e:
                    logger.error(f"Failed to send aggregated text from Live API to {text_channel.id}: {e}")
        
        # This task ending might not mean the whole session should end immediately,
        # as the user might want to speak again.
        # _cleanup_live_session should be called by /stop_live_chat or critical errors.
        if guild_id in live_sessions and live_sessions[guild_id].get("audio_output_task") is asyncio.current_task():
             # If this task is still registered, it means it wasn't cancelled by a cleanup
             # This could mean Gemini ended the conversation.
             logger.info(f"Gemini receive task ended naturally for guild {guild_id}. Session might persist for user input or bot reply.")
             # We might want to signal to user "Anything else?" or auto-stop after timeout.


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
        
        audio_source.cleanup() # Cleanup the source itself (drains queue, sets flag)

        if guild_id in live_sessions:
            live_sessions[guild_id]["is_bot_speaking_live_api"] = False
            gemini_session = live_sessions[guild_id].get("session")
            text_channel = live_sessions[guild_id].get("text_channel")
            if gemini_session:
                logger.info(f"[_play_gemini_audio][AfterCallback] Bot finished speaking. Signaling end_of_turn to Gemini for guild {guild_id}.")
                asyncio.create_task(gemini_session.send(input=".", end_of_turn=True)) # Signal bot's turn ended.
                if text_channel: # Prompt user again
                    try: asyncio.create_task(text_channel.send(f"🎤 {live_sessions[guild_id]['user_object'].mention}, 你可以繼續說話了，或使用 `/stop_live_chat` 結束。"))
                    except: pass
            else: # Session might have been cleaned up
                 logger.warning(f"[_play_gemini_audio][AfterCallback] Gemini session not found for guild {guild_id} after playback.")
        else:
            logger.warning(f"[_play_gemini_audio][AfterCallback] Live session data not found for guild {guild_id} after playback.")


    logger.info(f"[_play_gemini_audio] Starting playback for guild {guild_id}")
    if guild_id in live_sessions:
        live_sessions[guild_id]["is_bot_speaking_live_api"] = True # Bot is now speaking

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

        # Stop voice client listening if it was for this session
        vc = voice_clients.get(guild_id)
        if vc and vc.is_listening():
            # Check if the current sink is our GeminiLiveSink and for the correct user
            current_sink = getattr(vc._player, 'sink', None) if vc._player else None # Accessing sink might be internal
            if isinstance(current_sink, GeminiLiveSink) and current_sink.user_id == user_id:
                logger.info(f"Stopping listening for GeminiLiveSink in guild {guild_id}")
                vc.stop_listening()
                # Sink cleanup is usually handled by stop_listening or when player is destroyed

        if audio_output_task and not audio_output_task.done():
            logger.info(f"Cancelling Gemini audio output task for guild {guild_id}")
            audio_output_task.cancel()
            try: await audio_output_task
            except asyncio.CancelledError: logger.info(f"Audio output task cancelled for guild {guild_id}.")
            except Exception as e: logger.error(f"Error during audio output task cancellation for guild {guild_id}: {e}")

        if playback_queue:
            logger.info(f"Cleaning up playback queue for guild {guild_id}")
            await playback_queue.put(None) # Sentinel to stop player source
            while not playback_queue.empty():
                try: playback_queue.get_nowait()
                except asyncio.QueueEmpty: break
        
        if gemini_api_session:
            logger.info(f"Closing Gemini Live API session for guild {guild_id}")
            try:
                # The `client.aio.live.connect` uses an async context manager,
                # so explicit close might not be needed if exiting that context.
                # However, if we stored the session object, we might need to manage its lifecycle.
                # For `LiveConnectSession`, there isn't an explicit `close()` method documented for the session object itself.
                # Exiting the `async with` block handles cleanup.
                # If we broke out of the block due to error, it should have cleaned up.
                # If we are cleaning up "manually", we rely on tasks being cancelled.
                # The example's `AudioLoop` shows tasks being cancelled/exited to end session.
                 pass # Assuming context manager handles it or task cancellation is enough
            except Exception as e:
                logger.error(f"Error trying to close Gemini Live API session for guild {guild_id}: {e}")

        logger.info(f"Live session cleanup finished for guild {guild_id}.")
        if text_channel:
            try: await text_channel.send(f"🔴 即時語音對話已結束。 ({reason})")
            except discord.HTTPException: pass
    else:
        logger.info(f"No active live session found for guild {guild_id} to cleanup.")

# --- Discord Commands ---
@bot.tree.command(name='join', description="讓機器人加入您所在的語音頻道")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ 您需要先加入一個語音頻道才能邀請我！", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True) # Defer before potentially long op

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
            # If moving, clean up any active live session in this guild first
            if guild_id in live_sessions:
                await _cleanup_live_session(guild_id, "Bot moved to a new channel.")
            try:
                await vc.move_to(channel)
                voice_clients[guild_id] = vc # Update if needed, though move_to might update internal guild.voice_client
                await interaction.followup.send(f"✅ 已移動到語音頻道 <#{channel.id}>。", ephemeral=True)
            except Exception as e:
                logger.exception(f"Failed to move voice channel for guild {guild_id}: {e}")
                await interaction.followup.send("❌ 移動語音頻道時發生錯誤。", ephemeral=True)
                if guild_id in voice_clients: del voice_clients[guild_id] # Clear stale client
                return
    else:
        logger.info(f"Join request from {interaction.user.name} for channel '{channel.name}' (Guild: {guild_id})")
        if guild_id in voice_clients: # Clear any stale client
            del voice_clients[guild_id]
        if guild_id in live_sessions: # Clean up if for some reason a session exists without a client
            await _cleanup_live_session(guild_id, "Bot joining channel, cleaning up prior session state.")
        try:
            # Use VoiceRecvClient to enable receiving audio with custom sinks
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

    # NEW: Cleanup live session if active
    if guild_id in live_sessions:
        await _cleanup_live_session(guild_id, "Leave command issued.")

    vc = voice_clients.get(guild_id)
    if vc and vc.is_connected():
        try:
            # vc.stop_listening() is part of VoiceRecvClient, ensure it's called if listening
            if hasattr(vc, 'is_listening') and vc.is_listening():
                vc.stop_listening()
            await vc.disconnect(force=False) # force=False for graceful disconnect
            logger.info(f"Successfully disconnected from voice channel in guild {guild_id}.")
            await interaction.followup.send("👋 掰掰！我已經離開語音頻道了。", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error during voice disconnect for guild {guild_id}: {e}")
            await interaction.followup.send("❌ 離開語音頻道時發生錯誤。", ephemeral=True)
        finally:
            if guild_id in voice_clients: del voice_clients[guild_id]
            # listening_guilds might also need cleanup if used elsewhere
            if guild_id in listening_guilds: del listening_guilds[guild_id]
    else:
        logger.info(f"Leave command used but bot was not connected in guild {guild_id}.")
        await interaction.followup.send("⚠️ 我目前不在任何語音頻道中。", ephemeral=True)
        if guild_id in voice_clients: del voice_clients[guild_id] # Clean up stale entry

@bot.tree.command(name="live_chat", description=f"與 {bot_name} 開始即時語音對話 (使用 Gemini Live API)")
async def live_chat(interaction: discord.Interaction):
    if gemini_live_client_instance is None:
        await interaction.response.send_message("❌ 抱歉，AI語音對話功能目前無法使用 (Live Client 初始化失敗)。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    user = interaction.user

    if guild_id in live_sessions:
        active_user_id = live_sessions[guild_id].get("user_id")
        active_user = interaction.guild.get_member(active_user_id) if active_user_id else None
        active_user_name = active_user.display_name if active_user else f"User ID {active_user_id}"
        await interaction.response.send_message(f"⚠️ 目前已經有一個即時語音對話正在進行中 (由 {active_user_name} 發起)。請等待再試或請該用戶使用 `/stop_live_chat` 結束。", ephemeral=True)
        return

    vc = voice_clients.get(guild_id)
    if not vc or not vc.is_connected():
        await interaction.response.send_message(f"❌ 我目前不在語音頻道中。請先使用 `/join` 加入，或我會嘗試加入您所在的頻道。", ephemeral=True)
        if user.voice and user.voice.channel:
            try:
                await interaction.edit_original_response(content="⏳ 正在嘗試加入您的語音頻道...")
                vc = await user.voice.channel.connect(cls=voice_recv.VoiceRecvClient, timeout=60.0, reconnect=True)
                voice_clients[guild_id] = vc
                await interaction.edit_original_response(content=f"✅ 已加入語音頻道 <#{user.voice.channel.id}>。")
            except Exception as e:
                await interaction.edit_original_response(content=f"❌ 自動加入您的語音頻道失敗: {e}")
                return
        else:
            return

    if not isinstance(vc, voice_recv.VoiceRecvClient):
        await interaction.response.send_message("❌ 語音客戶端類型不正確，無法開始即時對話。請嘗試重新 `/join`。", ephemeral=True)
        logger.error(f"VoiceClient for guild {guild_id} is not VoiceRecvClient. Type: {type(vc)}")
        return

    if not user.voice or user.voice.channel != vc.channel:
        await interaction.response.send_message(f"❌ 您需要和我在同一個語音頻道 (<#{vc.channel.id}>) 才能使用此指令。", ephemeral=True)
        return

    await interaction.response.send_message(f"⏳ 正在啟動與 {bot_name} 的即時語音對話... 請等候。", ephemeral=True)

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

            recv_task = asyncio.create_task(_receive_gemini_audio_task(guild_id))
            live_sessions[guild_id]["audio_output_task"] = recv_task
            asyncio.create_task(_play_gemini_audio(guild_id))

            sink = GeminiLiveSink(api_session, guild_id, user.id, interaction.channel)
            vc.listen(sink)
            logger.info(f"Bot is now listening for live chat in guild {guild_id} with GeminiLiveSink.")

            await interaction.edit_original_response(content=f"✅ {bot_name} 正在聽你說話！請開始說話。使用 `/stop_live_chat` 結束。")

    except Exception as e:
        logger.exception(f"Error starting live_chat for guild {guild_id}: {e}")
        await interaction.edit_original_response(content=f"❌ 啟動即時語音對話失敗: {e}")
        await _cleanup_live_session(guild_id, f"Failed to start: {e}")

@bot.tree.command(name="stop_live_chat", description="結束目前的即時語音對話")
async def stop_live_chat(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    await interaction.response.defer(ephemeral=True)

    if guild_id not in live_sessions:
        await interaction.followup.send("⚠️ 目前沒有進行中的即時語音對話。", ephemeral=True)
        return

    # Optional: Check if the user issuing stop is the one who started, or if admin
    # session_user_id = live_sessions[guild_id].get("user_id")
    # if interaction.user.id != session_user_id and not interaction.user.guild_permissions.manage_channels:
    #     await interaction.followup.send("❌ 您沒有權限結束這個對話。", ephemeral=True)
    #     return

    logger.info(f"User {interaction.user.id} requested to stop live chat in guild {guild_id}.")
    await _cleanup_live_session(guild_id, f"Stopped by user {interaction.user.id}")
    await interaction.followup.send("✅ 即時語音對話已結束。", ephemeral=True)


# @bot.tree.command(name='stop_listening', description="讓機器人停止監聽語音 (但保持在頻道中)")
# async def stop_listening(interaction: discord.Interaction):
    # This command's original intent might conflict with live_chat's listening state.
    # If a live_chat is active, this should probably signal to stop THAT listening,
    # which effectively means ending the live_chat.
    # For now, I'll comment it out to avoid confusion. If needed, it should integrate with _cleanup_live_session.
    # pass

# @bot.tree.command(name="ask_voice", description=f"準備讓 {bot_name} 聆聽您接下來的語音提問 (Whisper STT)")
# async def ask_voice(interaction: discord.Interaction):
    # This is your original Whisper-based STT command.
    # It can co-exist if you want both Whisper STT -> Text AI -> EdgeTTS, AND the new Live API flow.
    # Or, you could modify this to also use the Live API but for a single turn (more complex).
    # For now, this is commented out to focus on the Live API.
    # global expecting_voice_query_from
    # ... (your original ask_voice logic using Whisper)
    # pass

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    guild_id = guild.id

    # Bot's own state changes
    if member.id == bot.user.id:
        if before.channel and not after.channel: # Bot was disconnected or left
            logger.warning(f"Bot was disconnected from voice channel '{before.channel.name}' in guild {guild_id}.")
            await _cleanup_live_session(guild_id, "Bot disconnected from voice channel.")
            if guild_id in voice_clients: del voice_clients[guild_id]
            if guild_id in listening_guilds: del listening_guilds[guild_id] # General listening flag
        # Other bot state changes (moved, etc.) are generally handled by commands or internal VC logic.
        return

    # User state changes
    if guild_id in live_sessions:
        session_data = live_sessions[guild_id]
        session_user_id = session_data.get("user_id")
        vc = voice_clients.get(guild_id)

        if member.id == session_user_id: # The user in the live session changed state
            if vc and vc.channel:
                if after.channel != vc.channel: # User left the bot's channel or disconnected
                    logger.info(f"User {member.id} (in live session) left bot's channel in guild {guild_id}. Cleaning up.")
                    await _cleanup_live_session(guild_id, "User left voice channel during session.")
            elif not after.channel: # User disconnected from voice entirely
                logger.info(f"User {member.id} (in live session) disconnected from voice in guild {guild_id}. Cleaning up.")
                await _cleanup_live_session(guild_id, "User disconnected during session.")
    
    # Auto-leave if bot is alone (original logic, adapted)
    if before.channel and before.channel != after.channel: # User left a channel the bot might be in
        # Check if bot is in before.channel and is now alone
        vc = voice_clients.get(guild_id)
        if vc and vc.is_connected() and vc.channel == before.channel:
            # Give a brief moment for state to fully update
            await asyncio.sleep(2.0) 
            # Re-check current state, as bot might have been commanded to leave, or session ended
            current_vc = voice_clients.get(guild_id) # Get current VC state again
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
    # This is your extensive on_message handler for text-based Gemini interactions.
    # It should largely remain functional. Ensure `model` is `text_model`.
    if message.author == bot.user or not message.guild or message.author.bot: return
    # ... (rest of your WHITELISTED_SERVERS check, DB updates)

    # Example of adapting to `text_model`:
    # if should_respond:
    #     if text_model is None: # Check the text model
    #          logger.warning(f"Ignoring mention/command in guild {guild_id} because Gemini TEXT model is not available.")
    #          return
    #     # ... (Points deduction logic)
    #     async with channel.typing():
    #         try:
    #             # ... (your prompt and history setup)
    #             chat = text_model.start_chat(history=chat_history_processed) # Use text_model
    #             response = await chat.send_message_async(...)
    #             # ... (rest of your response handling)
    #         except Exception as e:
    #             # ... (error handling)
    pass # Placeholder for your on_message logic


def bot_run():
    if not discord_bot_token:
        logger.critical("設定檔中未設定 Discord Bot Token！機器人無法啟動。")
        return
    if not API_KEY:
        logger.warning("設定檔中未設定 Gemini API Key！AI 功能可能部分受限。")

    # Original Whisper/VAD model loading (can be kept if other commands use them)
    # global whisper_model, vad_model
    # try:
    #     logger.info("正在載入 VAD 模型 (Silero VAD)...")
    #     vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', trust_repo=True)
    #     logger.info("Silero VAD 模型載入完成。")

    #     whisper_model_size = "medium"
    #     logger.info(f"正在載入 Whisper 模型 ({whisper_model_size})...")
    #     whisper_download_root = os.path.join(os.getcwd(), "whisper_models")
    #     os.makedirs(whisper_download_root, exist_ok=True)
    #     whisper_model = whisper.load_model(whisper_model_size, download_root=whisper_download_root)
    #     device_str = "CUDA" if torch.cuda.is_available() else "CPU"
    #     logger.info(f"Whisper 模型 ({whisper_model_size}) 載入完成。 Device: {device_str}")
    # except Exception as model_load_error:
    #     logger.critical(f"載入 VAD 或 Whisper 模型失敗: {model_load_error}", exc_info=True)
    #     logger.warning("舊版 STT/VAD 功能可能無法使用。")
    #     vad_model = None
    #     whisper_model = None
    
    # Ensure Opus is loaded for discord.py voice
    if not opus.is_loaded():
        try:
            # Try loading system-installed opus first
            # On Windows, you might need to specify the path to libopus-0.dll
            # e.g., opus.load_opus('C:/path/to/libopus-0.dll')
            # On Linux, usually 'libopus.so.0' or similar works if installed via package manager
            # On macOS, 'libopus.dylib'
            
            # Common names to try:
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
        # Cleanup any remaining live sessions (though bot.close() should trigger disconnections)
        # This loop might not run if bot.run() exits non-gracefully
        # for guild_id in list(live_sessions.keys()): # list() to avoid issues with dict size change
        #     asyncio.run_coroutine_threadsafe(_cleanup_live_session(guild_id, "Bot shutting down"), bot.loop)


if __name__ == "__main__":
    # init_db() # If you have a global init_db function from nana_bot
    logger.info("從主執行緒啟動機器人...")
    bot_run()
    logger.info("機器人執行完畢。")

__all__ = ['bot_run', 'bot'] # If this were a module