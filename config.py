import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)
API_KEY = "Your Gemini API Key"
gemini_model = "gemini-1.5-pro-002"
servers = ["servers_id"]
send_daily_channel_id_list = ["send_daily_channel_id"]
newcomer_channel_id = ["newcomer_channel_id"]
member_remove_channel_id = ["member_remove_channel_id"]
not_reviewed_id = ["not_reviewed_id"]
welcome_channel_id = ["welcome_channel_id"]
ALLOWED_ROLE_IDS = {"ALLOWED_ROLE_IDS"}
WHITELISTED_SERVERS = {
    "Your Server ID": 'Server 1',
}
TARGET_CHANNEL_ID = ["TARGET_CHANNEL_ID"]
discord_bot_token = "Your discord bot token"
engines = [
    app_commands.Choice(name='Google', value='google'),
    app_commands.Choice(name='yahoo', value='yahoo')
]
def get_current_time_utc8():
    timestamp = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    print(timestamp)
    return timestamp
def init_db(db_name, tables):
    with sqlite3.connect("./databases/"+db_name) as conn:
        cursor = conn.cursor()
        for table_name, table_schema in tables.items():
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({table_schema})")
        conn.commit()
def init_db_points(guild_id):
    db_name = 'points_' + str(guild_id) + '.db'
    conn = sqlite3.connect("./databases/"+db_name)
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
           transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
           user_id TEXT,
           points INTEGER,
           reason TEXT,
           timestamp TEXT
       )
       ''')
    conn.commit()
    conn.close()
