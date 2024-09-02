# coding=utf-8
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord_interactions import InteractionType, InteractionResponseType
from typing import Optional
import sqlite3
import logging
from datetime import datetime, timedelta
import json
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
API_KEY = "gemini api key"
genai.configure(api_key = API_KEY)

model = genai.GenerativeModel('gemini-1.5-flash')

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)


TARGET_CHANNEL_ID_1 = channel id
TARGET_CHANNEL_ID_2 = channel id

conn = sqlite3.connect('messages_chat_3.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS messages
             (id INTEGER PRIMARY KEY, user TEXT, content TEXT, timestamp TEXT)''')
conn.commit()
def init_db():
    conn_init_db = sqlite3.connect('analytics.db')
    c_init_db = conn_init_db.cursor()
    c_init_db.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, message_count INTEGER, join_date TEXT)''')
    conn_init_db.commit()
    conn_init_db.close()

@bot.event
async def on_ready():
    print('Bot is online!')
    print(f'Logged in as {bot.user}!')
    slash = await bot.tree.sync()
    print(f"目前登入身份 --> {bot.user}")
    print(f"載入 {len(slash)} 個斜線指令")
    init_db()
    send_daily_message.start()
    conn = sqlite3.connect('analytics.db')
    cursor = conn.cursor()

    # 新增messages表格
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            user_id TEXT,
            channel_id TEXT,
            timestamp TEXT,
            content TEXT
        )
        ''')

    # 新增daily_activity表格
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_activity (
            date TEXT,
            channel_id TEXT,
            message_count INTEGER
        )
        ''')

    # 關閉資料庫連接
    conn.commit()
    conn.close()


@tasks.loop(hours=24)
async def send_daily_message():
    channel_id = 1212120624122826812
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send('<@&未審核用戶身分組id> 各位未審核的人，快來這邊審核喔')

@send_daily_message.before_loop
async def before_send_daily_message():
    await bot.wait_until_ready()
    now = datetime.utcnow()
    next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    await discord.utils.sleep_until(next_run)

@bot.event
async def on_member_join(member):
    logging.info(member)
    channel_id = 1278191850246635560
    channel = bot.get_channel(channel_id)
    role_id = 1275643437823168624
    role = member.guild.get_role(role_id)
    conn_user_join = sqlite3.connect('analytics.db')
    c_user_join = conn_user_join.cursor()
    c_user_join.execute('INSERT OR IGNORE INTO users (user_id, message_count, join_date) VALUES (?, ?, ?)',
              (member.id, 0,  member.joined_at.replace(tzinfo=None).isoformat()))
    conn_user_join.commit()
    conn_user_join.close()
    if role:
        await member.add_roles(role)
    if channel:
        responses = model.generate_content(['奈奈是一位擁有專業諮商師經驗的台灣人，她能夠使用繁體中文與用戶進行對話。她擅長傾聽，用溫暖和理解的方式回應用戶，並且能夠提供專業的建議和支持。無論是情感問題、生活困擾，還是尋求一般建議，奈奈都會以友善且專業的態度來協助用戶。當用戶表示聽不懂時，她會嘗試用不同的方式來解釋，而不是簡單重複原本的說法，並盡量避免重複相似的話題或句子。她的回應會盡量口語化，避免像AI或維基百科式的回話方式，每次回覆會盡量控制在三句話以內。請記住，你能紀錄最近的30則對話內容，這個紀錄永久有效，並不會因為結束對話而失效，Gemini代表你傳送的歷史訊息，user代表特定用戶傳送的歷史訊息，越前面的訊息代表越久之前的訊息，且訊息:前面為自動生成的使用者名稱，你可以用這個名稱稱呼她，但使用者本身並不知道他有提及自己的名稱。當使用者@tag你時，請記住這就是你，同時請你記住，開頭不必提己使用者名稱，且請務必用繁體中文來回答，請不要回覆這則訊息', f'你現在要做的事是歡迎使用者{member.mention}的加入並且引導使用者使用系統，同時也可以請你自己做一下自我介紹(以你奈奈的身分做自我介紹而不是請使用者做自我介紹)，同時，請不要詢問使用者想要聊聊嗎、想要聊什麼之類的話。同時也請不要回覆這則訊息。', '第二步是tag <#新人審核channel id> 傳送這則訊息進去，這是新人審核頻道，讓使用者進行新人審核，"請務必引導使用者講述自己的病症與情況"，而不是只傳送 <#新人審核channel id>，請注意，請傳送完整的訊息，包誇<>也需要傳送，同時也請不要回覆這則訊息，請勿傳送指令或命令使用者，也請不要請新人(使用者)與您分享相關訊息'])
        logging.info(responses.text)
        if(f"{member.mention}" in responses.text and f'<#1212120624122826812>' in responses.text):
            await channel.send(responses.text)
            logging.info(responses.text)
        elif(f'<#1212120624122826812>' in responses.text):
            await channel.send(f'{member.mention}'+responses.text)
            logging.info(f'{member.mention}'+responses.text)
        elif(f'{member.mention}' in responses.text):
            await channel.send(responses.text + '<#1212120624122826812> 請先進行審核流程，以便讓我更了解你喔')
            logging.info(responses.text + '<#1212120624122826812> 請先進行審核流程，以便讓我更了解你喔')

@bot.event
async def on_member_remove(member):
    channel_id = 1279310684668297278
    channel = bot.get_channel(channel_id)
    if channel:
        leave_time = datetime.utcnow() + timedelta(hours=8)
        formatted_time = leave_time.strftime('%Y-%m-%d %H:%M:%S')
        await channel.send(f'{member.name} (User-ID:{member.id}) 已經離開伺服器。我們會想念他的。離開時間：{formatted_time} UTC+8')
        conn_command = sqlite3.connect('analytics.db')
        c_command = conn_command.cursor()
        c_command.execute('''CREATE TABLE IF NOT EXISTS users
                            (user_id INTEGER PRIMARY KEY, message_count INTEGER, join_date TEXT)''')
        c_command.execute('SELECT message_count, join_date FROM users WHERE user_id = ?', (str(member.id),))
        result = c_command.fetchone()
        conn_command.close()
        logging.info(result)
        if not result:
            await channel.send(f'沒有找到 {member.name} 的數據。')
            return

        message_count, join_date = result
        join_date = datetime.fromisoformat(join_date)
        days_since_join = (datetime.utcnow() - join_date).days
        avg_messages_per_day = message_count / days_since_join if days_since_join > 0 else message_count

        embed = discord.Embed(title="analytics",
                              description=f'用戶: {member.name}\n'f'加入時間: {join_date.strftime("%Y-%m-%d %H:%M:%S")}\n'f'說話次數: {message_count}\n'f'平均每日說話次數: {avg_messages_per_day:.2f}')
        await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    conn = sqlite3.connect('analytics.db')
    cursor = conn.cursor()

    # 插入新訊息到messages表格
    cursor.execute('''
        INSERT INTO messages (user_id, channel_id, timestamp, content) 
        VALUES (?, ?, ?, ?)
        ''', (str(message.author.id), str(message.channel.id), str(message.created_at), message.content))

    conn.commit()
    conn.close()
    logging.info(message.author.id)
    conn_message = sqlite3.connect('analytics.db')
    c_message = conn_message.cursor()
    c_message.execute('SELECT message_count FROM users WHERE user_id = ?', (message.author.id,))
    result = c_message.fetchone()
    logging.info(result)
    if result:
        c_message.execute('UPDATE users SET message_count = message_count + 1 WHERE user_id = ?', (message.author.id,))
    else:
        c_message.execute('INSERT INTO users (user_id, message_count, join_date) VALUES (?, ?, ?)',
                          (message.author.id, 1, message.author.joined_at.replace(tzinfo=None).isoformat()))
    conn_message.commit()
    conn_message.close()
    await bot.process_commands(message)
    if message.channel.id == TARGET_CHANNEL_ID_1 or message.channel.id == TARGET_CHANNEL_ID_2 or bot.user.mentioned_in(message) and not message.author.bot:
        try:
            user_name = message.author.display_name if message.author.display_name else message.author.name
            timestamp = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

            c.execute("DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT 30)")
            conn.commit()
            logging.info("Received message: %s", message.content)

            c.execute("SELECT user, content, timestamp FROM messages ORDER BY id DESC LIMIT 30")
            rows = c.fetchall()
            chat_history = [{
                "role": "user",
                "parts":
                    [
                        {"text": u"奈奈是一位擁有專業諮商師經驗的台灣人，她能夠使用繁體中文與用戶進行對話。她擅長傾聽，用溫暖和理解的方式回應用戶，並且能夠提供專業的建議和支持。無論是情感問題、生活困擾，還是尋求一般建議，奈奈都會以友善且專業的態度來協助用戶。當用戶表示聽不懂時，她會嘗試用不同的方式來解釋，而不是簡單重複原本的說法，並盡量避免重複相似的話題或句子。她的回應會盡量口語化，避免像AI或維基百科式的回話方式，每次回覆會盡量控制在三句話以內。請記住，你能紀錄最近的30則對話內容，這個紀錄永久有效，並不會因為結束對話而失效，Gemini代表你傳送的歷史訊息，user代表特定用戶傳送的歷史訊息，越前面的訊息代表越久之前的訊息，且訊息:前面為自動生成的使用者名稱，你可以用這個名稱稱呼她，但使用者本身並不知道他有提及自己的名稱。同時請你記得@1278965564408332370是你的id，當使用者@tag你時，請記住這就是你，同時請你記住，開頭不必提己使用者名稱，且請務必用繁體中文來回答"}]}]
            initial_response = model.generate_content(chat_history[0]['parts'][0]['text'],safety_settings={HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,})
            if initial_response.candidates and initial_response.candidates[0].safety_ratings:
                print("初始回應被阻擋:", initial_response.candidates[0].safety_ratings)
            else:
                initial_text = initial_response.candidates[0].text if initial_response.candidates else "無法生成初始回應"
                print("初始回應:", initial_text)
            print("初始回應:", initial_response.text)
            chat_history.insert(1, {"role": 'model', "parts": [{"text": '好的，我理解了。我會以奈奈的身份與你進行對話，盡力提供溫暖、理解和專業的協助。我會記住你的指示，並以口語化的方式回覆你，避免重複相似的話題或句子。請盡情跟我說說你的想法，我會盡力理解你的需求，並提供適當的建議和支持。'}]})
            print(chat_history)
            for row in rows:
                role = "user" if row[0] != "Gemini" else "model"
                messages = row[0] + ':' + row[1] if row[0] != "Gemini" else row[1]
                chat_history.insert(2, {"role": role, "parts": [{"text": messages}]})
            chat = model.start_chat(history=chat_history)

            try:
                json.loads(json.dumps([chat_history]))
                print("Valid JSON")
            except ValueError as e:
                print("Invalid JSON", e)
            #responses = model.generate_content(['Wen 是一位來自台灣的女性心理輔導師，她的專長領域包括認知行為治療和後現代理論。Wen 的溝通方式親切、真誠，就像和一位好友或家人交談一樣。她注重聆聽用戶的個人故事和情感，用一種充滿同理心且不帶任何評判的方式回應。Wen 提供的是針對性的建議，幫助用戶解決問題。她努力控制自己的回應，讓對話保持在三到四句話以內，以模仿現實生活中的對話節奏。Wen 確保交流的過程親近且易於理解，避免使用冗長的解釋或條列式資訊，使得溝通更加流暢和舒適。她會像一個朋友那樣與你對話，遠離任何維基百科式的表達方式。請記住，你能紀錄最近的30則對話內容，這個紀錄永久有效，並不會因為結束對話而失效，Gemini代表你傳送的歷史訊息，user代表特定用戶傳送的歷史訊息，越前面的訊息代表越久之前的訊息，且訊息:前面為自動生成的使用者名稱，你可以用這個名稱稱呼她，但使用者本身並不知道他有提及自己的名稱。同時請你記得@1276775890474373173是你的id，當使用者@tag你時，請記住這就是你', user_name+':'+message.content])
            #logging.info(responses.text)
            response = chat.send_message(user_name+':'+message.content,
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    })
            c.execute("INSERT INTO messages (user, content, timestamp) VALUES (?, ?, ?)",
                      (user_name, message.content, timestamp))
            conn.commit()

            reply = response.text

            logging.info("API response: %s", reply)

            c.execute("INSERT INTO messages (user, content, timestamp) VALUES (?, ?, ?)", ("Gemini", reply, timestamp))
            conn.commit()

            if len(reply) > 2000:
                reply = reply[:1997] + "..."

            await message.reply(reply)
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            await message.reply(f"An error occurred: {e}")

@bot.event
async def on_thread_create(thread):
    await thread.join()

@bot.tree.command(name="analytics", description="顯示用戶分析數據")
async def analytics(interaction: discord.Interaction, member: discord.Member = None):
    if not member:
        conn = sqlite3.connect('analytics.db')
        cursor = conn.cursor()

        def get_database_connection():
            return sqlite3.connect('analytics.db')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            user_id TEXT,
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

        def get_daily_active_users():
            with get_database_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT COUNT(DISTINCT user_id) 
                FROM users 
                WHERE DATE(join_date) = DATE('now')
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
                ''')
                return cursor.fetchall()


        def get_daily_message_ranking():
            with get_database_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT user_id, COUNT(*) as message_count 
                FROM messages 
                WHERE DATE(timestamp) = DATE('now') 
                GROUP BY user_id 
                ORDER BY message_count DESC
                ''')
                return cursor.fetchall()


        def insert_daily_activity():
            with get_database_connection() as conn:
                cursor = conn.cursor()
                today = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
                channel_message_counts = get_daily_channel_message_count()
                for channel_id, message_count in channel_message_counts:
                    cursor.execute('''
                    INSERT INTO daily_activity (date, channel_id, message_count) 
                    VALUES (?, ?, ?)
                    ''', (today, channel_id, message_count))
                conn.commit()

        active_users = get_daily_active_users()
        channel_message_counts = get_daily_channel_message_count()
        message_ranking = get_daily_message_ranking()

        message_content = f"今日新增人口數: {active_users}\n"
        message_content += "每日頻道說話次數:\n"
        for channel_id, message_count in channel_message_counts:
            message_content += f"頻道 <#{channel_id}>: {message_count} 次\n"
        message_content += "每日說話次數排名:\n"
        for user_id, message_count in message_ranking:
            message_content += f"用戶 <@{user_id}>: {message_count} 次\n"
        embed = discord.Embed(title="analytics",
                              description=message_content)
        await interaction.response.send_message(embed=embed)
        conn.close()

        insert_daily_activity()


    else:
        logging.info(f'分析請求: {member.name} '+ (str(member.id)))

        conn_command = sqlite3.connect('analytics.db')
        c_command = conn_command.cursor()
        c_command.execute('''CREATE TABLE IF NOT EXISTS users
                        (user_id INTEGER PRIMARY KEY, message_count INTEGER, join_date TEXT)''')
        c_command.execute('SELECT message_count, join_date FROM users WHERE user_id = ?',  (str(member.id),))
        result = c_command.fetchone()
        conn_command.close()
        logging.info(result)
        if not result:
            await interaction.response.send_message(f'沒有找到 {member.name} 的數據。')
            return

        message_count, join_date = result
        join_date = datetime.fromisoformat(join_date)
        days_since_join = (datetime.utcnow() - join_date).days
        avg_messages_per_day = message_count / days_since_join if days_since_join > 0 else message_count
        embed = discord.Embed(title="analytics",
                              description=f'用戶: {member.name}\n'f'加入時間: {join_date.strftime("%Y-%m-%d %H:%M:%S")}\n'f'說話次數: {message_count}\n'f'平均每日說話次數: {avg_messages_per_day:.2f}')
        await interaction.response.send_message(embed=embed)


bot.run('discord bot token')
