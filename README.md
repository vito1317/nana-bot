# 奈奈 - 智能陪伴機器人 (nana_bot) v5.3.9.0

## 簡介
奈奈是一個基於 Google Gemini 模型的 Discord 機器人，旨在提供溫暖、理解和專業的陪伴，並提供一些伺服器管理功能。 奈奈也具備自行上網搜尋資料和瀏覽網站的能力，讓她的知識更豐富，回覆更精確。

## 功能

* **陪伴與支持:**
    * 使用繁體中文與用戶進行自然流暢的對話。
    * 提供情感支持和建議，擅長 DBT 辯證行為治療。
    * 記憶最近 60 則對話內容，讓互動更自然。
    * 使用者 @tag 機器人時，機器人會回應。
* **資訊檢索:**
    * 自動上網搜尋資料：奈奈可以根據對話內容，自行判斷是否需要上網搜尋資料，以提供更準確的回覆。 例如，當使用者詢問天氣、新聞或其他 factual 的資訊時，奈奈會自動搜尋相關資訊。
    * 使用 `/search google/bing/yahoo [關鍵字]` 命令，進行指定搜尋引擎的搜索並總結結果。
    * 使用 `/browse [網址]` 命令，瀏覽特定網站並總結內容。
* **伺服器管理:**
    * 監控伺服器成員加入和離開，提供相關通知。
    * `/pass` 命令：審核通過新成員，賦予其特定角色，並移除未審核角色。
    * 點數系統：
        * `/add` 命令：增加使用者點數。
        * `/subtract` 命令：減少使用者點數。
        * `/points` 命令：查詢使用者點數。
* **分析數據:**
    * `/analytics` 命令：顯示伺服器或特定成員的分析數據。

## 安裝

```bash
pip install nana-bot
```
## 設定(可跳過，直接使用設定檔>>請看下面或是使用直接設定方法)
環境變數： 建立一個 .env 檔案於專案資料夾中，並設定以下環境變數（非必要）：
```ini
NANA_API_KEY="Your Gemini API Key"
NANA_DISCORD_TOKEN="Your Discord Bot Token"
```
設定檔 (config.ini)： 除了環境變數，你也可以使用 config.ini 檔案來自訂其他設定。預設設定檔的路徑為 default_config.ini，使用者可以創建 ~/.nana_config.ini 來覆蓋預設設定。
```ini
[Nana]
gemini_model = gemini-1.5-pro-002
servers = server_id1,server_id2  # 以逗號分隔多個伺服器 ID
send_daily_channel_id_list = channel_id1,channel_id2
# ...其他設定
```

## 使用方法
```python
from nana_bot import Config, initialize_bot, run_bot
import os

# 從 .env 檔案載入環境變數
from dotenv import load_dotenv
load_dotenv()

user_config = Config(
    api_key=os.environ.get("NANA_API_KEY"),  # 從環境變數讀取
    gemini_model="gemini-1.5-pro-002",  # 或直接設定
    bot_name = "奈奈"   # 可直接設定
    review_format="我叫:\n我從這裡來:\n我的困擾有:\n是否有在諮商或就醫:\n為什麼想加入這邊:\n我最近狀況如何：", #審核格式
    pass_user_prompt_text = "{member.mention} 已通過審核，可以先到 <#{reviewed_prompt_channel_id}> 打聲招呼，也歡迎到 <#{TARGET_CHANNEL_ID[1]}> 或 <#{TARGET_CHANNEL_ID[0]}>  找othor bot或是我聊聊喔!", #審核通過後的回覆
    reviewed_role_id = [int(os.environ.get("NANA_REVIEWED_ROLE_ID"))], #已審核身分組ID
    reviewed_prompt_channel_id = int(os.environ.get("NANA_REVIEWED_PROMPT_CHANNEL_ID")), #已審核提示頻道ID
    debug = False, #debug模式
    servers=[int(os.environ.get("NANA_SERVERS"))],       # 從環境變數讀取伺服器 ID 列表
    send_daily_channel_id_list=[int(os.environ.get("NANA_SEND_DAILY_CHANNEL_ID_LIST"))], #從環境變數讀取每日頻道ID
    newcomer_channel_id = [int(os.environ.get("NANA_NEWCOMER_CHANNEL_ID"))],#從環境變數讀取新人審核頻道ID
    member_remove_channel_id = [int(os.environ.get("NANA_MEMBER_REMOVE_CHANNEL_ID"))],#從環境變數讀取用戶離開頻道ID
    not_reviewed_id = [int(os.environ.get("NANA_NOT_REVIEWED_ID"))],#從環境變數讀取未審核身分組ID
    welcome_channel_id = [int(os.environ.get("NANA_WELCOME_CHANNEL_ID"))],#從環境變數讀取歡迎頻道ID
    allowed_role_ids={int(os.environ.get("NANA_ALLOWED_ROLE_IDS"))},#從環境變數讀取允許的管理員身分組ID
    whitelisted_servers={int(os.environ.get("NANA_WHITELISTED_SERVERS")): "Server 1"},#從環境變數讀取白名單ServerID
    target_channel_id=[int(os.environ.get("NANA_TARGET_CHANNEL_ID"))],#從環境變數讀取目標說話頻道ID
    discord_bot_token=os.environ.get("NANA_DISCORD_BOT_TOKEN") #從環境變數讀取discord bot tokenID
)

initialize_bot(user_config)

run_bot()
```
### 或是使用直接設定方法
```python
from nana_bot import Config, initialize_bot, run_bot

user_config = Config(
    api_key="User's Gemini API Key", #api key
    gemini_model="gemini-1.5-pro-002", #模型
    bot_name="奈奈", #機器人名稱
    review_format="我叫:\n我從這裡來:\n我的困擾有:\n是否有在諮商或就醫:\n為什麼想加入這邊:\n我最近狀況如何：", #審核格式
    pass_user_prompt_text = "{member.mention} 已通過審核，可以先到 <#{reviewed_prompt_channel_id}> 打聲招呼，也歡迎到 <#{TARGET_CHANNEL_ID[1]}> 或 <#{TARGET_CHANNEL_ID[0]}>  找othor bot或是我聊聊喔!", #審核通過後的回覆
    reviewed_role_id = [int("user_reviewed_role_id")], #已審核身分組ID
    reviewed_prompt_channel_id = int("user_reviewed_prompt_channel_id"), #已審核提示頻道ID
    debug = False, #debug模式
    servers=[int("user_servers_id")], #servers列表
    send_daily_channel_id_list=[int("user_send_daily_channel_id")], #每日頻道ID列表
    newcomer_channel_id=[int("user_newcomer_channel_id")], #新人審核頻道ID
    member_remove_channel_id=[int("user_member_remove_channel_id")], #用戶離開頻道ID
    not_reviewed_id=[int("user_not_reviewed_id")], #未審核身分組ID
    welcome_channel_id=[int("user_welcome_channel_id")], #歡迎頻道ID
    allowed_role_ids={int("user_ALLOWED_ROLE_IDS")}, #允許的管理員身分組ID
    whitelisted_servers={int("User's Server ID"): "Server 1"}, #白名單ServerID
    target_channel_id=[int("user_TARGET_CHANNEL_ID")], #目標說話頻道ID
    discord_bot_token="Your Discord Bot Token" #discord bot tokenID
    )
initialize_bot(user_config)
run_bot()
```
## 注意事項

本機器人僅供研究和實驗使用，不應該用於任何醫療或專業諮詢。

機器人可能會產生錯誤或不準確的資訊，請勿將其視為專業意見。

機器人的功能和行為可能隨著時間推移而發生變化。

## 貢獻

歡迎您提交拉取請求和錯誤報告！

## 作者

Vito1317 - 柯瑋宸

## 授權

本專案使用 [MIT](LICENSE) 授權
## 安全政策

[SECURITY.md](SECURITY.md)
