import unittest

from ui.screens import (
    format_recording_time,
    looping_typed_text,
    typed_text,
)


class TypingAnimationTests(unittest.TestCase):
    def test_typed_text_reveals_characters_over_time(self) -> None:
        self.assertEqual(typed_text("Hum", 0, 100), "")
        self.assertEqual(typed_text("Hum", 100, 100), "H")
        self.assertEqual(typed_text("Hum", 300, 100), "Hum")

    def test_looping_text_restarts_after_hold(self) -> None:
        self.assertEqual(looping_typed_text("Hi", 200, 100, 300), "Hi")
        self.assertEqual(looping_typed_text("Hi", 499, 100, 300), "Hi")
        self.assertEqual(looping_typed_text("Hi", 500, 100, 300), "")

    def test_recording_time_is_formatted_as_minutes_and_seconds(self) -> None:
        self.assertEqual(format_recording_time(0), "00:00")
        self.assertEqual(format_recording_time(4.99), "00:04")
        self.assertEqual(format_recording_time(65), "01:05")


if __name__ == "__main__":
    unittest.main()
