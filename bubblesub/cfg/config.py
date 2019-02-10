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

"""Program configuration."""

import typing as T
from pathlib import Path

import xdg

from bubblesub.cfg.hotkeys import HotkeysConfig
from bubblesub.cfg.menu import MenuConfig
from bubblesub.cfg.options import OptionsConfig
from bubblesub.data import ROOT_DIR


class Config:
    """Umbrella class containing all the configuration."""

    DEFAULT_PATH = Path(xdg.XDG_CONFIG_HOME) / "bubblesub"

    def __init__(self) -> None:
        """Initialize self."""
        self.opt = OptionsConfig()
        self.hotkeys = HotkeysConfig()
        self.menu = MenuConfig()
        self.root_dir = Path()

    def reset(self) -> None:
        """Reset configuration to factory defaults."""
        self.opt.reset()
        self.hotkeys.reset()
        self.menu.reset()

    def load(self, root_dir: Path) -> None:
        """
        Load configuration from the specified path.

        :param root_dir: root directory to load the configuration from
        """
        self.root_dir = root_dir
        self.opt.load(root_dir)
        self.hotkeys.load(root_dir)
        self.menu.load(root_dir)

    def save(self, root_dir: Path) -> None:
        """
        Save configuration to the specified path.

        :param root_dir: root directory to save the configuration to
        """
        self.opt.save(root_dir)
        self.hotkeys.create_example_file(root_dir)
        self.menu.create_example_file(root_dir)

    def get_assets(self, directory_name: str) -> T.Iterable[Path]:
        """
        Get path to all static assets under given directory name.

        :param directory_name: directory that contains relevant assets
        :return: list of paths found in the user and built-in asset directories
        """
        for path in [ROOT_DIR, self.root_dir]:
            if path is None:
                continue

            path /= directory_name
            if path.exists():
                yield from path.iterdir()