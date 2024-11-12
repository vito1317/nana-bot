import discord
from discord.ext import commands, tasks
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
import google.generativeai as genai
import os

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

API_KEY = None
gemini_model = None
bot_name = None 
debug = False
review_format = None
reviewed_role_id = None
reviewed_prompt_channel_id = None
servers = None
pass_user_prompt_text = None
send_daily_channel_id_list = None
newcomer_channel_id = None
member_remove_channel_id = None
not_reviewed_id = None
welcome_channel_id = None
ALLOWED_ROLE_IDS = None
WHITELISTED_SERVERS = None
TARGET_CHANNEL_ID = None
discord_bot_token = None

class Config:
    def __init__(
        self,
        api_key,
        gemini_model,
        bot_name,
        debug,
        review_format,
        reviewed_role_id,
        reviewed_prompt_channel_id,
        servers,
        pass_user_prompt_text,
        send_daily_channel_id_list,
        newcomer_channel_id,
        member_remove_channel_id,
        not_reviewed_id,
        welcome_channel_id,
        allowed_role_ids,
        whitelisted_servers,
        target_channel_id,
        discord_bot_token,
    ):
        self.api_key = api_key
        self.gemini_model = gemini_model
        self.bot_name = bot_name
        self.debug = debug
        self.review_format = review_format
        self.reviewed_role_id = reviewed_role_id
        self.reviewed_prompt_channel_id = reviewed_prompt_channel_id
        self.servers = servers
        self.pass_user_prompt_text = pass_user_prompt_text
        self.send_daily_channel_id_list = send_daily_channel_id_list
        self.newcomer_channel_id = newcomer_channel_id
        self.member_remove_channel_id = member_remove_channel_id
        self.not_reviewed_id = not_reviewed_id
        self.welcome_channel_id = welcome_channel_id
        self.allowed_role_ids = allowed_role_ids
        self.whitelisted_servers = whitelisted_servers
        self.target_channel_id = target_channel_id
        self.discord_bot_token = discord_bot_token

    def display(self):
        return {
            "API_KEY": self.api_key,
            "gemini_model": self.gemini_model,
            "bot_name": self.bot_name,
            "debug": self.debug,
            "review_format": self.review_format,
            "reviewed_role_id": self.reviewed_role_id,
            "reviewed_prompt_channel_id": self.reviewed_prompt_channel_id,
            "servers": self.servers,
            "pass_user_prompt_text": self.pass_user_prompt_text,
            "send_daily_channel_id_list": self.send_daily_channel_id_list,
            "newcomer_channel_id": self.newcomer_channel_id,
            "member_remove_channel_id": self.member_remove_channel_id,
            "not_reviewed_id": self.not_reviewed_id,
            "welcome_channel_id": self.welcome_channel_id,
            "ALLOWED_ROLE_IDS": self.allowed_role_ids,
            "WHITELISTED_SERVERS": self.whitelisted_servers,
            "TARGET_CHANNEL_ID": self.target_channel_id,
            "discord_bot_token": self.discord_bot_token,
        }

def initialize_bot(config):
    global API_KEY, gemini_model, servers, send_daily_channel_id_list
    global newcomer_channel_id, member_remove_channel_id, not_reviewed_id, pass_user_prompt_text
    global welcome_channel_id, ALLOWED_ROLE_IDS, WHITELISTED_SERVERS, reviewed_prompt_channel_id
    global TARGET_CHANNEL_ID, discord_bot_token, bot_name, debug, review_format, reviewed_role_id

    API_KEY = config.api_key
    gemini_model = config.gemini_model
    bot_name = config.bot_name
    debug = config.debug
    review_format = config.review_format
    reviewed_role_id = config.reviewed_role_id
    reviewed_prompt_channel_id = config.reviewed_prompt_channel_id
    servers = config.servers
    pass_user_prompt_text = config.pass_user_prompt_text
    send_daily_channel_id_list = config.send_daily_channel_id_list
    newcomer_channel_id = config.newcomer_channel_id
    member_remove_channel_id = config.member_remove_channel_id
    not_reviewed_id = config.not_reviewed_id
    welcome_channel_id = config.welcome_channel_id
    ALLOWED_ROLE_IDS = config.allowed_role_ids
    WHITELISTED_SERVERS = config.whitelisted_servers
    TARGET_CHANNEL_ID = config.target_channel_id
    discord_bot_token = config.discord_bot_token
    
    genai.configure(api_key=API_KEY)



def init_db(db_name, tables):
    db_path = "./databases/" + db_name
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for table_name, table_schema in tables.items():
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({table_schema})")
        conn.commit()

def get_current_time_utc8():
    timestamp = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    print(timestamp)
    return timestamp

def init_db_points(guild_id):
    db_name = "points_" + str(guild_id) + ".db"
    db_path = "./databases/" + db_name
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        user_name TEXT,
        join_date TEXT,
        points INTEGER DEFAULT 0
    )
    """
    )
    cursor.execute(
        """
       CREATE TABLE IF NOT EXISTS transactions (
           transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
           user_id TEXT,
           points INTEGER,
           reason TEXT,
           timestamp TEXT
       )
       """
    )
    conn.commit()
    conn.close()
    
def run_bot():
    from .bot import bot_run  
    bot_run()  

__all__ = [
    'bot', 'initialize_bot', 'init_db', 'get_current_time_utc8', 'init_db_points', 'Config', 'run_bot'
]
