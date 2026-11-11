"""网易云音乐、QQ 音乐、酷狗音乐的搜索与歌词接口。

这些接口均为各音乐平台网页端正在使用的公开接口，不需要登录。
接口可能随平台调整而变化，所有错误都会转换成面向用户的中文提示。
"""

from __future__ import annotations

import base64
import binascii
import html
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

PAGE_SIZE = 20
SOURCES = ("netease", "qq", "kugou")

SOURCE_LABELS = {
    "netease": "网易云音乐",
    "qq": "QQ音乐",
    "kugou": "酷狗音乐",
}

SOURCE_ACCENTS = {
    "netease": "#E11D48",
    "qq": "#16A34A",
    "kugou": "#0284C7",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BASE_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
}


class LyricsError(Exception):
    """可直接展示给用户的接口错误。"""


@dataclass(frozen=True)
class Track:
    source: str
    track_id: str
    title: str
    artists: str
    album: str
    duration: int = 0


@dataclass(frozen=True)
class SearchPage:
    tracks: list[Track]
    total: int
    page: int

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / PAGE_SIZE))


def _clean(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = html.unescape(str(value)).replace("\xa0", " ").strip()
    return text or fallback


def _join_artists(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        names = [_clean(item.get("name") if isinstance(item, dict) else item) for item in value]
        names = [name for name in names if name]
        return "、".join(dict.fromkeys(names)) or "未知歌手"
    return _clean(value, "未知歌手")


def _duration(value: Any) -> int:
    try:
        number = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    # 网易云返回毫秒，QQ 与酷狗返回秒。
    return max(0, number)


def _decode_json(response: requests.Response, service: str) -> dict[str, Any]:
    raw = response.content
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        logger.debug("%s 返回非 JSON 内容：%s", service, text[:300])
        raise LyricsError(f"{service}接口返回异常，请稍后重试") from exc
    if not isinstance(data, dict):
        raise LyricsError(f"{service}接口返回异常，请稍后重试")
    return data


def _get_json(
    url: str,
    params: dict[str, Any],
    *,
    service: str,
    referer: str,
    origin: str | None = None,
) -> dict[str, Any]:
    headers = dict(_BASE_HEADERS)
    headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=(7, 16),
            )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                raise LyricsError(f"{service}暂时限制了请求，请稍后再试")
            if response.status_code >= 400:
                raise LyricsError(f"{service}接口请求失败（HTTP {response.status_code}）")
            return _decode_json(response, service)
        except LyricsError:
            raise
        except requests.Timeout as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.4)
                continue
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.4)
                continue
        except Exception as exc:  # 防御性兜底，避免后台线程直接崩掉
            last_error = exc
            break

    logger.debug("%s 请求失败：%s", service, last_error)
    raise LyricsError(f"{service}网络连接失败，请检查网络后重试")


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------


def _search_netease(query: str, page: int) -> SearchPage:
    data = _get_json(
        "https://music.163.com/api/search/get/web",
        {
            "s": query,
            "type": 1,
            "offset": (page - 1) * PAGE_SIZE,
            "limit": PAGE_SIZE,
        },
        service="网易云音乐",
        referer="https://music.163.com/",
        origin="https://music.163.com",
    )
    result = data.get("result") or {}
    songs = result.get("songs") or []
    if not isinstance(songs, list):
        songs = []

    tracks: list[Track] = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        track_id = song.get("id")
        if track_id is None:
            continue
        album = song.get("album") or {}
        if not isinstance(album, dict):
            album = {}
        tracks.append(
            Track(
                source="netease",
                track_id=str(track_id),
                title=_clean(song.get("name"), "未知歌曲"),
                artists=_join_artists(song.get("artists") or song.get("ar")),
                album=_clean(album.get("name"), "未知专辑"),
                duration=_duration(song.get("duration")),
            )
        )

    try:
        total = int(result.get("songCount") or 0)
    except (TypeError, ValueError):
        total = 0
    if total < len(tracks):
        total = len(tracks)
    return SearchPage(tracks=tracks, total=total, page=page)


def _search_qq(query: str, page: int) -> SearchPage:
    data = _get_json(
        "https://c.y.qq.com/soso/fcgi-bin/client_search_cp",
        {
            "p": page,
            "n": PAGE_SIZE,
            "w": query,
            "format": "json",
            "cr": 1,
            "aggr": 1,
            "lossless": 0,
            "flag_qc": 0,
        },
        service="QQ音乐",
        referer="https://y.qq.com/",
        origin="https://y.qq.com",
    )
    payload = data.get("data") or {}
    song_block = payload.get("song") or {}
    songs = song_block.get("list") or []
    if not isinstance(songs, list):
        songs = []

    tracks: list[Track] = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        song_mid = song.get("songmid") or song.get("mid")
        if not song_mid:
            continue
        album = song.get("albumname")
        if album is None and isinstance(song.get("album"), dict):
            album = song["album"].get("name")
        tracks.append(
            Track(
                source="qq",
                track_id=str(song_mid),
                title=_clean(song.get("songname") or song.get("name"), "未知歌曲"),
                artists=_join_artists(song.get("singer") or song.get("ar")),
                album=_clean(album, "未知专辑"),
                duration=_duration(song.get("interval")),
            )
        )

    try:
        total = int(song_block.get("totalnum") or 0)
    except (TypeError, ValueError):
        total = 0
    if total < len(tracks):
        total = len(tracks)
    return SearchPage(tracks=tracks, total=total, page=page)


def _search_kugou(query: str, page: int) -> SearchPage:
    data = _get_json(
        "https://songsearch.kugou.com/song_search_v2",
        {
            "keyword": query,
            "page": page,
            "pagesize": PAGE_SIZE,
            "platform": "WebFilter",
            "userid": 0,
            "clientver": 2000,
            "iscorrection": 1,
            "privilege_filter": 0,
            "filter": 10,
        },
        service="酷狗音乐",
        referer="https://www.kugou.com/",
        origin="https://www.kugou.com",
    )
    payload = data.get("data") or {}
    songs = payload.get("lists") or []
    if not isinstance(songs, list):
        songs = []

    tracks: list[Track] = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        # FileHash 是歌词接口需要的音频 hash，没有它就无法定位歌词。
        file_hash = song.get("FileHash") or song.get("HQFileHash") or song.get("SQFileHash")
        if not file_hash:
            continue
        tracks.append(
            Track(
                source="kugou",
                track_id=str(file_hash),
                title=_clean(song.get("SongName"), "未知歌曲"),
                artists=_clean(song.get("SingerName"), "未知歌手").replace("/", "、"),
                album=_clean(song.get("AlbumName"), "未知专辑"),
                duration=_duration(song.get("Duration")),
            )
        )

    try:
        total = int(payload.get("total") or 0)
    except (TypeError, ValueError):
        total = 0
    if total < len(tracks):
        total = len(tracks)
    return SearchPage(tracks=tracks, total=total, page=page)


_SEARCHERS: dict[str, Callable[[str, int], SearchPage]] = {
    "netease": _search_netease,
    "qq": _search_qq,
    "kugou": _search_kugou,
}


def search(source: str, query: str, page: int = 1) -> SearchPage:
    """按平台搜索歌曲。异常统一转换为 LyricsError。"""
    query = (query or "").strip()
    if not query:
        raise LyricsError("请输入歌曲名或歌手名")
    if source not in _SEARCHERS:
        raise ValueError(f"未知音乐平台：{source}")
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    return _SEARCHERS[source](query, page)


# ---------------------------------------------------------------------------
# 歌词
# ---------------------------------------------------------------------------


_TAG_ONLY_LINE = re.compile(r"^(?:\s*\[[^\]]+\]\s*)+$")


def normalize_lrc(text: Any) -> str:
    """清理接口返回的歌词，拒绝空歌词，并统一为 UTF-8 文本格式。"""
    if not text:
        raise LyricsError("该歌曲暂无可下载的歌词")
    cleaned = html.unescape(str(text))
    cleaned = cleaned.replace("\ufeff", "").replace("\x00", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in cleaned.split("\n")]

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    meaningful = [
        line for line in lines if line.strip() and not _TAG_ONLY_LINE.match(line.strip())
    ]
    if not meaningful:
        raise LyricsError("该歌曲暂无可下载的歌词（可能为纯音乐）")
    return "\n".join(lines) + "\n"


def _fetch_netease(track: Track) -> str:
    data = _get_json(
        "https://music.163.com/api/song/lyric",
        {"id": track.track_id, "lv": -1, "kv": -1, "tv": -1},
        service="网易云音乐",
        referer="https://music.163.com/",
        origin="https://music.163.com",
    )
    lrc = data.get("lrc") or {}
    lyric = lrc.get("lyric") if isinstance(lrc, dict) else ""
    if not lyric:
        klyric = data.get("klyric") or {}
        lyric = klyric.get("lyric") if isinstance(klyric, dict) else ""
    if not lyric:
        raise LyricsError("网易云音乐暂未提供这首歌的歌词（可能为纯音乐）")
    return normalize_lrc(lyric)


def _fetch_qq(track: Track) -> str:
    data = _get_json(
        "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg",
        {"songmid": track.track_id, "format": "json", "nobase64": 1},
        service="QQ音乐",
        referer="https://y.qq.com/",
        origin="https://y.qq.com",
    )
    retcode = data.get("retcode", data.get("code", 0))
    if retcode not in (0, "0", None):
        raise LyricsError("QQ音乐暂未提供这首歌的歌词")
    lyric = data.get("lyric") or ""
    if not lyric:
        raise LyricsError("QQ音乐暂未提供这首歌的歌词（可能为纯音乐）")
    return normalize_lrc(lyric)


def _kugou_candidates(track: Track) -> list[dict[str, Any]]:
    data = _get_json(
        "https://krcs.kugou.com/search",
        {
            "ver": 1,
            "man": "yes",
            "client": "mobi",
            "keyword": "",
            "duration": "",
            "hash": track.track_id,
        },
        service="酷狗音乐",
        referer="https://www.kugou.com/",
        origin="https://www.kugou.com",
    )
    candidates = data.get("candidates") or []
    return [item for item in candidates if isinstance(item, dict)]


def _fetch_kugou(track: Track) -> str:
    candidates = _kugou_candidates(track)
    if not candidates:
        raise LyricsError("酷狗音乐暂未提供这首歌的歌词（可能为纯音乐）")

    last_error: Exception | None = None
    for candidate in candidates[:4]:
        candidate_id = candidate.get("id") or candidate.get("download_id")
        access_key = candidate.get("accesskey")
        if not candidate_id or not access_key:
            continue
        try:
            data = _get_json(
                "https://lyrics.kugou.com/download",
                {
                    "ver": 1,
                    "client": "pc",
                    "id": candidate_id,
                    "accesskey": access_key,
                    "fmt": "lrc",
                    "charset": "utf8",
                },
                service="酷狗音乐",
                referer="https://www.kugou.com/",
                origin="https://www.kugou.com",
            )
            content = data.get("content") or ""
            if not content:
                continue
            raw = base64.b64decode(content)
            try:
                lyric = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                lyric = raw.decode("gb18030", errors="replace")
            return normalize_lrc(lyric)
        except (LyricsError, ValueError, UnicodeError, binascii.Error) as exc:
            last_error = exc
            continue

    if isinstance(last_error, LyricsError):
        raise last_error
    raise LyricsError("酷狗音乐歌词下载失败，请稍后重试")


_FETCHERS: dict[str, Callable[[Track], str]] = {
    "netease": _fetch_netease,
    "qq": _fetch_qq,
    "kugou": _fetch_kugou,
}


def fetch_lyric(track: Track) -> str:
    """获取指定歌曲的 LRC 文本。异常统一转换为 LyricsError。"""
    if track.source not in _FETCHERS:
        raise ValueError(f"未知音乐平台：{track.source}")
    return _FETCHERS[track.source](track)
