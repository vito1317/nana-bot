import unittest
from nana_bot import Config, initialize_bot, get_current_time_utc8, init_db_points
import os

class TestNanaBot(unittest.TestCase):
    
    def setUp(self):
        # 配置測試參數
        self.config = Config(
            api_key="Test Gemini API Key",
            gemini_model="gemini-1.5-pro-002",
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
        bot = initialize_bot(self.config)
        
        self.assertIsNotNone(bot)
        self.assertEqual(bot.api_key, "Test Gemini API Key")
        self.assertEqual(bot.gemini_model, "gemini-1.5-pro-002")
        self.assertEqual(bot.servers, ["test_server_id"])
        self.assertEqual(bot.send_daily_channel_id_list, ["test_send_daily_channel_id"])
        self.assertEqual(bot.newcomer_channel_id, ["test_newcomer_channel_id"])
        self.assertEqual(bot.member_remove_channel_id, ["test_member_remove_channel_id"])
        self.assertEqual(bot.not_reviewed_id, ["test_not_reviewed_id"])
        self.assertEqual(bot.welcome_channel_id, ["test_welcome_channel_id"])
        self.assertEqual(bot.allowed_role_ids, {"test_allowed_role_ids"})
        self.assertEqual(bot.whitelisted_servers, {"test_server_id": "Test Server"})
        self.assertEqual(bot.target_channel_id, ["test_target_channel_id"])
        self.assertEqual(bot.discord_bot_token, "Test discord bot token")

    def test_get_current_time_utc8(self):
        current_time = get_current_time_utc8()
        self.assertIsNotNone(current_time)
        
    def test_init_db_points(self):
        init_db_points("test_guild_id")
        db_path = "./databases/points_test_guild_id.db"
        self.assertTrue(os.path.exists(db_path))

if __name__ == "__main__":
    unittest.main()
