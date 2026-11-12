import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

from notifier import StockNotifier


class TelegramNotificationTests(unittest.TestCase):
    @patch("notifier.requests.post")
    def test_telegram_http_error_is_reported_as_failure(self, post):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("bad request")
        post.return_value = response

        notifier = StockNotifier()
        notifier.tg_token = "test-token"
        notifier.tg_chat_id = "test-chat"

        self.assertFalse(notifier.send_telegram("test"))

    @patch("notifier.requests.post")
    def test_telegram_api_error_is_reported_as_failure(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": False, "description": "chat not found"}
        post.return_value = response

        notifier = StockNotifier()
        notifier.tg_token = "test-token"
        notifier.tg_chat_id = "test-chat"

        self.assertFalse(notifier.send_telegram("test"))

    @patch.object(StockNotifier, "send_telegram", return_value=False)
    def test_missing_email_recipient_skips_email_without_failing_pipeline(self, send_telegram):
        notifier = StockNotifier()
        notifier.report_receiver_email = None
        report = pd.DataFrame({"Ticker": ["2330.TW"]})

        self.assertTrue(
            notifier.send_stock_report(
                market_name="台灣股市",
                img_data=[],
                report_df=report,
                text_reports={},
                stats={"total": 1, "success": 1, "fail": 0},
            )
        )
        send_telegram.assert_called_once()


if __name__ == "__main__":
    unittest.main()
