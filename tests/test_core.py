from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_clients import (  # noqa: E402
    PAGE_SIZE,
    LyricsError,
    SearchPage,
    normalize_lrc,
)
from lyrics_app import sanitize_filename, write_lrc  # noqa: E402


class FilenameTests(unittest.TestCase):
    def test_illegal_characters_are_replaced(self) -> None:
        self.assertEqual(sanitize_filename('A/B:C*D?"E<F>G|H'), "A_B_C_D_E_F_G_H")

    def test_reserved_windows_name_is_escaped(self) -> None:
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("con.txt"), "_con.txt")

    def test_empty_and_overlong_names_are_handled(self) -> None:
        self.assertEqual(sanitize_filename("   "), "未命名歌词")
        self.assertEqual(len(sanitize_filename("歌" * 300)), 100)

    def test_trailing_dots_and_spaces_are_removed(self) -> None:
        self.assertEqual(sanitize_filename("晴天. "), "晴天")


class LyricsFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(__file__).resolve().parent / "_tmp"
        shutil.rmtree(self.directory, ignore_errors=True)
        self.directory.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_writes_utf8_bom_and_crlf(self) -> None:
        path = write_lrc(self.directory, "晴天", "[00:00.00]故事的小黄花\n")
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn("\r\n".encode("utf-8"), raw)
        self.assertEqual(path.name, "晴天.lrc")

    def test_never_overwrites_an_existing_file(self) -> None:
        first = write_lrc(self.directory, "晴天", "[00:00.00]第一份\n")
        second = write_lrc(self.directory, "晴天", "[00:00.00]第二份\n")
        self.assertNotEqual(first, second)
        self.assertEqual(second.name, "晴天 (2).lrc")
        self.assertIn("第一份", first.read_text(encoding="utf-8-sig"))
        self.assertIn("第二份", second.read_text(encoding="utf-8-sig"))


class NormalizeLyricTests(unittest.TestCase):
    def test_html_entities_and_blank_lines_are_cleaned(self) -> None:
        lyric = normalize_lrc("&lt;测试&gt;\r\n\r\n[00:01.00]下一句  \r\n")
        self.assertEqual(lyric, "<测试>\n\n[00:01.00]下一句\n")

    def test_tag_only_content_is_rejected(self) -> None:
        with self.assertRaises(LyricsError):
            normalize_lrc("[ti:纯音乐]\n[ar:歌手]\n")

    def test_empty_content_is_rejected(self) -> None:
        with self.assertRaises(LyricsError):
            normalize_lrc("")


class PaginationTests(unittest.TestCase):
    def test_total_pages_is_at_least_one(self) -> None:
        self.assertEqual(SearchPage([], 0, 1).total_pages, 1)
        self.assertEqual(SearchPage([], PAGE_SIZE, 1).total_pages, 1)
        self.assertEqual(SearchPage([], PAGE_SIZE + 1, 1).total_pages, 2)


if __name__ == "__main__":
    unittest.main()
