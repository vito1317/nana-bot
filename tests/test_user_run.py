from nana_bot import Config, initialize_bot, run_bot


user_config = Config(
    api_key="User's Gemini API Key",
    gemini_model="gemini-1.5-pro-002",
    bot_name="奈奈",
    servers=[int("user_servers_id")],
    send_daily_channel_id_list=[int("user_send_daily_channel_id")],
    newcomer_channel_id=[int("user_newcomer_channel_id")],
    member_remove_channel_id=[int("user_member_remove_channel_id")],
    not_reviewed_id=[int("user_not_reviewed_id")],
    welcome_channel_id=[int("user_welcome_channel_id")],
    allowed_role_ids={int("user_ALLOWED_ROLE_IDS")},
    whitelisted_servers={int("User's Server ID"): "Server 1"},
    target_channel_id=[int("user_TARGET_CHANNEL_ID")],
    discord_bot_token="Your Discord Bot Token"
)

initialize_bot(user_config)
run_bot()
