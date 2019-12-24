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

import threading
import typing as T

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

from bubblesub.api import Api
from bubblesub.api.log import LogApi
from bubblesub.api.threading import QueueWorker
from bubblesub.api.video import VideoApi, VideoState
from bubblesub.cache import load_cache, save_cache
from bubblesub.ui.audio.base import SLIDER_SIZE, BaseLocalAudioWidget
from bubblesub.util import chunks, sanitize_file_name

_CACHE_LOCK = threading.Lock()
BAND_Y_RESOLUTION = 30
CHUNK_SIZE = 50
VIDEO_BAND_SIZE = 10


class VideoBandWorkerSignals(QtCore.QObject):
    cache_updated = QtCore.pyqtSignal()


class VideoBandWorker(QueueWorker):
    def __init__(self, log_api: LogApi, video_api: VideoApi) -> None:
        super().__init__(log_api)
        self.signals = VideoBandWorkerSignals()
        self._video_api = video_api

        self._anything_to_save = False
        self._cache_name: T.Optional[str] = None
        self.cache: T.Dict[int, np.array] = {}

        video_api.state_changed.connect(self._on_video_state_change)

    def _process_task(self, task: T.Any) -> None:
        anything_changed = False
        for frame_idx in task:
            frame = self._video_api.get_frame(frame_idx, 1, BAND_Y_RESOLUTION)
            if frame is None:
                continue
            frame = frame.reshape(BAND_Y_RESOLUTION, 3)
            with _CACHE_LOCK:
                self.cache[frame_idx] = frame.copy()
                self._anything_to_save = True
            anything_changed = True
        if anything_changed:
            self.signals.cache_updated.emit()

    def _queue_cleared(self) -> None:
        with _CACHE_LOCK:
            self._save_to_cache()

    def _on_video_state_change(self, state: VideoState) -> None:
        if state == VideoState.NotLoaded:
            with _CACHE_LOCK:
                if self._anything_to_save:
                    self._save_to_cache()
                self.clear_tasks()
                self._cache_name = None
                self.cache = {}
            self.signals.cache_updated.emit()

        elif state == VideoState.Loading:
            with _CACHE_LOCK:
                assert self._video_api.path
                self._cache_name = (
                    sanitize_file_name(self._video_api.path) + "-video-band"
                )
                self.clear_tasks()
                self._anything_to_save = False
                self.cache = self._load_from_cache()
            self.signals.cache_updated.emit()

        elif state == VideoState.Loaded:
            with _CACHE_LOCK:
                not_cached_frames = [
                    frame_idx
                    for frame_idx in range(len(self._video_api.timecodes))
                    if frame_idx not in self.cache
                ]
                for chunk in chunks(not_cached_frames, CHUNK_SIZE):
                    self._queue.put(chunk)

    def _load_from_cache(self) -> T.Dict[int, np.array]:
        if self._cache_name is None:
            return {}
        cache = load_cache(self._cache_name) or {}
        cache = {
            key: value
            for key, value in cache.items()
            if np.count_nonzero(value)
        }
        return cache

    def _save_to_cache(self) -> None:
        if self._cache_name is not None:
            save_cache(self._cache_name, self.cache)


class VideoPreview(BaseLocalAudioWidget):
    def __init__(self, api: Api, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(api, parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )

        self._pixels: np.array = np.zeros([0, 0, 3], dtype=np.uint8)

        self._worker = VideoBandWorker(api.log, api.video)
        self._worker.signals.cache_updated.connect(self.repaint)
        self._api.threading.schedule_runnable(self._worker)

        api.video.state_changed.connect(self.repaint_if_needed)
        api.audio.view.view_changed.connect(self.repaint_if_needed)
        api.gui.terminated.connect(self.shutdown)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, VIDEO_BAND_SIZE)

    def _get_paint_cache_key(self) -> int:
        return hash(
            (
                # frame bitmaps
                self._api.video.state,
                # audio view
                self._api.audio.view.view_start,
                self._api.audio.view.view_end,
            )
        )

    def shutdown(self) -> None:
        self._worker.stop()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._pixels = np.zeros(
            [BAND_Y_RESOLUTION, self.width(), 3], dtype=np.uint8
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter()

        painter.begin(self)
        self._draw_video_band(painter)
        self._draw_frame(painter, bottom_line=False)
        painter.end()

    def _draw_video_band(self, painter: QtGui.QPainter) -> None:
        if not self._api.video.timecodes:
            return

        pixels = self._pixels.transpose(1, 0, 2)
        prev_column = np.zeros([pixels.shape[1], 3], dtype=np.uint8)

        min_pts = self.pts_from_x(0)
        max_pts = self.pts_from_x(self.width() - 1)

        pts_range = np.linspace(min_pts, max_pts, self.width())
        frame_idx_range = self._api.video.frame_idx_from_pts(pts_range)

        for x, frame_idx in enumerate(frame_idx_range):
            column = self._worker.cache.get(frame_idx, prev_column)
            pixels[x] = column
            prev_column = column

        image = QtGui.QImage(
            self._pixels.data,
            self._pixels.shape[1],
            self._pixels.shape[0],
            self._pixels.strides[0],
            QtGui.QImage.Format_RGB888,
        )
        painter.save()
        painter.scale(1, painter.viewport().height() / (BAND_Y_RESOLUTION - 1))
        painter.drawPixmap(0, 0, QtGui.QPixmap.fromImage(image))
        painter.restore()
