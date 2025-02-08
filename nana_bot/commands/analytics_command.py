import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from datetime import datetime, timedelta, timezone
import sqlite3
from nana_bot import bot
import logging
import os
@bot.tree.command(name="analytics", description="顯示用戶或頻道分析數據")
@app_commands.describe(
    channel="選擇一個頻道以分析其數據",
    member="選擇一個成員以分析其數據",
    analysis_type="選擇要查看的數據分析類型"
)
@app_commands.choices(analysis_type=[
    app_commands.Choice(name="本日數據", value="daily"),
    app_commands.Choice(name="本週數據", value="weekly"),
    app_commands.Choice(name="本月數據", value="monthly"),
    app_commands.Choice(name="人口增加數據", value="population"),
    app_commands.Choice(name="審核數據", value="reviews"),
    app_commands.Choice(name="說話次數分析", value="message_ranking"),
    app_commands.Choice(name="Token及費用", value="token"),
])
async def analytics(interaction: discord.Interaction, analysis_type: str, channel: discord.TextChannel = None, member: discord.Member = None):
    db_name = 'analytics_server_' + str(interaction.guild.id) + '.db'
    # 直接 defer
    await interaction.response.defer()
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../databases", db_name)
    logging.info(f"Database path: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()


    def get_database_connection():
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../databases", db_name)
        logging.info(f"Database path: {db_path}")
        return sqlite3.connect(db_path)

    # 確保所有表格都存在
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        user_name TEXT,
        join_date TEXT,
        message_count INTEGER DEFAULT 0
    )
    ''')

    cursor.execute('''
          CREATE TABLE IF NOT EXISTS messages (
              message_id INTEGER PRIMARY KEY,
              user_id TEXT,
              user_name TEXT,
              channel_id TEXT,
              timestamp TEXT,
              content TEXT
          )
          ''')

    cursor.execute('''
          CREATE TABLE IF NOT EXISTS daily_activity (
              date TEXT,
              channel_id TEXT,
              message_count INTEGER
          )
          ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userid TEXT UNIQUE,
            total_token_count INTEGER,
            channelid TEXT
        )
        ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY,
            user_id TEXT,
            review_date TEXT
        )
        ''')
    conn.commit()


    # --- 輔助函數 ---
    def get_daily_active_users():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(DISTINCT user_id) 
            FROM users 
            WHERE DATE(join_date) = DATE('now')
            ''')
            return cursor.fetchone()[0]

    def get_weekly_active_users():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(DISTINCT user_id) 
            FROM users 
            WHERE DATE(join_date) >= DATE('now', '-7 days')
            ''')
            return cursor.fetchone()[0]

    def get_monthly_active_users():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(DISTINCT user_id)
            FROM users
            WHERE DATE(join_date) >= DATE('now', '-30 days')
            ''')
            return cursor.fetchone()[0]

    def get_daily_reviews():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(*) 
            FROM reviews 
            WHERE DATE(review_date) = DATE('now')
            ''')
            return cursor.fetchone()[0]

    def get_weekly_reviews():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(*) 
            FROM reviews 
            WHERE DATE(review_date) >= DATE('now', '-7 days')
            ''')
            return cursor.fetchone()[0]

    def get_monthly_reviews():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(*)
            FROM reviews
            WHERE DATE(review_date) >= DATE('now', '-30 days')
            ''')
            return cursor.fetchone()[0]

    def get_daily_channel_message_count():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT channel_id, COUNT(*) 
            FROM messages 
            WHERE DATE(timestamp) = DATE('now') 
            GROUP BY channel_id 
            ORDER BY COUNT(*) DESC
            ''')
            return cursor.fetchall()

    def get_weekly_channel_message_count():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT channel_id, COUNT(*) 
            FROM messages 
            WHERE DATE(timestamp) >= DATE('now', '-7 days') 
            GROUP BY channel_id 
            ORDER BY COUNT(*) DESC
            ''')
            return cursor.fetchall()
    
    def get_monthly_channel_message_count():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT channel_id, COUNT(*)
            FROM messages
            WHERE DATE(timestamp) >= DATE('now', '-30 days')
            GROUP BY channel_id
            ORDER BY COUNT(*) DESC
            ''')
            return cursor.fetchall()

    def get_daily_message_ranking():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT user_id, user_name, COUNT(*) as message_count 
            FROM messages 
            WHERE DATE(timestamp) = DATE('now') 
            GROUP BY user_id, user_name
            ORDER BY message_count DESC
            ''')
            return cursor.fetchall()

    def get_weekly_message_ranking():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT user_id, user_name, COUNT(*) as message_count 
            FROM messages 
            WHERE DATE(timestamp) >= DATE('now', '-7 days') 
            GROUP BY user_id, user_name
            ORDER BY message_count DESC
            ''')
            return cursor.fetchall()
    
    def get_monthly_message_ranking():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT user_id, user_name, COUNT(*) as message_count
            FROM messages
            WHERE DATE(timestamp) >= DATE('now', '-30 days')
            GROUP BY user_id, user_name
            ORDER BY message_count DESC
            ''')
            return cursor.fetchall()

    def get_server_token_count():
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT SUM(total_token_count)
            FROM metadata
            ''')
            result = cursor.fetchone()
            return result[0] if result[0] else 0

    def get_channel_daily_message_count(channel_id):
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT COUNT(*) 
            FROM messages 
            WHERE DATE(timestamp) = DATE('now') AND channel_id = ?
            ''', (str(channel_id),))
            return cursor.fetchone()[0]

    def get_channel_weekly_message_count(channel_id):
         with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
             SELECT COUNT(*)
             FROM messages
             WHERE DATE(timestamp) >= DATE('now', '-7 days') AND channel_id = ?
             ''', (str(channel_id),))
            return cursor.fetchone()[0]

    def get_channel_monthly_message_count(channel_id):
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
             SELECT COUNT(*)
             FROM messages
             WHERE DATE(timestamp) >= DATE('now', '-30 days') AND channel_id = ?
            ''', (str(channel_id),))
            return cursor.fetchone()[0]

    def get_channel_token_count(channel_id):
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT SUM(total_token_count)
                FROM metadata
                WHERE channelid = ?
            ''', (str(channel_id),))
            result = cursor.fetchone()
            return result[0] if result[0] else 0

    def get_user_token_count(userid):
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../databases", db_name)
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT total_token_count FROM metadata WHERE userid = ?
            ''', (userid,))
            result = c.fetchone()
            if result:
                return result[0]
            else:
                return None
    # --- 數據分析邏輯 ---

    if channel:  # 頻道數據
        if analysis_type == "daily":
            daily_message_count = get_channel_daily_message_count(channel.id)
            message_content = f"頻道 <#{channel.id}> 的數據分析:\n今日訊息數量: {daily_message_count}"
        elif analysis_type == "weekly":
            weekly_message_count = get_channel_weekly_message_count(channel.id)
            message_content = f"頻道 <#{channel.id}> 的數據分析:\n本週訊息數量: {weekly_message_count}"
        elif analysis_type == "monthly":
            monthly_message_count = get_channel_monthly_message_count(channel.id)
            message_content = f"頻道 <#{channel.id}> 的數據分析:\n本月訊息數量: {monthly_message_count}"
        elif analysis_type == "token":
            token_count = get_channel_token_count(channel.id)
            message_content = f"頻道 <#{channel.id}> 的數據分析:\n累計Token: {token_count}\n預估累計費用:  {round((token_count / 100000) + (token_count / 1000000 * 0.625), 3)}美元"
        else:
            message_content = "請選擇有效的分析類型（例如：`daily`, `weekly`, `monthly`, `token`）。"

        embed = discord.Embed(title="頻道分析", description=message_content)
        await interaction.edit_original_response(embed=embed)


    elif member:  # 用戶數據
        c_command = conn.cursor()
        c_command.execute('SELECT message_count, join_date FROM users WHERE user_id = ?', (str(member.id),))
        result = c_command.fetchone()

        if not result:
            await interaction.edit_original_response(content=f'沒有找到 {member.name} 的數據。')
            return

        message_count, join_date = result
        join_date = datetime.fromisoformat(join_date)
        days_since_join = (datetime.utcnow() - join_date).days
        avg_messages_per_day = message_count / days_since_join if days_since_join > 0 else message_count
        token = get_user_token_count(member.id)

        if analysis_type == 'message_ranking':
            embed = discord.Embed(title="用戶分析", description=f'用戶: {member.name}\n說話次數: {message_count}\n平均每日說話次數: {avg_messages_per_day:.2f}')

        elif analysis_type == "token":
             embed = discord.Embed(title="用戶分析",
                              description=f'用戶: {member.name}\n'f'累計token: {token}\n'f'預估累計費用:  {round((token / 100000) + (token / 1000000 * 0.625), 3)}美元')
        else:
            embed = discord.Embed(title="用戶分析",
                              description=f'用戶: {member.name}\n'f'加入時間: {join_date.strftime("%Y-%m-%d %H:%M:%S")}\n'f'說話次數: {message_count}\n'f'平均每日說話次數: {avg_messages_per_day:.2f}\n'f'累計token: {token}\n'f'預估累計費用:  {round((token / 100000) + (token / 1000000 * 0.625), 3)}美元')

        await interaction.edit_original_response(embed=embed)
        c_command.close()

    else:  # 伺服器數據
        message_content = "伺服器總體數據分析:\n"

        if analysis_type == "daily":
            active_users = get_daily_active_users()
            daily_reviews = get_daily_reviews()
            channel_message_counts = get_daily_channel_message_count()
            message_ranking = get_daily_message_ranking()

            message_content += f"今日新增人口數: {active_users}\n"
            message_content += f"今日審核人數: {daily_reviews}\n"
            message_content += "每日頻道說話次數:\n"
            for channel_id, message_count in channel_message_counts:
                message_content += f"頻道 <#{channel_id}>: {message_count} 次\n"
            message_content += "每日說話次數排名:\n"
            for user_id, user_name, message_count in message_ranking:
                message_content += f"用戶 <@{user_id}> {user_name}: {message_count} 次\n"


        elif analysis_type == "weekly":
            weekly_active_users = get_weekly_active_users()
            weekly_reviews = get_weekly_reviews()
            weekly_channel_message_counts = get_weekly_channel_message_count()
            weekly_message_ranking = get_weekly_message_ranking()

            message_content += f"本週新增人口數: {weekly_active_users}\n"
            message_content += f"本週審核人數: {weekly_reviews}\n"
            message_content += "每週頻道說話次數:\n"
            for channel_id, message_count in weekly_channel_message_counts:
                message_content += f"頻道 <#{channel_id}>: {message_count} 次\n"
            message_content += "每週說話次數排名:\n"
            for user_id, user_name, message_count in weekly_message_ranking:
                message_content += f"用戶 <@{user_id}> {user_name}: {message_count} 次\n"
        elif analysis_type == 'monthly': #處理月數據
            monthly_active_users = get_monthly_active_users()
            monthly_reviews = get_monthly_reviews()
            monthly_channel_message_counts = get_monthly_channel_message_count()
            monthly_message_ranking = get_monthly_message_ranking()

            message_content += f"本月新增人口數: {monthly_active_users}\n"
            message_content += f"本月審核人數: {monthly_reviews}\n"
            message_content += "每月頻道說話次數:\n"
            for channel_id, message_count in monthly_channel_message_counts:
                message_content += f"頻道 <#{channel_id}>: {message_count} 次\n"
            message_content += "每月說話次數排名:\n"
            for user_id, user_name, message_count in monthly_message_ranking:
                message_content += f"用戶 <@{user_id}> {user_name}: {message_count} 次\n"

        elif analysis_type == "population":
            daily_active_users = get_daily_active_users()
            weekly_active_users = get_weekly_active_users()
            monthly_active_users = get_monthly_active_users()
            message_content += f"今日新增人口數: {daily_active_users}\n"
            message_content += f"本週新增人口數: {weekly_active_users}\n"
            message_content += f"本月新增人口數: {monthly_active_users}\n"

        elif analysis_type == "reviews":
            daily_reviews = get_daily_reviews()
            weekly_reviews = get_weekly_reviews()
            monthly_reviews = get_monthly_reviews()
            message_content += f"今日審核人數: {daily_reviews}\n"
            message_content += f"本週審核人數: {weekly_reviews}\n"
            message_content += f"本月審核人數: {monthly_reviews}\n"


        elif analysis_type == "message_ranking":
            daily_message_ranking = get_daily_message_ranking()
            weekly_message_ranking = get_weekly_message_ranking()
            monthly_message_ranking = get_monthly_message_ranking()

            message_content += "每日說話次數排名:\n"
            for user_id, user_name, message_count in daily_message_ranking:
                message_content += f"用戶 <@{user_id}> {user_name}: {message_count} 次\n"

            message_content += "\n每週說話次數排名:\n"
            for user_id, user_name, message_count in weekly_message_ranking:
                message_content += f"用戶 <@{user_id}> {user_name}: {message_count} 次\n"

            message_content += "\n每月說話次數排名:\n"
            for user_id, user_name, message_count in monthly_message_ranking:
                message_content += f"用戶 <@{user_id}> {user_name}: {message_count} 次\n"
        elif analysis_type == "token":
            token_count = get_server_token_count()
            message_content += f"累計Token: {token_count}\n"
            message_content += f"預估累計費用:  {round((token_count / 100000) + (token_count / 1000000 * 0.625), 3)}美元"
        else:
            message_content = "請選擇有效的分析類型。"

        embed = discord.Embed(title="伺服器分析", description=message_content)
        descriptions = [embed.description[i:i + 4096] for i in range(0, len(embed.description), 4096)]

        # 只需發送一次，Discord 會自動處理多個 embed
        if descriptions:
             await interaction.edit_original_response(embed=discord.Embed(description=descriptions[0]))
             #如果有多個embed, 用followup發送剩下的
             for desc in descriptions[1:]:
                new_embed = discord.Embed(description=desc)
                await interaction.followup.send(embed=new_embed)

    conn.close()