import unittest
from nana_bot import Config, initialize_bot, get_current_time_utc8, init_db_points
import os

class TestNanaBot(unittest.TestCase):
    
    def setUp(self):
        # 配置測試參數
        self.config = Config(
            api_key="Test Gemini API Key",
            gemini_model="gemini-2.0-flash-exp",
            bot_name="Test Bot",
            debug=False,
            Point_deduction_system=0,
            default_points=100,
            review_format="test format",
            reviewed_role_id=["test_reviewed_role_id"],
            reviewed_prompt_channel_id="test_prompt_channel_id",
            pass_user_prompt_text="test pass text",
            servers=["test_server_id"],
            send_daily_channel_id_list=["test_send_daily_channel_id"],
            newcomer_channel_id=["test_newcomer_channel_id"],
            member_remove_channel_id=["test_member_remove_channel_id"],
            not_reviewed_id=["test_not_reviewed_id"],
            welcome_channel_id=["test_welcome_channel_id"],
            allowed_role_ids={"test_allowed_role_ids"},
            whitelisted_servers={"test_server_id": "Test Server"},
            target_channel_id=["test_target_channel_id"],
            discord_bot_token="Test discord bot token"
        )

    def test_initialize_bot(self):
        # 測試機器人初始化
        initialize_bot(self.config)
        import nana_bot
        
        self.assertEqual(nana_bot.API_KEY, "Test Gemini API Key")
        self.assertEqual(nana_bot.gemini_model, "gemini-2.0-flash-exp")
        self.assertEqual(nana_bot.servers, ["test_server_id"])
        self.assertEqual(nana_bot.send_daily_channel_id_list, ["test_send_daily_channel_id"])
        self.assertEqual(nana_bot.newcomer_channel_id, ["test_newcomer_channel_id"])
        self.assertEqual(nana_bot.member_remove_channel_id, ["test_member_remove_channel_id"])
        self.assertEqual(nana_bot.not_reviewed_id, ["test_not_reviewed_id"])
        self.assertEqual(nana_bot.welcome_channel_id, ["test_welcome_channel_id"])
        self.assertEqual(nana_bot.ALLOWED_ROLE_IDS, {"test_allowed_role_ids"})
        self.assertEqual(nana_bot.WHITELISTED_SERVERS, {"test_server_id": "Test Server"})
        self.assertEqual(nana_bot.TARGET_CHANNEL_ID, ["test_target_channel_id"])
        self.assertEqual(nana_bot.discord_bot_token, "Test discord bot token")

    def test_get_current_time_utc8(self):
        current_time = get_current_time_utc8()
        self.assertIsNotNone(current_time)
        
    def test_init_db_points(self):
        init_db_points("test_guild_id")
        db_path = "./databases/points_test_guild_id.db"
        self.assertTrue(os.path.exists(db_path))

if __name__ == "__main__":
    unittest.main()
