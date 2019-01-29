# bubblesub - ASS subtitle editor
# Copyright (C) 2018 Marcin Kurczewski
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import typing as T
from unittest.mock import MagicMock

import pytest

from bubblesub.api.cmd import CommandError, CommandUnavailable
from bubblesub.ass.event import Event, EventList
from bubblesub.cmd.common import Pts


def _assert_pts_value(
    pts: Pts,
    expected_value: T.Union[int, T.Type[CommandError]],
    origin: T.Optional[int] = None,
) -> None:
    actual_value: T.Union[int, T.Type[CommandError]] = 0
    try:
        actual_value = asyncio.get_event_loop().run_until_complete(
            pts.get(origin=origin)
        )
    except CommandError as ex:
        actual_value = type(ex)

    assert actual_value == expected_value


@pytest.mark.parametrize(
    "expr,origin,expected_value",
    [
        ("", None, CommandError),
        ("", 25, CommandError),
        ("+", None, CommandError),
        ("+", 25, CommandError),
        ("0ms+", None, CommandError),
        ("0ms+", 25, CommandError),
        ("0ms++", None, CommandError),
        ("0ms++", 25, CommandError),
        ("500ms", None, 500),
        ("500ms", 25, 500),
        ("+500ms", None, 500),
        ("+500ms", 25, 525),
        ("-500ms", None, -500),
        ("-500ms", 25, -475),
        ("0ms+500ms", None, 500),
        ("0ms+500ms", 25, 500),
        ("25ms+500ms", None, 525),
        ("25ms+500ms", 25, 525),
        ("500ms-25ms", None, 475),
        ("500ms-25ms", 25, 475),
        ("500", None, CommandError),
        ("500", 0, CommandError),
        ("ms", None, CommandError),
        ("ms", 0, CommandError),
        ("cfcf", None, CommandError),
        ("cfcf", 0, CommandError),
        ("0 ms", None, 0),
        ("0ms + 0ms", None, 0),
        ("0ms  +  0ms", None, 0),
        ("  0ms  +  0ms  ", None, 0),
    ],
)
def test_basic_arithmetic(
    expr: str,
    origin: T.Optional[int],
    expected_value: T.Union[int, T.Type[CommandError]],
) -> None:
    api = MagicMock()
    pts = Pts(api, expr)

    _assert_pts_value(pts, expected_value, origin)


@pytest.mark.parametrize(
    "expr,sub_times,sub_selection,expected_value",
    [
        ("cs.s", [(1, 2), (3, 4), (5, 6)], [1], 3),
        ("cs.e", [(1, 2), (3, 4), (5, 6)], [1], 4),
        ("ps.s", [(1, 2), (3, 4), (5, 6)], [1], 1),
        ("ps.e", [(1, 2), (3, 4), (5, 6)], [1], 2),
        ("ns.s", [(1, 2), (3, 4), (5, 6)], [1], 5),
        ("ns.e", [(1, 2), (3, 4), (5, 6)], [1], 6),
        ("ps.s", [(1, 2), (3, 4), (5, 6)], [0], 0),
        ("ps.e", [(1, 2), (3, 4), (5, 6)], [0], 0),
        ("ns.s", [(1, 2), (3, 4), (5, 6)], [2], 0),
        ("ns.e", [(1, 2), (3, 4), (5, 6)], [2], 0),
        ("s1.s", [(1, 2), (3, 4), (5, 6)], [], 1),
        ("s1.e", [(1, 2), (3, 4), (5, 6)], [], 2),
        ("s2.s", [(1, 2), (3, 4), (5, 6)], [], 3),
        ("s2.e", [(1, 2), (3, 4), (5, 6)], [], 4),
        ("s3.s", [(1, 2), (3, 4), (5, 6)], [], 5),
        ("s3.e", [(1, 2), (3, 4), (5, 6)], [], 6),
        ("s1.s", [], [], 0),
        ("s1.e", [], [], 0),
        ("s3.s", [(1, 2)], [], 1),
        ("s3.e", [(1, 2)], [], 2),
        ("s0.s", [(1, 2)], [], 1),
        ("s0.e", [(1, 2)], [], 2),
    ],
)
def test_subtitles(
    expr: str,
    sub_times: T.List[T.Tuple[int, int]],
    sub_selection: T.List[int],
    expected_value: int,
) -> None:
    api = MagicMock()
    api.subs.events = EventList()
    for start, end in sub_times:
        api.subs.events.append(Event(start=start, end=end))
    for i, event in enumerate(api.subs.events):
        event.prev = api.subs.events[i - 1] if i > 0 else None
        try:
            event.next = api.subs.events[i + 1]
        except LookupError:
            event.next = None
    api.subs.selected_events = [api.subs.events[idx] for idx in sub_selection]
    pts = Pts(api, expr)

    _assert_pts_value(pts, expected_value)


@pytest.mark.parametrize(
    "expr,frame_times,cur_frame_idx,keyframe_indexes,expected_value",
    [
        ("cf", [10, 20, 30], 1, [], 20),
        ("pf", [10, 20, 30], 1, [], 10),
        ("nf", [10, 20, 30], 1, [], 30),
        ("cf", [], ..., [], 0),
        ("pf", [], ..., [], CommandError),
        ("nf", [], ..., [], CommandError),
        ("1f", [10, 20, 30], ..., [], 10),
        ("2f", [10, 20, 30], ..., [], 20),
        ("3f", [10, 20, 30], ..., [], 30),
        ("0f", [10, 20, 30], ..., [], 10),
        ("5f", [10, 20, 30], ..., [], 30),
        ("1f", [], ..., [], CommandError),
        ("5ms+1f", [10, 20, 30], ..., [], 10),
        ("9ms+1f", [10, 20, 30], ..., [], 10),
        ("10ms+1f", [10, 20, 30], ..., [], 20),
        ("11ms+1f", [10, 20, 30], ..., [], 20),
        ("30ms+1f", [10, 20, 30], ..., [], 30),
        ("31ms+1f", [10, 20, 30], ..., [], 30),
        ("9ms-1f", [10, 20, 30], ..., [], 10),
        ("10ms-1f", [10, 20, 30], ..., [], 10),
        ("11ms-1f", [10, 20, 30], ..., [], 10),
        ("19ms-1f", [10, 20, 30], ..., [], 10),
        ("20ms-1f", [10, 20, 30], ..., [], 10),
        ("21ms-1f", [10, 20, 30], ..., [], 20),
        ("31ms-1f", [10, 20, 30], ..., [], 30),
        ("1f+1f", [10, 20, 30], ..., [], 20),
        ("1f+1ms", [10, 20, 30], ..., [], 11),
        ("1f+1ms+1f", [10, 20, 30], ..., [], 20),
        ("ckf", [10, 20, 30, 40], 1, [0, 1, 3], 20),
        ("ckf", [10, 20, 30, 40], 2, [0, 1, 3], 20),
        ("pkf", [10, 20, 30, 40], 1, [0, 1, 3], 10),
        ("nkf", [10, 20, 30, 40], 1, [0, 1, 2], 30),
        ("nkf", [10, 20, 30, 40], 1, [0, 1, 3], 40),
        ("ckf", [], ..., [], CommandError),
        ("pkf", [], ..., [], CommandError),
        ("nkf", [], ..., [], CommandError),
        ("1kf", [10, 20, 30], ..., [0, 2], 10),
        ("2kf", [10, 20, 30], ..., [0, 2], 30),
        ("0kf", [10, 20, 30], ..., [0, 2], 10),
        ("3kf", [10, 20, 30], ..., [0, 2], 30),
        ("1kf", [], ..., [], CommandError),
        ("5ms+1kf", [10, 20, 30], ..., [0, 2], 10),
        ("9ms+1kf", [10, 20, 30], ..., [0, 2], 10),
        ("10ms+1kf", [10, 20, 30], ..., [0, 1], 20),
        ("10ms+1kf", [10, 20, 30], ..., [0, 2], 30),
        ("11ms+1kf", [10, 20, 30], ..., [0, 1], 20),
        ("11ms+1kf", [10, 20, 30], ..., [0, 2], 30),
        ("31ms+1kf", [10, 20, 30], ..., [0, 1], 20),
        ("31ms+1kf", [10, 20, 30], ..., [0, 2], 30),
        ("9ms-1kf", [10, 20, 30], ..., [0, 1, 2], 10),
        ("10ms-1kf", [10, 20, 30], ..., [0, 1, 2], 10),
        ("11ms-1kf", [10, 20, 30], ..., [0, 1, 2], 10),
        ("19ms-1kf", [10, 20, 30], ..., [0, 1, 2], 10),
        ("20ms-1kf", [10, 20, 30], ..., [0, 1, 2], 10),
        ("21ms-1kf", [10, 20, 30], ..., [0, 1, 2], 20),
        ("31ms-1kf", [10, 20, 30], ..., [0, 1, 2], 30),
    ],
)
def test_frames(
    expr: str,
    frame_times: T.List[int],
    cur_frame_idx: T.Any,
    keyframe_indexes: T.List[int],
    expected_value: T.Union[int, T.Type[CommandError]],
) -> None:
    api = MagicMock()
    api.media.video.timecodes = frame_times
    api.media.video.keyframes = keyframe_indexes
    if cur_frame_idx is Ellipsis:
        api.media.current_pts = 0
    else:
        api.media.current_pts = frame_times[cur_frame_idx]
    pts = Pts(api, expr)

    _assert_pts_value(pts, expected_value)


@pytest.mark.parametrize(
    "expr,selection,expected_value",
    [
        ("a.s", (1, 2), 1),
        ("a.e", (1, 2), 2),
        ("a.s", None, CommandUnavailable),
        ("a.e", None, CommandUnavailable),
    ],
)
def test_audio_selection(
    expr: str,
    selection: T.Optional[T.Tuple[int, int]],
    expected_value: T.Union[int, T.Type[CommandError]],
) -> None:
    api = MagicMock()
    if selection:
        api.media.audio.has_selection = True
        api.media.audio.selection_start = selection[0]
        api.media.audio.selection_end = selection[1]
    else:
        api.media.audio.has_selection = False
        api.media.audio.selection_start = None
        api.media.audio.selection_end = None
    pts = Pts(api, expr)
    _assert_pts_value(pts, expected_value)


@pytest.mark.parametrize(
    "expr,view,expected_value", [("av.s", (1, 2), 1), ("av.e", (1, 2), 2)]
)
def test_audio_view(
    expr: str, view: T.Optional[T.Tuple[int, int]], expected_value: int
) -> None:
    api = MagicMock()
    api.media.audio.view_start = view[0]
    api.media.audio.view_end = view[1]
    pts = Pts(api, expr)
    _assert_pts_value(pts, expected_value)


def test_default_subtitle_duration() -> None:
    api = MagicMock()
    api.cfg.opt = {"subs": {"default_duration": 123}}
    pts = Pts(api, "dsd")

    _assert_pts_value(pts, 123)
