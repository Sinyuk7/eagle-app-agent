from __future__ import annotations

import os
import unittest
from unittest import mock

from moodtag.ui import locale


class LocaleTests(unittest.TestCase):
    def test_unset_language_defaults_to_english(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.ui.locale._system_language", return_value="zh"),
        ):
            self.assertEqual(locale.language(), "en")

    def test_empty_language_follows_system_language(self):
        with (
            mock.patch.dict(os.environ, {"MOODTAG_LANG": ""}, clear=True),
            mock.patch("moodtag.ui.locale._system_language", return_value="zh"),
        ):
            self.assertEqual(locale.language(), "zh")

    def test_language_override_accepts_chinese_locale(self):
        with mock.patch.dict(os.environ, {"MOODTAG_LANG": "zh-CN"}, clear=True):
            self.assertEqual(locale.language(), "zh")

    def test_language_override_accepts_english(self):
        with mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}, clear=True):
            self.assertEqual(locale.language(), "en")
