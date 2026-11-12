import unittest
from unittest.mock import Mock

from notifier import deliver_notification_channels


class NotificationDeliveryTests(unittest.TestCase):
    def test_email_unconfigured_telegram_still_sends(self):
        telegram = Mock(return_value=True)
        ok, email_sent, telegram_sent = deliver_notification_channels(
            False, True, Mock(), telegram, logger=lambda _: None
        )
        self.assertTrue(ok)
        self.assertFalse(email_sent)
        self.assertTrue(telegram_sent)
        telegram.assert_called_once_with(False)

    def test_email_failure_does_not_block_telegram(self):
        email = Mock(side_effect=RuntimeError("email unavailable"))
        telegram = Mock(return_value=True)
        ok, email_sent, telegram_sent = deliver_notification_channels(
            True, True, email, telegram, logger=lambda _: None
        )
        self.assertTrue(ok)
        self.assertFalse(email_sent)
        self.assertTrue(telegram_sent)
        telegram.assert_called_once_with(False)

    def test_telegram_failure_does_not_fail_successful_email(self):
        email = Mock()
        telegram = Mock(return_value=False)
        ok, email_sent, telegram_sent = deliver_notification_channels(
            True, True, email, telegram, logger=lambda _: None
        )
        self.assertTrue(ok)
        self.assertTrue(email_sent)
        self.assertFalse(telegram_sent)
        telegram.assert_called_once_with(True)

    def test_no_configured_channels_is_failure(self):
        ok, email_sent, telegram_sent = deliver_notification_channels(
            False, False, Mock(), Mock(), logger=lambda _: None
        )
        self.assertFalse(ok)
        self.assertFalse(email_sent)
        self.assertFalse(telegram_sent)


if __name__ == "__main__":
    unittest.main()
