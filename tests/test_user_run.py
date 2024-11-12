from nana_bot import Config, initialize_bot, run_bot

user_config = Config(
    api_key="User's Gemini API Key", #api key
    gemini_model="gemini-1.5-pro-002", #模型
    bot_name="奈奈", #機器人名稱
    review_format="我叫:\n我從這裡來:\n我的困擾有:\n是否有在諮商或就醫:\n為什麼想加入這邊:\n我最近狀況如何：", #審核格式
    pass_user_prompt_text = "{member.mention} 已通過審核，可以先到 <#{reviewed_prompt_channel_id}> 打聲招呼，也歡迎到 <#1282901299624677448> 或 <#{TARGET_CHANNEL_ID[0]}>  找Wen或是我聊聊喔!", #審核通過後的回覆
    reviewed_role_id = [int("user_reviewed_role_id")], #已審核身分組ID
    reviewed_prompt_channel_id = int("user_reviewed_prompt_channel_id"), #審核提示頻道ID
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