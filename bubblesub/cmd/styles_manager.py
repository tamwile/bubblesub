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

from copy import copy
from fractions import Fraction
from typing import Optional, cast

import PIL.Image
import PIL.ImageQt
from ass_parser import (
    AssEvent,
    AssEventList,
    AssScriptInfo,
    AssStyle,
    AssStyleList,
)
from PyQt5.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QImage, QMouseEvent, QPixmap, QResizeEvent
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListView,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bubblesub.api import Api
from bubblesub.api.cmd import BaseCommand
from bubblesub.ass_renderer import AssRenderer
from bubblesub.errors import ResourceUnavailable
from bubblesub.ui.assets import get_assets
from bubblesub.ui.font_combo_box import FontComboBox, refresh_font_db
from bubblesub.ui.model.styles import AssStylesModel, AssStylesModelColumn
from bubblesub.ui.util import (
    ColorPicker,
    Dialog,
    ImmediateDataWidgetMapper,
    async_dialog_exec,
    async_slot,
    get_text_edit_row_height,
    show_prompt,
)


class _StylePreview(QGroupBox):
    preview_text_changed = pyqtSignal([])

    def __init__(
        self,
        api: Api,
        model: AssStylesModel,
        selection_model: QItemSelectionModel,
        parent: QWidget,
    ) -> None:
        super().__init__("Preview", parent)
        self._api = api
        self._selection_model = selection_model

        self._renderer = AssRenderer()

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(api.cfg.opt["styles"]["preview_test_text"])
        self._editor.setFixedWidth(400)
        self._editor.setTabChangesFocus(True)
        self._editor.setFixedHeight(get_text_edit_row_height(self._editor, 2))

        self._background_combobox = QComboBox()
        for i, path in enumerate(get_assets("style_preview_bk")):
            self._background_combobox.addItem(path.name, path.resolve())
            if path.name == api.cfg.opt["styles"]["preview_background"]:
                self._background_combobox.setCurrentIndex(i)

        self._preview_box = QLabel(self)
        self._preview_box.setLineWidth(1)
        self._preview_box.setFrameShape(QFrame.StyledPanel)
        self._preview_box.setFrameShadow(QFrame.Sunken)
        self._preview_box.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Ignored
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self._editor)
        layout.addWidget(self._background_combobox)
        layout.addWidget(self._preview_box)

        self.update_preview()
        self._editor.textChanged.connect(self._on_text_change)
        self._background_combobox.currentIndexChanged.connect(
            self._on_background_change
        )

        model.dataChanged.connect(self.update_preview)
        model.rowsInserted.connect(self.update_preview)
        model.rowsRemoved.connect(self.update_preview)
        selection_model.selectionChanged.connect(self.update_preview)

    def _on_background_change(self) -> None:
        self.update_preview()
        self._api.cfg.opt["styles"][
            "preview_background"
        ] = self._background_combobox.currentData().name

    def _on_text_change(self) -> None:
        self.preview_text_changed.emit()
        self.update_preview()
        self._api.cfg.opt["styles"]["preview_test_text"] = self.preview_text

    @property
    def preview_text(self) -> str:
        return self._editor.toPlainText()

    @property
    def _selected_style(self) -> Optional[AssStyle]:
        try:
            idx = self._selection_model.selectedIndexes()[0].row()
        except IndexError:
            return None
        else:
            return self._api.subs.styles[idx]

    def update_preview(self) -> None:
        selected_style = self._selected_style
        if not selected_style:
            self._preview_box.clear()
            return

        resolution = (self._preview_box.width(), self._preview_box.height())
        if resolution[0] <= 0 or resolution[1] <= 0:
            self._preview_box.clear()
            return

        fake_style = copy(selected_style)
        fake_style.name = "Default"
        if (
            self._api.video.has_current_stream
            and self._api.video.current_stream.is_ready
        ):
            fake_style.scale(
                resolution[1] / self._api.video.current_stream.height
            )
        fake_style_list = AssStyleList()
        fake_style_list.append(fake_style)

        fake_event = AssEvent(
            start=0,
            end=1000,
            text=self.preview_text.replace("\n", "\\N"),
            style_name=fake_style.name,
        )
        fake_event_list = AssEventList()
        fake_event_list.append(fake_event)

        fake_script_info = AssScriptInfo()

        image = PIL.Image.new(mode="RGBA", size=resolution)

        background_path = self._background_combobox.currentData()
        if background_path and background_path.exists():
            background = PIL.Image.open(background_path)
            for y in range(0, resolution[1], background.height):
                for x in range(0, resolution[0], background.width):
                    image.paste(background, (x, y))

        self._renderer.set_source(
            fake_style_list, fake_event_list, fake_script_info, resolution
        )
        try:
            aspect_ratio = self._api.video.current_stream.aspect_ratio
        except ResourceUnavailable:
            aspect_ratio = Fraction(1)
        subs_image = self._renderer.render(
            time=0,
            aspect_ratio=aspect_ratio,
        )
        image = PIL.Image.composite(subs_image, image, subs_image)

        image = PIL.ImageQt.ImageQt(image)
        image = QImage(image)
        self._preview_box.setPixmap(QPixmap.fromImage(image))


class _StyleList(QWidget):
    def __init__(
        self,
        api: Api,
        model: AssStylesModel,
        selection_model: QItemSelectionModel,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._model = model
        selection_model.selectionChanged.connect(self._on_selection_change)

        self._styles_list_view = QListView(self)
        self._styles_list_view.setModel(model)
        self._styles_list_view.setSelectionModel(selection_model)

        self._add_button = QPushButton("Add", self)
        self._add_button.clicked.connect(self._on_add_button_click)
        self._remove_button = QPushButton("Remove", self)
        self._remove_button.setEnabled(False)
        self._remove_button.clicked.connect(self._on_remove_button_click)
        self._duplicate_button = QPushButton("Duplicate", self)
        self._duplicate_button.setEnabled(False)
        self._duplicate_button.clicked.connect(self._on_duplicate_button_click)
        self._move_up_button = QPushButton("Move up", self)
        self._move_up_button.setEnabled(False)
        self._move_up_button.clicked.connect(self._on_move_up_button_click)
        self._move_down_button = QPushButton("Move down", self)
        self._move_down_button.setEnabled(False)
        self._move_down_button.clicked.connect(self._on_move_down_button_click)
        self._rename_button = QPushButton("Rename", self)
        self._rename_button.setEnabled(False)
        self._rename_button.clicked.connect(self._on_rename_button_click)

        strip = QWidget(self)
        strip_layout = QGridLayout(strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.addWidget(self._add_button, 0, 0)
        strip_layout.addWidget(self._remove_button, 0, 1)
        strip_layout.addWidget(self._duplicate_button, 0, 2)
        strip_layout.addWidget(self._move_up_button, 1, 0)
        strip_layout.addWidget(self._move_down_button, 1, 1)
        strip_layout.addWidget(self._rename_button, 1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._styles_list_view)
        layout.addWidget(strip)

    @property
    def _selected_style(self) -> Optional[AssStyle]:
        selected_row = self._selected_row
        if selected_row is None:
            return None
        return self._api.subs.styles[selected_row]

    @property
    def _selected_row(self) -> Optional[int]:
        indexes = self._styles_list_view.selectedIndexes()
        if not indexes:
            return None
        return cast(int, indexes[0].row())

    def _on_selection_change(
        self,
        selected: QItemSelection,
        _deselected: QItemSelection,
    ) -> None:
        anything_selected = len(selected.indexes()) > 0
        self._remove_button.setEnabled(anything_selected)
        self._rename_button.setEnabled(anything_selected)
        self._duplicate_button.setEnabled(anything_selected)
        self._move_up_button.setEnabled(
            anything_selected and selected.indexes()[0].row() > 0
        )
        self._move_down_button.setEnabled(
            anything_selected
            and selected.indexes()[0].row() < len(self._api.subs.styles) - 1
        )

    @async_slot()
    async def _on_add_button_click(self) -> None:
        style_name = await self._prompt_for_unique_style_name()
        if not style_name:
            return

        style = AssStyle(name=style_name)
        self._api.subs.styles.append(style)
        idx = style.index

        self._styles_list_view.selectionModel().select(
            self._model.index(idx, 0),
            QItemSelectionModel.SelectionFlag(
                QItemSelectionModel.SelectionFlag.Clear
                | QItemSelectionModel.SelectionFlag.Select
            ),
        )

    async def _prompt_for_unique_style_name(
        self, style_name: str = ""
    ) -> Optional[str]:
        prompt_text = "Name of the new style:"
        while True:
            dialog = QInputDialog(self)
            dialog.setLabelText(prompt_text)
            dialog.setTextValue(style_name)
            dialog.setInputMode(QInputDialog.TextInput)
            if not await async_dialog_exec(dialog):
                return None
            style_name = dialog.textValue()

            exists = False
            for style in self._api.subs.styles:
                if style.name == style_name:
                    exists = True

            if not exists:
                return style_name

            prompt_text = '"{}" already exists. Choose different name:'.format(
                style_name
            )

    @async_slot()
    async def _on_remove_button_click(self) -> None:
        style = self._selected_style
        assert style is not None
        idx = style.index

        if not await show_prompt(
            f'Are you sure you want to remove style "{style.name}"?', self
        ):
            return

        self._styles_list_view.selectionModel().clear()
        with self._api.undo.capture():
            del self._api.subs.styles[idx]

    def _on_duplicate_button_click(self, event: QMouseEvent) -> None:
        style = self._selected_style
        assert style is not None
        idx = style.index

        style_copy = copy(style)
        style_copy.name += " (copy)"
        with self._api.undo.capture():
            self._api.subs.styles.insert(idx + 1, style_copy)
        self._styles_list_view.selectionModel().select(
            self._model.index(idx + 1, 0),
            QItemSelectionModel.SelectionFlag(
                QItemSelectionModel.SelectionFlag.Clear
                | QItemSelectionModel.SelectionFlag.Select
            ),
        )

    def _on_move_up_button_click(self, event: QMouseEvent) -> None:
        style = self._selected_style
        assert style is not None
        idx = style.index

        with self._api.undo.capture():
            self._api.subs.styles[idx : idx + 1] = []
            self._api.subs.styles[idx - 1 : idx - 1] = [style]
        self._styles_list_view.selectionModel().select(
            self._model.index(idx - 1, 0),
            QItemSelectionModel.SelectionFlag(
                QItemSelectionModel.SelectionFlag.Clear
                | QItemSelectionModel.SelectionFlag.Select
            ),
        )

    def _on_move_down_button_click(self, event: QMouseEvent) -> None:
        style = self._selected_style
        assert style is not None
        idx = style.index

        with self._api.undo.capture():
            self._api.subs.styles[idx : idx + 1] = []
            self._api.subs.styles[idx + 1 : idx + 1] = [style]
        self._styles_list_view.selectionModel().select(
            self._model.index(idx + 1, 0),
            QItemSelectionModel.SelectionFlag(
                QItemSelectionModel.SelectionFlag.Clear
                | QItemSelectionModel.SelectionFlag.Select
            ),
        )

    @async_slot()
    async def _on_rename_button_click(self) -> None:
        style = self._selected_style
        assert style is not None
        idx = style.index

        old_name = style.name
        new_name = await self._prompt_for_unique_style_name(old_name)
        if not new_name:
            return

        with self._api.undo.capture():
            style.name = new_name
            for line in self._api.subs.events:
                if line.style_name == old_name:
                    line.style_name = new_name

        self._styles_list_view.selectionModel().select(
            self._model.index(idx, 0), QItemSelectionModel.SelectionFlag.Select
        )


class _FontGroupBox(QGroupBox):
    def __init__(
        self,
        api: Api,
        parent: QWidget,
        mapper: ImmediateDataWidgetMapper,
    ) -> None:
        super().__init__("Font", parent)

        if api.cfg.opt["gui"]["try_to_refresh_fonts"]:
            refresh_font_db()

        self.font_name_edit = FontComboBox(api, self)
        self.font_size_edit = QSpinBox(self)
        self.font_size_edit.setMinimum(0)
        self.font_size_edit.setMaximum(999)
        self.bold_checkbox = QCheckBox("Bold", self)
        self.italic_checkbox = QCheckBox("Italic", self)
        self.underline_checkbox = QCheckBox("Underline", self)
        self.strike_out_checkbox = QCheckBox("Strike-out", self)

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Name:", self), 0, 0)
        layout.addWidget(self.font_name_edit, 0, 1, 1, 2)
        layout.addWidget(QLabel("Size:", self), 1, 0)
        layout.addWidget(self.font_size_edit, 1, 1, 1, 2)
        layout.addWidget(QLabel("Style:", self), 2, 0)
        layout.addWidget(self.bold_checkbox, 2, 1)
        layout.addWidget(self.italic_checkbox, 3, 1)
        layout.addWidget(self.underline_checkbox, 2, 2)
        layout.addWidget(self.strike_out_checkbox, 3, 2)

        mapper.add_mapping(self.font_name_edit, AssStylesModelColumn.FONT_NAME)
        mapper.add_mapping(self.font_size_edit, AssStylesModelColumn.FONT_SIZE)
        mapper.add_mapping(self.bold_checkbox, AssStylesModelColumn.BOLD)
        mapper.add_mapping(self.italic_checkbox, AssStylesModelColumn.ITALIC)
        mapper.add_mapping(
            self.underline_checkbox, AssStylesModelColumn.UNDERLINE
        )
        mapper.add_mapping(
            self.strike_out_checkbox, AssStylesModelColumn.STRIKE_OUT
        )


class _AlignmentGroupBox(QGroupBox):
    changed = pyqtSignal()

    def __init__(
        self, parent: QWidget, mapper: ImmediateDataWidgetMapper
    ) -> None:
        super().__init__("Alignment", parent)
        self.radio_buttons = {
            x: QRadioButton(
                [
                    "\N{SOUTH WEST ARROW}",
                    "\N{DOWNWARDS ARROW}",
                    "\N{SOUTH EAST ARROW}",
                    "\N{LEFTWARDS ARROW}",
                    "\N{BLACK DIAMOND}",
                    "\N{RIGHTWARDS ARROW}",
                    "\N{NORTH WEST ARROW}",
                    "\N{UPWARDS ARROW}",
                    "\N{NORTH EAST ARROW}",
                ][x - 1],
                self,
            )
            for x in range(1, 10)
        }
        layout = QGridLayout(self)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.addWidget(self.radio_buttons[7], 0, 0)
        layout.addWidget(self.radio_buttons[8], 0, 1)
        layout.addWidget(self.radio_buttons[9], 0, 2)
        layout.addWidget(self.radio_buttons[4], 1, 0)
        layout.addWidget(self.radio_buttons[5], 1, 1)
        layout.addWidget(self.radio_buttons[6], 1, 2)
        layout.addWidget(self.radio_buttons[1], 2, 0)
        layout.addWidget(self.radio_buttons[2], 2, 1)
        layout.addWidget(self.radio_buttons[3], 2, 2)

        for radio_button in self.radio_buttons.values():
            radio_button.toggled.connect(lambda _event: self.changed.emit())

        mapper.add_mapping(self, AssStylesModelColumn.ALIGNMENT)

    def get_value(self) -> int:
        for idx, radio_button in self.radio_buttons.items():
            if radio_button.isChecked():
                return idx
        return -1

    def set_value(self, value: int) -> None:
        if value in self.radio_buttons:
            self.radio_buttons[value].setChecked(True)

    value = pyqtProperty(int, get_value, set_value, user=True)


class _ColorsGroupBox(QGroupBox):
    def __init__(
        self, parent: QWidget, mapper: ImmediateDataWidgetMapper
    ) -> None:
        super().__init__("Colors", parent)
        self.primary_color_button = ColorPicker(self)
        self.secondary_color_button = ColorPicker(self)
        self.outline_color_button = ColorPicker(self)
        self.back_color_button = ColorPicker(self)

        layout = QGridLayout(self)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        layout.addWidget(QLabel("Primary:", self), 0, 0)
        layout.addWidget(self.primary_color_button, 0, 1)
        layout.addWidget(QLabel("Secondary:", self), 1, 0)
        layout.addWidget(self.secondary_color_button, 1, 1)
        layout.addWidget(QLabel("Outline:", self), 2, 0)
        layout.addWidget(self.outline_color_button, 2, 1)
        layout.addWidget(QLabel("Shadow:", self), 3, 0)
        layout.addWidget(self.back_color_button, 3, 1)

        mapper.add_mapping(
            self.primary_color_button, AssStylesModelColumn.PRIMARY_COLOR
        )
        mapper.add_mapping(
            self.secondary_color_button, AssStylesModelColumn.SECONDARY_COLOR
        )
        mapper.add_mapping(
            self.back_color_button, AssStylesModelColumn.BACK_COLOR
        )
        mapper.add_mapping(
            self.outline_color_button, AssStylesModelColumn.OUTLINE_COLOR
        )


class _OutlineGroupBox(QGroupBox):
    def __init__(
        self, parent: QWidget, mapper: ImmediateDataWidgetMapper
    ) -> None:
        super().__init__("Outline", parent)
        self.outline_width_edit = QDoubleSpinBox(self)
        self.outline_width_edit.setMinimum(0)
        self.outline_width_edit.setMaximum(999)
        self.shadow_width_edit = QDoubleSpinBox(self)
        self.shadow_width_edit.setMinimum(0)
        self.shadow_width_edit.setMaximum(999)

        layout = QGridLayout(self)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        layout.addWidget(QLabel("Outline:", self), 0, 0)
        layout.addWidget(self.outline_width_edit, 0, 1)
        layout.addWidget(QLabel("Shadow:", self), 1, 0)
        layout.addWidget(self.shadow_width_edit, 1, 1)

        mapper.add_mapping(
            self.shadow_width_edit, AssStylesModelColumn.SHADOW_WIDTH
        )
        mapper.add_mapping(
            self.outline_width_edit, AssStylesModelColumn.OUTLINE_WIDTH
        )


class _MarginGroupBox(QGroupBox):
    def __init__(
        self, parent: QWidget, mapper: ImmediateDataWidgetMapper
    ) -> None:
        super().__init__("Margins", parent)
        self.margin_left_edit = QSpinBox(self)
        self.margin_left_edit.setMinimum(0)
        self.margin_left_edit.setMaximum(999)
        self.margin_right_edit = QSpinBox(self)
        self.margin_right_edit.setMinimum(0)
        self.margin_right_edit.setMaximum(999)
        self.margin_vertical_edit = QSpinBox(self)
        self.margin_vertical_edit.setMinimum(0)
        self.margin_vertical_edit.setMaximum(999)

        layout = QGridLayout(self)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        layout.addWidget(QLabel("Left:", self), 0, 0)
        layout.addWidget(self.margin_left_edit, 0, 1)
        layout.addWidget(QLabel("Right:", self), 1, 0)
        layout.addWidget(self.margin_right_edit, 1, 1)
        layout.addWidget(QLabel("Vertical:", self), 2, 0)
        layout.addWidget(self.margin_vertical_edit, 2, 1)

        mapper.add_mapping(
            self.margin_left_edit, AssStylesModelColumn.MARGIN_LEFT
        )
        mapper.add_mapping(
            self.margin_right_edit, AssStylesModelColumn.MARGIN_RIGHT
        )
        mapper.add_mapping(
            self.margin_vertical_edit, AssStylesModelColumn.MARGIN_VERTICAL
        )


class _MiscGroupBox(QGroupBox):
    def __init__(
        self, parent: QWidget, mapper: ImmediateDataWidgetMapper
    ) -> None:
        super().__init__("Transformations", parent)
        self.scale_x_edit = QDoubleSpinBox(self)
        self.scale_x_edit.setMinimum(0)
        self.scale_x_edit.setMaximum(999)
        self.scale_y_edit = QDoubleSpinBox(self)
        self.scale_y_edit.setMinimum(0)
        self.scale_y_edit.setMaximum(999)
        self.angle_edit = QDoubleSpinBox(self)
        self.angle_edit.setMinimum(0)
        self.angle_edit.setMaximum(999)
        self.spacing_edit = QDoubleSpinBox(self)
        self.spacing_edit.setMinimum(0)
        self.spacing_edit.setMaximum(999)

        layout = QGridLayout(self)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        layout.addWidget(QLabel("Scale X:", self), 0, 0)
        layout.addWidget(self.scale_x_edit, 0, 1)
        layout.addWidget(QLabel("Scale Y:", self), 1, 0)
        layout.addWidget(self.scale_y_edit, 1, 1)
        layout.addWidget(QLabel("Angle:", self), 2, 0)
        layout.addWidget(self.angle_edit, 2, 1)
        layout.addWidget(QLabel("Spacing:", self), 3, 0)
        layout.addWidget(self.spacing_edit, 3, 1)

        mapper.add_mapping(self.scale_x_edit, AssStylesModelColumn.SCALE_X)
        mapper.add_mapping(self.scale_y_edit, AssStylesModelColumn.SCALE_Y)
        mapper.add_mapping(self.angle_edit, AssStylesModelColumn.ANGLE)
        mapper.add_mapping(self.spacing_edit, AssStylesModelColumn.SPACING)


class _StyleEditor(QWidget):
    def __init__(
        self,
        api: Api,
        model: AssStylesModel,
        selection_model: QItemSelectionModel,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._mapper = ImmediateDataWidgetMapper(
            model, {_AlignmentGroupBox: "changed"}
        )
        selection_model.selectionChanged.connect(self._on_selection_change)

        self.font_group_box = _FontGroupBox(api, self, self._mapper)
        self.colors_group_box = _ColorsGroupBox(self, self._mapper)
        self.outline_group_box = _OutlineGroupBox(self, self._mapper)
        self.misc_group_box = _MiscGroupBox(self, self._mapper)
        self.margins_group_box = _MarginGroupBox(self, self._mapper)
        self.alignment_group_box = _AlignmentGroupBox(self, self._mapper)

        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.font_group_box)
        left_layout.addWidget(self.colors_group_box)
        left_layout.addWidget(self.outline_group_box)

        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.misc_group_box)
        right_layout.addWidget(self.margins_group_box)
        right_layout.addWidget(self.alignment_group_box)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(left_widget)
        layout.addWidget(right_widget)

    def _on_selection_change(
        self,
        selected: QItemSelection,
        _deselected: QItemSelection,
    ) -> None:
        if len(selected.indexes()) == 1:
            self.setEnabled(True)
            self._mapper.set_current_index(selected.indexes()[0].row())
        else:
            self.setEnabled(False)
            self._mapper.set_current_index(None)


class _StylesManagerDialog(Dialog):
    def __init__(self, api: Api, main_window: QMainWindow) -> None:
        super().__init__(main_window)
        model = AssStylesModel(self, api.subs.styles)
        selection_model = QItemSelectionModel(model)

        self._style_list = _StyleList(api, model, selection_model, self)
        self._style_editor = _StyleEditor(api, model, selection_model, self)
        self._style_editor.setEnabled(False)
        self._preview_box = _StylePreview(api, model, selection_model, self)
        self._preview_box.preview_text_changed.connect(self._sync_preview_text)

        layout = QHBoxLayout(self)
        layout.addWidget(self._style_list)
        layout.addWidget(self._style_editor)
        layout.addWidget(self._preview_box)

        self.setWindowTitle("Styles manager")

        self._sync_preview_text()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._preview_box.update_preview()

    def _sync_preview_text(self) -> None:
        self._style_editor.font_group_box.font_name_edit.set_sample_text(
            self._preview_box.preview_text
        )


class ManageStylesCommand(BaseCommand):
    names = ["manage-styles", "styles-manager", "style-manager"]
    help_text = "Opens up the style manager."

    @property
    def is_enabled(self) -> bool:
        return True

    async def run(self) -> None:
        await self.api.gui.exec(self._run_with_gui)

    async def _run_with_gui(self, main_window: QMainWindow) -> None:
        with self.api.undo.capture():
            dialog = _StylesManagerDialog(self.api, main_window)
            await async_dialog_exec(dialog)


COMMANDS = [ManageStylesCommand]
