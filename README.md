# 奈奈 - 智能陪伴機器人

奈奈是一個基於 [Gemini](https://cloud.google.com/generative-ai/docs/reference/rest/v1beta/projects.locations.models) 模型的 Discord 機器人，旨在提供溫暖、理解和專業的陪伴。

## 功能

* 使用繁體中文與用戶進行自然流暢的對話。
* 提供情感支持和建議，擅長DBT辯證行為治療。
* 記憶最近60則對話內容，讓互動更自然。
* 使用者@tag機器人時，機器人會回應。
* 使用 `/search google/bing/yahoo [關鍵字]` 命令，進行搜索並總結結果。
* 使用 `/browse [網址]` 命令，瀏覽網站並總結內容。
* 監控伺服器成員加入和離開，提供相關通知。

## 設定

1. 取得 Google Cloud Platform API 金鑰。
2. 將金鑰設定在 `config.py` 檔案的 `API_KEY` 變數中。
3. 將 Discord 機器人 Token 設定在 `config.py` 檔案的 `discord_bot_token` 變數中。
4. 將伺服器 ID 設定在 `config.py` 檔案的 `servers` 變數中。
5. 將歡迎頻道 ID 設定在 `config.py` 檔案的 `welcome_channel_id` 變數中。
6. 將未審核角色 ID 設定在 `config.py` 檔案的 `not_reviewed_id` 變數中。
7. 將新人審核頻道 ID 設定在 `config.py` 檔案的 `newcomer_channel_id` 變數中。
8. 將每日訊息發送頻道 ID 設定在 `config.py` 檔案的 `send_daily_channel_id_list` 變數中。
9. 將成員離開通知頻道 ID 設定在 `config.py` 檔案的 `member_remove_channel_id` 變數中。
10. 將 Gemini 模型名稱設定在 `config.py` 檔案的 `gemini_model` 變數中。

## 啟動

1. 安裝必要的套件：
   ```bash
   pip install -r requirements.txt
   ```

## 執行機器人：
```bash
python bot.py
```
## 注意事項

本機器人僅供研究和實驗使用，不應該用於任何醫療或專業諮詢。

機器人可能會產生錯誤或不準確的資訊，請勿將其視為專業意見。

機器人的功能和行為可能隨著時間推移而發生變化。

## 貢獻

歡迎您提交拉取請求和錯誤報告！

## 作者

Vito1317

## 授權

本專案使用 MIT 授權。

