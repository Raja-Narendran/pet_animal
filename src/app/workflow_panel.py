"""Persistent linear workflow editor; drafts survive Manager/core refreshes."""
import copy
import re
import sqlite3
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QFrame,
    QLabel, QLineEdit, QPlainTextEdit, QCheckBox, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QDoubleSpinBox, QFileDialog, QMessageBox, QAbstractItemView, QSplitter, QGridLayout, QBoxLayout)
from ..core.workflows import STEP_LABELS
from ..core.shortcuts import APPLICATION_NAMES
from ..services.windows_launcher import WindowsLauncher

ICONS = {'application': '▣', 'url': '↗', 'folder': '▤', 'file': '▧', 'wait': '◷', 'message': '☏'}
COLORS = {'running': '#3368A0', 'success': '#23835B', 'failed': '#D54848', 'cancelled': '#A46D1B'}


def text_label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def action(text, callback):
    button = QPushButton(text)
    button.setMinimumHeight(36)
    button.clicked.connect(callback)
    return button


class WorkflowPanel(QWidget):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager, self.core, self.controller = manager, manager.core, manager.controller
        self.routine_id = None
        self.steps = []
        self.dirty = False
        self.loading = False
        self.result = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = text_label('Workflows')
        title.setObjectName('heading')
        root.addWidget(title)
        root.addWidget(text_label('Build your routine once. Start it with a phrase or the Run button.'))
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter = splitter
        self.compact = None
        root.addWidget(splitter, 1)
        library = QWidget()
        self.library = library
        lib = QVBoxLayout(library)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search routines')
        self.search.textChanged.connect(self.refresh_library)
        lib.addWidget(self.search)
        self.routines = QListWidget()
        self.routines.currentItemChanged.connect(self.select_routine)
        lib.addWidget(self.routines, 1)
        self.new_button = action('New routine', lambda: self.new_draft())
        self.template_button = action('Start Work template', self.template)
        self.duplicate_button = action('Duplicate', self.duplicate)
        self.delete_button = action('Delete', self.delete)
        self.toggle_button = action('Enable / Disable', self.toggle)
        self.library_actions = (self.new_button, self.template_button, self.duplicate_button, self.delete_button, self.toggle_button)
        self.library_buttons = QGridLayout()
        for i, button in enumerate(self.library_actions):
            self.library_buttons.addWidget(button, i, 0)
        lib.addLayout(self.library_buttons)
        splitter.addWidget(library)
        right = QWidget()
        layout = QVBoxLayout(right)
        bar = QHBoxLayout()
        self.save_button = action('Save', self.save)
        self.run_button = action('▶ Run', self.run)
        self.stop_button = action('■ Stop', self.controller.stop_routine)
        for button in (self.save_button, self.run_button, self.stop_button):
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)
        self.editor = QWidget()
        edit = QVBoxLayout(self.editor)
        edit.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setMaxLength(150)
        self.name.setPlaceholderText('Routine name')
        self.phrases = QPlainTextEdit()
        self.phrases.setMaximumHeight(72)
        self.phrases.setPlaceholderText('Trigger phrases, one per line\nstart work')
        self.enabled = QCheckBox('Enabled')
        form.addRow('Name', self.name)
        form.addRow('Phrases', self.phrases)
        form.addRow('', self.enabled)
        edit.addLayout(form)
        body = QHBoxLayout()
        self.body_layout = body
        canvas = QFrame()
        canvas.setObjectName('card')
        flow = QVBoxLayout(canvas)
        trigger = text_label('◉  Trigger phrase\n↓')
        trigger.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flow.addWidget(trigger)
        self.canvas = QListWidget()
        self.canvas.setMinimumHeight(280)
        self.canvas.setWordWrap(True)
        self.canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.canvas.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.canvas.currentRowChanged.connect(self.select_step)
        self.canvas.model().rowsMoved.connect(self.reordered)
        flow.addWidget(self.canvas, 1)
        done = text_label('↓\n◎  Done')
        done.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flow.addWidget(done)
        controls = QHBoxLayout()
        self.add_type = QComboBox()
        for kind, label in STEP_LABELS.items():
            self.add_type.addItem(label, kind)
        controls.addWidget(self.add_type)
        controls.addWidget(action('+ Add Step', self.add_step))
        flow.addLayout(controls)
        move = QHBoxLayout()
        move.addWidget(action('Move Up', lambda: self.move_step(-1)))
        move.addWidget(action('Move Down', lambda: self.move_step(1)))
        move.addWidget(action('Remove', self.remove_step))
        flow.addLayout(move)
        body.addWidget(canvas, 3)
        self.settings = QFrame()
        self.settings.setObjectName('card')
        self.step_form = QFormLayout(self.settings)
        self.step_form.addRow(text_label('Step settings'))
        self.type = QComboBox()
        for kind, label in STEP_LABELS.items():
            self.type.addItem(label, kind)
        self.application = QComboBox()
        self.value = QLineEdit()
        self.browse = action('Choose folder…', self.choose_path)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0, 90)
        self.seconds.setDecimals(2)
        self.seconds.setSuffix(' seconds')
        self.step_form.addRow('Action', self.type)
        self.step_form.addRow('Application', self.application)
        self.step_form.addRow('Target / message', self.value)
        self.url_hint = text_label('Enter a website such as example.com or https://example.com. HTTPS is used automatically.')
        self.step_form.addRow(self.url_hint)
        self.file_hint = text_label('Opens with the default Windows app for this file.')
        self.step_form.addRow(self.file_hint)
        self.step_form.addRow(self.browse)
        self.step_form.addRow('Wait', self.seconds)
        body.addWidget(self.settings, 2)
        edit.addLayout(body, 1)
        layout.addWidget(self.editor, 1)
        self.notice = text_label('Create a routine or choose one from the list.')
        layout.insertWidget(1, self.notice)
        self.progress = text_label('')
        layout.addWidget(self.progress)
        splitter.addWidget(right)
        splitter.setSizes([220, 700])
        self.name.textChanged.connect(self.mark_dirty)
        self.phrases.textChanged.connect(self.mark_dirty)
        self.enabled.toggled.connect(self.mark_dirty)
        self.type.currentIndexChanged.connect(self.change_type)
        self.application.currentIndexChanged.connect(self.change_value)
        self.value.textChanged.connect(self.change_value)
        self.seconds.valueChanged.connect(self.change_value)
        self.controller.workflow_updated.connect(self.update_progress)
        self.new_draft(initial=True)

    def set_compact(self, compact):
        if self.compact == compact:
            return
        self.compact = compact
        self.splitter.setOrientation(Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.body_layout.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)
        self.library.setMaximumHeight(320 if compact else 16777215)
        self.routines.setMaximumHeight(90 if compact else 16777215)
        self.routines.setMinimumHeight(70 if compact else 0)
        self.settings.setMaximumHeight(220 if compact else 16777215)
        for button in self.library_actions:
            self.library_buttons.removeWidget(button)
        for i, button in enumerate(self.library_actions):
            self.library_buttons.addWidget(button, i // 2 if compact else i, i % 2 if compact else 0)
        self.splitter.setSizes([280, 800] if compact else [210, 680])

    def show_notice(self, message, *, error=False):
        self.notice.setText(message)
        self.notice.setStyleSheet('color: ' + COLORS['failed'] + '; font-weight: 600;' if error else '')
        if error:
            self.manager.content_scroll.ensureWidgetVisible(self.notice)

    def mark_dirty(self, *_):
        if not self.loading:
            self.dirty = True
            self.show_notice('Unsaved changes. Save before running.')
            self.update_controls()

    def refresh(self):
        self.refresh_library()
        self.refresh_applications()
        self.update_controls()

    def refresh_library(self, *_):
        query = self.search.text().casefold()
        self.routines.blockSignals(True)
        self.routines.clear()
        for routine in self.core.workflows.list():
            if query not in routine['name'].casefold():
                continue
            item = QListWidgetItem(routine['name'] + '\n' + ('Enabled' if routine['enabled'] else 'Disabled') + ' · ' + routine['last_result'])
            item.setData(Qt.ItemDataRole.UserRole, routine['id'])
            if routine['issues']:
                item.setToolTip(routine['issues'])
                item.setText(item.text() + '\n⚠ Needs review')
            self.routines.addItem(item)
            if routine['id'] == self.routine_id:
                self.routines.setCurrentItem(item)
        self.routines.blockSignals(False)

    def refresh_applications(self):
        self.application.blockSignals(True)
        step = self.selected_step()
        selected = step['value'] if step and step['type'] == 'application' else None
        self.application.clear()
        for key in sorted(WindowsLauncher.SUPPORTED_APPS):
            self.application.addItem(APPLICATION_NAMES.get(key, key), key)
        for app in self.core.list_registered_applications():
            if app.enabled and not app.needs_repair:
                self.application.addItem(app.name, app.id)
        if selected is not None:
            index = self.application.findData(selected)
            if index < 0:
                self.application.addItem('Unavailable — choose a replacement', selected)
                index = self.application.count() - 1
            self.application.setCurrentIndex(index)
        self.application.blockSignals(False)

    def can_leave(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, 'Unsaved routine', 'Save changes to this routine?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        self.dirty = False
        if self.routine_id and self.core.workflows.get(self.routine_id):
            self.open_routine(self.routine_id)
        else:
            self.new_draft(initial=True)
        return True

    def new_draft(self, draft=None, initial=False):
        if not initial and not self.can_leave():
            return
        self.loading = True
        draft = draft or dict(name='', phrases=[], steps=[], enabled=True)
        self.routine_id = None
        self.result = None
        self.name.setText(draft['name'])
        self.phrases.setPlainText('\n'.join(draft['phrases']))
        self.enabled.setChecked(bool(draft['enabled']))
        self.steps = copy.deepcopy(draft['steps'])
        self.loading = False
        self.dirty = bool(draft['name'] or self.steps)
        self.render_canvas()
        self.refresh()
        self.progress.setText('')
        self.show_notice('Choose steps, add your phrases, then save to approve this routine.')

    def template(self):
        self.new_draft(dict(name='Start Work', phrases=['start work'], enabled=True, steps=[
            dict(type='application', value='vscode'), dict(type='application', value='chrome'),
            dict(type='url', value=''), dict(type='folder', value=''),
            dict(type='wait', value=2), dict(type='message', value='Ready!')]))

    def select_routine(self, item, previous=None):
        if item is None:
            return
        routine_id = item.data(Qt.ItemDataRole.UserRole)
        if routine_id == self.routine_id:
            return
        if not self.can_leave():
            self.refresh_library()
            return
        self.open_routine(routine_id)

    def open_routine(self, routine_id):
        routine = self.core.workflows.get(routine_id)
        if routine is None:
            return
        self.loading = True
        self.routine_id = routine_id
        self.name.setText(routine['name'])
        self.phrases.setPlainText('\n'.join(routine['phrases']))
        self.enabled.setChecked(bool(routine['enabled']))
        self.steps = copy.deepcopy(routine['steps'])
        self.loading = False
        self.dirty = False
        last = self.controller.last_workflow_result
        self.result = last if last and last.routine_id == routine_id else None
        self.render_canvas()
        self.show_notice(routine['issues'] or 'Saved. Run this routine or use its trigger phrase.')
        self.progress.setText(self.result.message if self.result else '')
        self.refresh()

    def selected_step(self):
        row = self.canvas.currentRow()
        return self.steps[row] if 0 <= row < len(self.steps) else None

    def render_canvas(self, selected=0):
        self.canvas.blockSignals(True)
        self.canvas.clear()
        for i, step in enumerate(self.steps):
            value = step['value']
            if step['type'] == 'application':
                app = self.core.get_registered_application(value)
                value = app.name if app else APPLICATION_NAMES.get(value, value)
            if step['type'] == 'wait':
                value = str(value) + ' seconds'
            status = self.result.steps[i].status if self.result and i < len(self.result.steps) else 'pending'
            item = QListWidgetItem(f"{ICONS[step['type']]}  {i + 1}. {STEP_LABELS[step['type']]}  ·  {status}\n{str(value)[:90] or 'Choose a target'}" + ('\n                 ↓' if i < len(self.steps) - 1 else ''))
            item.setData(Qt.ItemDataRole.UserRole, copy.deepcopy(step))
            if status in COLORS:
                item.setForeground(QColor(COLORS[status]))
            self.canvas.addItem(item)
        self.canvas.setCurrentRow(min(selected, len(self.steps) - 1))
        self.canvas.blockSignals(False)
        self.select_step(self.canvas.currentRow())

    def select_step(self, row):
        step = self.selected_step()
        self.settings.setEnabled(step is not None)
        if step is None:
            return
        self.loading = True
        self.type.setCurrentIndex(self.type.findData(step['type']))
        self.refresh_applications()
        self.value.setMaxLength(100 if step['type'] == 'message' else 2048)
        self.value.setText(str(step['value']) if step['type'] in ('url', 'folder', 'file', 'message') else '')
        self.seconds.setValue(float(step['value']) if step['type'] == 'wait' else 0)
        for widget, visible in ((self.application, step['type'] == 'application'), (self.value, step['type'] in ('url', 'folder', 'file', 'message')),
                                (self.browse, step['type'] in ('folder', 'file')), (self.seconds, step['type'] == 'wait')):
            widget.setVisible(visible)
        for widget in (self.application, self.value, self.seconds):
            label = self.step_form.labelForField(widget)
            if label:
                label.setVisible(widget.isVisibleTo(self.settings))
        self.url_hint.setVisible(step['type'] == 'url')
        self.file_hint.setVisible(step['type'] == 'file')
        self.browse.setText('Choose file…' if step['type'] == 'file' else 'Choose folder…')
        self.value.setPlaceholderText({'url': 'https://dev.azure.com/your-organization', 'folder': 'Choose a local folder', 'file': 'Choose a local file', 'message': 'Ready!'}.get(step['type'], ''))
        self.loading = False

    def change_type(self, *_):
        step = self.selected_step()
        if self.loading or step is None:
            return
        kind = self.type.currentData()
        step.update(type=kind, value=0 if kind == 'wait' else ('notepad' if kind == 'application' else ''))
        self.mark_dirty()
        self.result = None
        self.render_canvas(self.canvas.currentRow())

    def change_value(self, *_):
        step = self.selected_step()
        if self.loading or step is None:
            return
        step['value'] = self.application.currentData() if step['type'] == 'application' else (self.seconds.value() if step['type'] == 'wait' else self.value.text())
        self.result = None
        row = self.canvas.currentRow()
        self.canvas.item(row).setData(Qt.ItemDataRole.UserRole, copy.deepcopy(step))
        self.canvas.item(row).setText(f"{ICONS[step['type']]}  {row + 1}. {STEP_LABELS[step['type']]}\n{step['value']}" + ('\n                 ↓' if row < len(self.steps) - 1 else ''))
        self.mark_dirty()

    def choose_path(self):
        step = self.selected_step()
        if step is None:
            return
        if step['type'] == 'file':
            path, _ = QFileDialog.getOpenFileName(self, 'Choose a file to open with its default app', '', 'All files (*)')
        else:
            path = QFileDialog.getExistingDirectory(self, 'Choose a local project folder')
        if path:
            self.value.setText(path)

    def add_step(self):
        if len(self.steps) >= 50:
            self.show_notice('A routine supports at most 50 steps.')
            return
        kind = self.add_type.currentData()
        self.steps.append(dict(type=kind, value=0 if kind == 'wait' else ('notepad' if kind == 'application' else '')))
        self.result = None
        self.mark_dirty()
        self.render_canvas(len(self.steps) - 1)

    def remove_step(self):
        row = self.canvas.currentRow()
        if row >= 0:
            self.steps.pop(row)
            self.result = None
            self.mark_dirty()
            self.render_canvas(row)

    def move_step(self, offset):
        row = self.canvas.currentRow()
        target = row + offset
        if 0 <= row < len(self.steps) and 0 <= target < len(self.steps):
            self.steps[row], self.steps[target] = self.steps[target], self.steps[row]
            self.result = None
            self.mark_dirty()
            self.render_canvas(target)

    def reordered(self, *_):
        self.steps = [copy.deepcopy(self.canvas.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.canvas.count())]
        self.result = None
        self.mark_dirty()
        self.render_canvas(self.canvas.currentRow())

    def save(self):
        # Normalize ordinary website entry only at the editor boundary. The core,
        # imports, restores and launcher still require validated HTTPS URLs.
        steps = copy.deepcopy(self.steps)
        for step in steps:
            if step['type'] == 'url' and isinstance(step['value'], str):
                address = step['value'].strip()
                if '://' not in address and re.match(r'^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z0-9-]+(?=[:/?#]|$)', address):
                    address = 'https://' + address
                step['value'] = address
        try:
            result = self.core.workflows.save(self.name.text(), [p.strip() for p in self.phrases.toPlainText().splitlines() if p.strip()],
                steps, self.enabled.isChecked(), self.routine_id)
        except (ValueError, OSError) as error:
            self.show_notice(str(error), error=True)
            return False
        except sqlite3.Error as error:
            busy = any(word in str(error).lower() for word in ('locked', 'busy'))
            self.show_notice('The local database is busy. Close any other Pet Animal instance and try Save again.' if busy
                             else 'This routine could not be saved to local storage. Your changes are still in the editor.', error=True)
            return False
        self.routine_id = result
        self.dirty = False
        self.steps = copy.deepcopy(self.core.workflows.get(result)['steps'])
        self.render_canvas(self.canvas.currentRow())
        self.show_notice('Saved. These steps are approved for this routine.')
        self.refresh()
        return True

    def duplicate(self):
        if self.routine_id:
            self.new_draft(self.core.workflows.duplicate(self.routine_id))

    def delete(self):
        if not self.routine_id or not self.can_leave():
            return
        if QMessageBox.question(self, 'Delete routine', 'Delete this routine and its trigger phrases?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.manager.guard(lambda: self.core.workflows.delete(self.routine_id))
            self.new_draft(initial=True)

    def toggle(self):
        if self.routine_id and self.can_leave():
            try:
                self.core.workflows.set_enabled(self.routine_id, not self.enabled.isChecked())
            except ValueError as error:
                self.show_notice(str(error))
                return
            self.open_routine(self.routine_id)

    def run(self):
        if not self.routine_id or self.dirty:
            self.show_notice('Save this routine before running it.')
            return
        result = self.controller.start_routine(self.routine_id)
        self.controller._show_result(result)
        self.show_notice(result['message'])

    def update_progress(self, result):
        self.update_controls()
        if result.routine_id == self.routine_id:
            self.result = result
            self.render_canvas(self.canvas.currentRow())
            statuses = ' · '.join(f'{s.position + 1}: {s.status}' for s in result.steps)
            self.progress.setText((result.message or 'Running ' + result.name + '…') + '\n' + statuses)
        self.refresh_library()

    def update_controls(self):
        active = self.core.workflows.active
        own_running = bool(active and active.result.routine_id == self.routine_id)
        self.editor.setEnabled(not own_running)
        self.save_button.setEnabled(not own_running)
        self.run_button.setEnabled(bool(self.routine_id and not self.dirty and self.enabled.isChecked() and not active))
        self.stop_button.setEnabled(active is not None)
        for button in (self.delete_button, self.toggle_button):
            button.setEnabled(bool(self.routine_id and not own_running))
        self.duplicate_button.setEnabled(bool(self.routine_id))
