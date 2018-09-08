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

"""Hotkey config."""

import enum
import json
import typing as T

from bubblesub.opt.base import BaseConfig


class HotkeyContext(enum.Enum):
    """Which GUI widget the hotkey works in."""

    Global = 'global'
    Spectrogram = 'spectrogram'
    SubtitlesGrid = 'subtitles_grid'


class Hotkey:
    """Hotkey definition."""

    def __init__(
            self,
            shortcut: str,
            *invocations: T.Iterable[str],
    ) -> None:
        """
        Initialize self.

        :param shortcut: key combination that activates the hotkey
        :param invocations: invocations to execute
        """
        self.shortcut = shortcut
        self.invocations = invocations


_DEFAULT_GLOBAL_HOTKEYS = [
    Hotkey('Ctrl+Shift+N', '/new'),
    Hotkey('Ctrl+O', '/open'),
    Hotkey('Ctrl+S', '/save'),
    Hotkey('Ctrl+Shift+S', '/save-as'),
    Hotkey('Ctrl+Q', '/quit'),
    Hotkey('Ctrl+G', '/sub-select ask-number'),
    Hotkey('Ctrl+Shift+G', '/sub-select ask-time'),
    Hotkey('Alt+G', '/seek -d=ask'),
    Hotkey('Ctrl+K', '/sub-select one-above'),
    Hotkey('Ctrl+J', '/sub-select one-below'),
    Hotkey('Ctrl+A', '/sub-select all'),
    Hotkey('Ctrl+Shift+A', '/sub-select none'),
    Hotkey('Alt+2', '/play-audio-sel -de=+500ms --start'),
    Hotkey('Alt+1', '/play-audio-sel -ds=-500ms --start'),
    Hotkey('Alt+3', '/play-audio-sel -ds=-500ms --end'),
    Hotkey('Alt+4', '/play-audio-sel -de=+500ms --end'),
    Hotkey('Ctrl+R', '/play-audio-sel'),
    Hotkey('Ctrl+T', '/seek -d=cur-sub-start', '/pause off'),
    Hotkey('Ctrl+,', '/seek -d=-1f'),
    Hotkey('Ctrl+.', '/seek -d=+1f'),
    Hotkey('Ctrl+Shift+,', '/seek -d=-500ms'),
    Hotkey('Ctrl+Shift+.', '/seek -d=+500ms'),
    Hotkey('Ctrl+P', '/pause toggle'),
    Hotkey('Ctrl+Z', '/undo'),
    Hotkey('Ctrl+Y', '/redo'),
    Hotkey('Ctrl+F', '/search'),
    Hotkey('Ctrl+H', '/search-and-replace'),
    Hotkey('Ctrl+Return', '/sub-insert --before'),
    Hotkey('Ctrl+Delete', '/sub-delete'),
    Hotkey('Ctrl+Shift+1', '/audio-shift-sel -d=-10f --start'),
    Hotkey('Ctrl+Shift+2', '/audio-shift-sel -d=+10f --start'),
    Hotkey('Ctrl+Shift+3', '/audio-shift-sel -d=-10f --end'),
    Hotkey('Ctrl+Shift+4', '/audio-shift-sel -d=+10f --end'),
    Hotkey('Ctrl+1', '/audio-shift-sel -d=-1f --start'),
    Hotkey('Ctrl+2', '/audio-shift-sel -d=+1f --start'),
    Hotkey('Ctrl+3', '/audio-shift-sel -d=-1f --end'),
    Hotkey('Ctrl+4', '/audio-shift-sel -d=+1f --end'),
    Hotkey('Ctrl+B', '/audio-shift-sel -d=cur-frame --start'),
    Hotkey('Ctrl+M', '/audio-shift-sel -d=cur-frame --end'),
    Hotkey(
        'Ctrl+N',
        '/audio-shift-sel -d=cur-frame --both',
        '/audio-shift-sel -d=default-sub-duration --end'
    ),
    Hotkey('Ctrl+[', '/set-playback-speed {}/1.5'),
    Hotkey('Ctrl+]', '/set-playback-speed {}*1.5'),
    Hotkey('F3', '/search-repeat -d=below'),
    Hotkey('Shift+F3', '/search-repeat -d=above'),
    Hotkey('Alt+A', '/focus-widget spectrogram'),
    Hotkey('Alt+S', '/focus-widget subtitles-grid'),
    Hotkey('Alt+D', '/focus-widget text-editor -s'),
    Hotkey('Alt+Shift+D', '/focus-widget note-editor -s'),
    Hotkey('Alt+C', '/focus-widget console-input -s'),
    Hotkey('Alt+Shift+C', '/focus-widget console'),
    Hotkey('Alt+X', '/sub-split -p=cur-frame'),
    Hotkey('Alt+J', '/edit/join-subs-concatenate'),
    Hotkey('Alt+Up', '/edit/move-subs -d=above'),
    Hotkey('Alt+Down', '/edit/move-subs -d=below'),
    Hotkey('Alt+Return', '/file-properties'),
]

_DEFAULT_SPECTROGRAM_HOTKEYS = [
    Hotkey('Shift+1', '/audio-shift-sel -d=-10f --start'),
    Hotkey('Shift+2', '/audio-shift-sel -d=+10f --start'),
    Hotkey('Shift+3', '/audio-shift-sel -d=-10f --end'),
    Hotkey('Shift+4', '/audio-shift-sel -d=+10f --end'),
    Hotkey('1', '/audio-shift-sel -d=-1f --start'),
    Hotkey('2', '/audio-shift-sel -d=+1f --start'),
    Hotkey('3', '/audio-shift-sel -d=-1f --end'),
    Hotkey('4', '/audio-shift-sel -d=+1f --end'),
    Hotkey('C', '/audio-commit-sel'),
    Hotkey('K', '/sub-insert --before'),
    Hotkey('J', '/sub-insert --after'),
    Hotkey('R', '/play-audio-sel'),
    Hotkey('T', '/play-sub'),
    Hotkey('P', '/pause toggle'),
    Hotkey('Shift+K', '/sub-select one-above'),
    Hotkey('Shift+J', '/sub-select one-below'),
    Hotkey('A', '/audio-scroll -d=-0.05'),
    Hotkey('F', '/audio-scroll -d=0.05'),
    Hotkey('Ctrl+-', '/audio-zoom -d=1.1'),
    Hotkey('Ctrl+=', '/audio-zoom -d=0.9'),
    Hotkey('Ctrl++', '/audio-zoom -d=0.9'),
    Hotkey(',', '/seek -d=-1f'),
    Hotkey('.', '/seek -d=+1f'),
    Hotkey('Ctrl+Shift+,', '/seek -d=-1500ms'),
    Hotkey('Ctrl+Shift+.', '/seek -d=+1500ms'),
    Hotkey('Shift+,', '/seek -d=-500ms'),
    Hotkey('Shift+.', '/seek -d=+500ms'),
    Hotkey('B', '/audio-shift-sel -d=cur-frame --start'),
    Hotkey('M', '/audio-shift-sel -d=cur-frame --end'),
    Hotkey(
        'N',
        '/audio-shift-sel -d=cur-frame --both',
        '/audio-shift-sel -d=default-sub-duration --end'
    ),
    Hotkey('[', '/set-playback-speed {}/1.5'),
    Hotkey(']', '/set-playback-speed {}*1.5'),
    Hotkey('Alt+Left', '/audio-shift-sel -d=prev-sub-end --start'),
    Hotkey('Alt+Right', '/audio-shift-sel -d=next-sub-start --end'),
    Hotkey('Alt+Shift+Left', '/audio-shift-sel -d=-1kf --start'),
    Hotkey('Alt+Shift+Right', '/audio-shift-sel -d=+1kf --end'),
]

_DEFAULT_SUBTITLES_GRID_HOTKEYS = [
    Hotkey('Ctrl+C', '/sub-copy'),
    Hotkey('Ctrl+V', '/sub-paste --after'),
]


class HotkeysConfig(BaseConfig):
    """Configuration for global and widget-centric GUI hotkeys."""

    file_name = 'hotkeys.json'

    def __init__(self) -> None:
        """Initialize self."""
        self.hotkeys: T.Dict[HotkeyContext, T.List[Hotkey]] = {
            HotkeyContext.Global: _DEFAULT_GLOBAL_HOTKEYS,
            HotkeyContext.Spectrogram: _DEFAULT_SPECTROGRAM_HOTKEYS,
            HotkeyContext.SubtitlesGrid: _DEFAULT_SUBTITLES_GRID_HOTKEYS,
        }

    def loads(self, text: str) -> None:
        """
        Load internals from a human readable representation.

        :param text: JSON
        """
        obj = json.loads(text)
        for context in self.hotkeys:
            self.hotkeys[context].clear()
            for hotkey_obj in obj.get(context.value, []):
                self.hotkeys[context].append(
                    Hotkey(
                        hotkey_obj['shortcut'],
                        *hotkey_obj['invocations']
                    )
                )

    def dumps(self) -> str:
        """
        Serialize internals to a human readable representation.

        :return: JSON
        """
        return json.dumps(
            {
                context.value:
                [
                    {
                        'shortcut': hotkey.shortcut,
                        'invocations': hotkey.invocations,
                    }
                    for hotkey in hotkeys
                ]
                for context, hotkeys in self.__iter__()
            },
            indent=4
        )

    def __iter__(self) -> T.Iterator[T.Tuple[HotkeyContext, T.List[Hotkey]]]:
        """
        Let users iterate directly over this config.

        :return: iterator
        """
        return iter(self.hotkeys.items())
