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

# pylint: disable=no-member

import io
import locale
from typing import Any, Optional

import mpv
from ass_parser import write_ass
from mpv import MPV, MpvRenderContext, OpenGlCbGetProcAddrFn
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtOpenGL import QGLContext
from PyQt5.QtWidgets import QOpenGLWidget, QWidget

from bubblesub.api import Api
from bubblesub.api.audio_stream import AudioStream
from bubblesub.api.playback import PlaybackFrontendState
from bubblesub.api.video_stream import VideoStream
from bubblesub.errors import ResourceUnavailable
from bubblesub.util import ms_to_str


def get_proc_addr(_: Any, name: bytes) -> int:
    glctx = QGLContext.currentContext()
    if glctx is None:
        return None
    addr = int(glctx.getProcAddress(name.decode("utf-8")))
    return addr


class MpvWidget(QOpenGLWidget):
    _schedule_update = pyqtSignal()

    def __init__(self, api: Api, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._api = api

        locale.setlocale(locale.LC_NUMERIC, "C")

        self._destroyed = False
        self._need_subs_refresh = False

        self.mpv = MPV(ytdl=False, loglevel="info", log_handler=print)
        self.mpv_gl = None
        self.get_proc_addr_c = OpenGlCbGetProcAddrFn(get_proc_addr)
        self.frameSwapped.connect(
            self.swapped, Qt.ConnectionType.DirectConnection
        )

        for key, value in {
            # "config": False,
            "quiet": False,
            "msg-level": "all=info",
            "osc": False,
            "osd-bar": False,
            "input-cursor": False,
            "input-vo-keyboard": False,
            "input-default-bindings": False,
            "ytdl": False,
            "sub-auto": False,
            "audio-file-auto": False,
            "vo": "null" if api.args.no_video else "libmpv",
            "hwdec": "no",
            "pause": True,
            "idle": True,
            "blend-subtitles": "video",
            "video-sync": "display-vdrop",
            "keepaspect": True,
            "stop-playback-on-init-failure": False,
            "keep-open": True,
            "track-auto-selection": False,
        }.items():
            setattr(self.mpv, key, value)

        self._opengl = None

        self._timer = QTimer(parent=None)
        self._timer.setInterval(api.cfg.opt["video"]["subs_sync_interval"])
        self._timer.timeout.connect(self._refresh_subs_if_needed)

        api.subs.loaded.connect(self._on_subs_load)
        api.video.stream_created.connect(self._on_video_state_change)
        api.video.stream_unloaded.connect(self._on_video_state_change)
        api.video.current_stream_switched.connect(self._on_video_state_change)
        api.audio.stream_created.connect(self._on_audio_state_change)
        api.audio.stream_unloaded.connect(self._on_audio_state_change)
        api.audio.current_stream_switched.connect(self._on_audio_state_change)
        api.playback.request_seek.connect(
            self._on_request_seek, Qt.ConnectionType.DirectConnection
        )
        api.playback.request_playback.connect(self._on_request_playback)
        api.playback.playback_speed_changed.connect(
            self._on_playback_speed_change
        )
        api.playback.volume_changed.connect(self._on_volume_change)
        api.playback.mute_changed.connect(self._on_mute_change)
        api.playback.pause_changed.connect(self._on_pause_change)
        api.video.view.zoom_changed.connect(self._on_video_zoom_change)
        api.video.view.pan_changed.connect(self._on_video_pan_change)
        api.gui.terminated.connect(self.shutdown)
        self._schedule_update.connect(self.update)

        self.mpv.observe_property("time-pos", self._on_mpv_time_pos_change)
        self.mpv.observe_property("track-list", self._on_mpv_track_list_change)
        self.mpv.observe_property("pause", self._on_mpv_pause_change)

        self._timer.start()

    def initializeGL(self) -> None:
        self.mpv_gl = MpvRenderContext(
            self.mpv,
            "opengl",
            opengl_init_params={"get_proc_address": self.get_proc_addr_c},
        )
        self.mpv_gl.update_cb = self.on_update

    def paintGL(self) -> None:
        if self.mpv_gl:
            ratio = self.devicePixelRatioF()
            w = int(self.width() * ratio)
            h = int(self.height() * ratio)
            self.mpv_gl.render(
                flip_y=True,
                opengl_fbo={
                    "fbo": self.defaultFramebufferObject(),
                    "w": w,
                    "h": h,
                },
            )

    @pyqtSlot()
    def maybe_update(self) -> None:
        if self._destroyed:
            return
        if self.window().isMinimized():
            self.makeCurrent()
            self.paintGL()
            self.context().swapBuffers(self.context().surface())
            self.swapped()
            self.doneCurrent()
        else:
            self.update()

    def on_update(self) -> None:
        self._schedule_update.emit()

    def on_update_fake(self) -> None:
        pass

    def swapped(self) -> None:
        if self.mpv_gl:
            self.mpv_gl.report_swap()

    def closeEvent(self, _: Any) -> None:
        self.makeCurrent()
        if self.mpv_gl:
            self.mpv_gl.update_cb = self.on_update_fake
            self.mpv_gl.free()

    def _on_subs_load(self) -> None:
        self._api.subs.script_info.changed.subscribe(
            lambda _event: self._on_subs_change()
        )
        self._api.subs.events.changed.subscribe(
            lambda _event: self._on_subs_change()
        )
        self._api.subs.styles.changed.subscribe(
            lambda _event: self._on_subs_change()
        )

    def _on_video_state_change(self, stream: VideoStream) -> None:
        self._sync_media()
        self._need_subs_refresh = True

    def _on_audio_state_change(self, stream: AudioStream) -> None:
        self._sync_media()

    def _sync_media(self) -> None:
        self.mpv.pause = True
        self.mpv.loadfile("null://")
        external_files: set[str] = set()
        for video_stream in self._api.video.streams:
            external_files.add(str(video_stream.path))
        for audio_stream in self._api.audio.streams:
            external_files.add(str(audio_stream.path))
        self.mpv.external_files = list(external_files)
        if not external_files:
            self._api.playback.state = PlaybackFrontendState.NOT_READY
        else:
            self._api.playback.state = PlaybackFrontendState.LOADING

    def shutdown(self) -> None:
        self._destroyed = True
        self.makeCurrent()
        if self._opengl:
            self._opengl.set_update_callback(lambda: None)
            self._opengl.close()
        self.deleteLater()
        self._timer.stop()

    def _refresh_subs_if_needed(self) -> None:
        if self._need_subs_refresh:
            self._refresh_subs()

    def _refresh_subs(self) -> None:
        if not self._api.playback.is_ready:
            return
        if self.mpv.sub:
            try:
                self.mpv.command("sub_remove")
            except mpv.MPVError:
                pass
        with io.StringIO() as handle:
            write_ass(self._api.subs.ass_file, handle)
            self.mpv.command("sub_add", "memory://" + handle.getvalue())
        self._need_subs_refresh = False

    def _set_end(self, end: Optional[int]) -> None:
        if not self._api.playback.is_ready:
            return
        if end is None:
            ret = "none"
        else:
            end = max(0, end - 1)
            ret = ms_to_str(end)
        if self.mpv.end != ret:
            self.mpv.end = ret

    def _on_request_seek(self, pts: int, precise: bool) -> None:
        self._set_end(None)  # mpv refuses to seek beyond --end
        self.mpv.seek(ms_to_str(pts), "absolute", "exact")

    def _on_request_playback(
        self, start: Optional[int], end: Optional[int]
    ) -> None:
        if start is not None:
            self.mpv.seek(ms_to_str(start), "absolute")
        self._set_end(end)
        self.mpv.pause = False

    def _on_playback_speed_change(self) -> None:
        self.mpv.speed = float(self._api.playback.playback_speed)

    def _on_volume_change(self) -> None:
        self.mpv.volume = float(self._api.playback.volume)

    def _on_mute_change(self) -> None:
        self.mpv.mute = self._api.playback.is_muted

    def _on_pause_change(self, is_paused: bool) -> None:
        self._set_end(None)
        self.mpv.pause = is_paused

    def _on_video_zoom_change(self) -> None:
        # ignore errors coming from setting extreme values
        try:
            self.mpv.video_zoom = float(self._api.video.view.zoom)
        except mpv.MPVError:
            pass

    def _on_video_pan_change(self) -> None:
        # ignore errors coming from setting extreme values
        try:
            self.mpv.video_pan_x = float(self._api.video.view.pan_x)
            self.mpv.video_pan_y = float(self._api.video.view.pan_y)
        except mpv.MPVError:
            pass

    def _on_subs_change(self) -> None:
        self._need_subs_refresh = True

    def _on_mpv_unload(self) -> None:
        self._api.playback.state = PlaybackFrontendState.NOT_READY

    def _on_mpv_load(self) -> None:
        self._api.playback.state = PlaybackFrontendState.READY
        self._need_subs_refresh = True

    def _on_track_list_ready(self, track_list: Any) -> None:
        # self._api.log.debug(json.dumps(track_list, indent=4))
        vid: Optional[int] = None
        aid: Optional[int] = None

        current_audio_stream: Optional[AudioStream]
        try:
            current_audio_stream = self._api.audio.current_stream
        except ResourceUnavailable:
            current_audio_stream = None

        current_video_stream: Optional[VideoStream]
        try:
            current_video_stream = self._api.video.current_stream
        except ResourceUnavailable:
            current_video_stream = None

        for track in track_list:
            track_type = track["type"]
            track_path = track.get("external-filename")

            if (
                track_type == "video"
                and current_video_stream
                and current_video_stream.path.samefile(track_path)
            ):
                vid = track["id"]

            if (
                track_type == "audio"
                and current_audio_stream
                and current_audio_stream.path.samefile(track_path)
            ):
                aid = track["id"]

        if self.mpv.vid != vid:
            self.mpv.vid = vid if vid is not None else "no"
            self._api.log.debug(f"playback: changing vid to {vid}")

        if self.mpv.aid != aid:
            self.mpv.aid = aid if aid is not None else "no"
            self._api.log.debug(f"playback: changing aid to {aid}")

        delay = (
            current_audio_stream.delay if current_audio_stream else 0
        ) / 1000.0
        if self.mpv.audio_delay != delay:
            self.mpv.audio_delay = delay

        if vid is not None or aid is not None:
            self._api.playback.state = PlaybackFrontendState.READY
        else:
            self._api.playback.state = PlaybackFrontendState.NOT_READY

    def _on_mpv_time_pos_change(self, prop_name: str, new_value: Any) -> None:
        pts = round((new_value or 0) * 1000)
        self._api.playback.receive_current_pts_change.emit(pts)

    def _on_mpv_pause_change(self, prop_name: str, new_value: Any) -> None:
        self._api.playback.pause_changed.disconnect(self._on_pause_change)
        self._api.playback.is_paused = new_value
        self._api.playback.pause_changed.connect(self._on_pause_change)

    def _on_mpv_track_list_change(
        self, prop_name: str, new_value: Any
    ) -> None:
        self._on_track_list_ready(new_value)
