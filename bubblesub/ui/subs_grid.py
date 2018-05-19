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

import functools
import re
import typing as T

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import bubblesub.api
import bubblesub.ui.util
from bubblesub.opt.hotkeys import HotkeyContext
from bubblesub.opt.menu import MenuContext
from bubblesub.ui.model.subs import SubtitlesModel, SubtitlesModelColumn
from bubblesub.ui.util import get_color

# ????
MAGIC_MARGIN = 2
HIGHLIGHTABLE_CHUNKS = {'\N{FULLWIDTH ASTERISK}', '\\N', '\\h', '\\n'}


class SubsGridDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(
            self,
            api: bubblesub.api.Api,
            parent: QtWidgets.QWidget = None
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._format = self._create_format()

    def on_palette_change(self) -> None:
        self._format = self._create_format()

    def _create_format(self) -> QtGui.QTextCharFormat:
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(get_color(self._api, 'grid/ass-mark'))
        return fmt

    def paint(
            self,
            painter: QtGui.QPainter,
            option: QtWidgets.QStyleOptionViewItem,
            index: QtCore.QModelIndex
    ) -> None:
        model = self.parent().model()
        text = self._process_text(model.data(index, QtCore.Qt.DisplayRole))
        alignment = model.data(index, QtCore.Qt.TextAlignmentRole)
        background = model.data(index, QtCore.Qt.BackgroundRole)

        painter.save()
        if option.state & QtWidgets.QStyle.State_Selected:
            self._paint_selected(painter, option, text, alignment)
        else:
            self._paint_regular(painter, option, text, alignment, background)
        painter.restore()

    def _process_text(self, text: str) -> str:
        return re.sub('{[^}]+}', '\N{FULLWIDTH ASTERISK}', text)

    def _paint_selected(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        text: str,
        alignment: int
    ) -> None:
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(option.palette.color(QtGui.QPalette.Highlight))
        painter.drawRect(option.rect)

        painter.setPen(option.palette.color(QtGui.QPalette.HighlightedText))
        painter.drawText(option.rect, alignment, text)

    def _paint_regular(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        text: str,
        alignment: int,
        background: QtGui.QColor
    ) -> None:
        if not isinstance(background, QtCore.QVariant):
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QBrush(background))
            painter.drawRect(option.rect)

        rect = option.rect
        metrics = painter.fontMetrics()
        regex = '({})'.format('|'.join(
            re.escape(sep) for sep in HIGHLIGHTABLE_CHUNKS
        ))

        for chunk in re.split(regex, text):
            painter.setPen(
                get_color(self._api, 'grid/ass-mark')
                if chunk in HIGHLIGHTABLE_CHUNKS else
                option.palette.color(QtGui.QPalette.Text)
            )

            # chunk = metrics.elidedText(
            #     chunk, QtCore.Qt.ElideRight, rect.width()
            # )

            painter.drawText(rect, alignment, chunk)
            rect = rect.adjusted(metrics.width(chunk), 0, 0, 0)


class SubsGrid(QtWidgets.QTableView):
    def __init__(
            self,
            api: bubblesub.api.Api,
            parent: QtWidgets.QWidget = None
    ) -> None:
        super().__init__(parent)
        self._api = api
        self.setModel(SubtitlesModel(self, api))
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setTabKeyNavigation(False)
        self.horizontalHeader().setSectionsMovable(True)
        self.verticalHeader().setDefaultSectionSize(
            self.fontMetrics().height() + MAGIC_MARGIN
        )

        self._subs_grid_delegate = SubsGridDelegate(self._api, self)
        for column_idx in {
                SubtitlesModelColumn.Text,
                SubtitlesModelColumn.Note
        }:
            self.setItemDelegateForColumn(column_idx, self._subs_grid_delegate)
            self.horizontalHeader().setSectionResizeMode(
                column_idx, QtWidgets.QHeaderView.Stretch
            )

        api.subs.loaded.connect(self._on_subs_load)
        api.subs.selection_changed.connect(self._on_api_selection_change)
        self.selectionModel().selectionChanged.connect(
            self._widget_selection_changed
        )

        self._setup_subtitles_menu()
        self._setup_header_menu()

    def _setup_subtitles_menu(self) -> None:
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_subtitles_menu)
        self.subtitles_menu = QtWidgets.QMenu(self)
        bubblesub.ui.util.setup_cmd_menu(
            self._api,
            self.subtitles_menu,
            self._api.opt.menu[MenuContext.SubtitlesGrid],
            HotkeyContext.SubtitlesGrid
        )

    def _setup_header_menu(self) -> None:
        header = self.horizontalHeader()
        header.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        for column in SubtitlesModelColumn:
            action = QtWidgets.QAction(self)
            action.setCheckable(True)
            action.setData(column)
            action.setChecked(not self.isColumnHidden(column))
            action.changed.connect(
                functools.partial(self.toggle_column, action)
            )
            action.setText(column.name)
            header.addAction(action)

    def toggle_column(self, action: QtWidgets.QAction) -> None:
        column: SubtitlesModelColumn = action.data()
        self.horizontalHeader().setSectionHidden(
            column.value,
            not action.isChecked()
        )

    def restore_grid_columns(self) -> None:
        header = self.horizontalHeader()
        data = self._api.opt.general.gui.grid_columns
        if data:
            header.restoreState(data)
        for action in header.actions():
            column: SubtitlesModelColumn = action.data()
            action.setChecked(not header.isSectionHidden(column.value))

    def store_grid_columns(self) -> None:
        self._api.opt.general.gui.grid_columns = (
            self.horizontalHeader().saveState()
        )

    def keyboardSearch(self, _text: str) -> None:
        pass

    def changeEvent(self, _event: QtCore.QEvent) -> None:
        self._subs_grid_delegate.on_palette_change()

    def _open_subtitles_menu(self, position: QtCore.QPoint) -> None:
        self.subtitles_menu.exec_(self.viewport().mapToGlobal(position))

    def _collect_rows(self) -> T.List[int]:
        rows = set()
        for index in self.selectionModel().selectedIndexes():
            rows.add(index.row())
        return list(rows)

    def _on_subs_load(self) -> None:
        self.scrollTo(
            self.model().index(0, 0),
            self.EnsureVisible | self.PositionAtTop
        )

    def _widget_selection_changed(
            self,
            _selected: T.List[int],
            _deselected: T.List[int]
    ) -> None:
        if self._collect_rows() != self._api.subs.selected_indexes:
            self._api.subs.selection_changed.disconnect(
                self._on_api_selection_change
            )
            self._api.subs.selected_indexes = self._collect_rows()
            self._api.subs.selection_changed.connect(
                self._on_api_selection_change
            )

    def _on_api_selection_change(
            self,
            _rows: T.List[int],
            _changed: bool
    ) -> None:
        if self._collect_rows() == self._api.subs.selected_indexes:
            return

        self.setUpdatesEnabled(False)

        self.selectionModel().selectionChanged.disconnect(
            self._widget_selection_changed
        )

        selection = QtCore.QItemSelection()
        for row in self._api.subs.selected_indexes:
            idx = self.model().index(row, 0)
            selection.select(idx, idx)

        self.selectionModel().clear()

        if self._api.subs.selected_indexes:
            first_row = self._api.subs.selected_indexes[0]
            cell_index = self.model().index(first_row, 0)
            self.setCurrentIndex(cell_index)
            self.scrollTo(cell_index)

        self.selectionModel().select(
            selection,
            QtCore.QItemSelectionModel.Rows |
            QtCore.QItemSelectionModel.Current |
            QtCore.QItemSelectionModel.Select
        )

        self.selectionModel().selectionChanged.connect(
            self._widget_selection_changed
        )

        self.setUpdatesEnabled(True)
