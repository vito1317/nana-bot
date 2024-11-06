# 奈奈 - 智能陪伴機器人 v5.1.1

奈奈是一個基於 [Gemini](https://cloud.google.com/generative-ai/docs/reference/rest/v1beta/projects.locations.models) 模型的 Discord 機器人，旨在提供溫暖、理解和專業的陪伴，並提供一些伺服器管理功能。

## 功能

* **陪伴與支持:**
    * 使用繁體中文與用戶進行自然流暢的對話。
    * 提供情感支持和建議，擅長 DBT 辯證行為治療。
    * 記憶最近 60 則對話內容，讓互動更自然。
    * 使用者 @tag 機器人時，機器人會回應。
* **資訊檢索:**
    * 使用 `/search google/yahoo [關鍵字]` 命令，進行搜索並總結結果。
    * 使用 `/browse [網址]` 命令，瀏覽網站並總結內容。
* **伺服器管理:**
    * 監控伺服器成員加入和離開，提供相關通知。
    * `/pass` 命令：審核通過新成員，賦予其特定角色，並移除未審核角色。
    * 點數系統：
        * `/add` 命令：增加使用者點數。
        * `/subtract` 命令：減少使用者點數。
        * `/points` 命令：查詢使用者點數。
* **分析數據:**
    * `/analytics` 命令：顯示伺服器或特定成員的分析數據。


## 設定

1. 取得 Google Cloud Platform API 金鑰。
2. 設定 `config.py` 檔案，並設定以下變數：
    * `API_KEY`:  Google Cloud API 金鑰。
    * `discord_bot_token`: Discord 機器人 Token。
    * `servers`: 伺服器 ID 列表。
    * `welcome_channel_id`: 歡迎頻道 ID 列表。
    * `not_reviewed_id`: 未審核角色 ID 列表。
    * `newcomer_channel_id`: 新人審核頻道 ID 列表。
    * `send_daily_channel_id_list`: 每日訊息發送頻道 ID 列表。
    * `member_remove_channel_id`: 成員離開通知頻道 ID 列表。
    * `gemini_model`: Gemini 模型名稱。
    * `ALLOWED_ROLE_IDS`: 允許使用管理命令的角色 ID 列表。
    * `GUILD_ID`:  Discord 伺服器 ID。


## 啟動

1. 安裝必要的套件：
   ```bash
   pip install -r requirements.txt
   ```
content_copy
Use code with caution.
Markdown

執行機器人：
```bash
python bot.py
```
## 指令權限

/pass、/add 和 /subtract 命令需要特定角色才能使用，這些角色 ID 需設定在 config.py 的 ALLOWED_ROLE_IDS 變數中。

## 資料庫

機器人使用 SQLite 資料庫儲存資料，包括：

analytics_server_[server_id].db: 伺服器分析數據，例如成員加入/離開時間、訊息數量等。

messages_chat_[server_id].db: 聊天訊息紀錄。

points_[server_id].db: 使用者點數資料。

## 注意事項

本機器人僅供研究和實驗使用，不應該用於任何醫療或專業諮詢。

機器人可能會產生錯誤或不準確的資訊，請勿將其視為專業意見。

機器人的功能和行為可能隨著時間推移而發生變化。

## 貢獻

歡迎您提交拉取請求和錯誤報告！

## 作者

Vito1317 -柯瑋宸

## 安全政策

請查看[奈奈 - 安全政策](SECURITY.md)來了解奈奈的安全政策。

## 授權

本專案使用 [MIT](LICENSE) 授權。
