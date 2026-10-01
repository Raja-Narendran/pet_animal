"""Native Manager with six pages, shared services, and Figma-inspired tokens."""
import json
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QListWidget, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QComboBox, QDialog, QFormLayout,
    QLayout, QDialogButtonBox, QTextEdit, QCheckBox, QFileDialog,
    QMessageBox, QInputDialog, QProgressBar, QSlider)
from ..core.application import DEFAULT_PET, identifier
from ..config.settings import settings
from .software_discovery import SoftwareDiscoveryState, SoftwareDiscoveryPanel


PALETTES = {
    'light': dict(background='#F7F9FC', surface='#FFFFFF', text='#1F2937', muted='#64748B', border='#E2E8F0', selection='#D1D5DB'),
    'dark': dict(background='#111827', surface='#1F2937', text='#F7F9FC', muted='#A6B5C9', border='#374151', selection='#4B5563'),
}
PAGES = ['Dashboard', 'Memory', 'Commands', 'Pet Studio', 'Activity', 'Settings']


def label(value, role=''):
    item = QLabel(value)
    item.setWordWrap(True)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(role)
    return item


def button(title, callback, primary=False, icon=None):
    item = QPushButton(title)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setMinimumHeight(40)
    item.setObjectName('primary' if primary else '')
    if icon:
        icon_path = settings.BASE_DIR / 'assets/ui' / (icon + ('-white' if primary and (settings.BASE_DIR / 'assets/ui' / f'{icon}-white.svg').exists() else '') + '.svg')
        item.setIcon(QIcon(str(icon_path)))
        item.setIconSize(QSize(16, 16))
    item.clicked.connect(callback)
    return item


class ManagerWindow(QMainWindow):
    def __init__(self, core, controller):
        super().__init__()
        self.core, self.controller = core, controller
        self.software_state = SoftwareDiscoveryState(self)
        self.setWindowTitle('Pet Animal Manager')
        self.resize(1200, 900)
        self.setMinimumSize(850, 650)
        self.page = core.app_settings()['page']
        self.memory_query = ''
        self.memory_category = None
        self.activity_status = self.activity_date = ''
        self.activity_command = None
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(20, 28, 20, 20)
        nav.addWidget(label('PET ANIMAL', 'brand'))
        nav.addWidget(label('Your desktop companion', 'muted'))
        nav.addSpacing(28)
        self.navigation = QListWidget()
        self.navigation.addItems(PAGES)
        self.navigation.currentRowChanged.connect(self.navigate)
        nav.addWidget(self.navigation)
        nav.addWidget(button('Open floating pet', self.controller.show_pet, True))
        shell.addWidget(sidebar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(36, 32, 36, 36)
        self.content_layout.setSpacing(20)
        self.content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(self.content)
        shell.addWidget(scroll, 1)
        self.core.listeners.append(self.refresh)
        self.navigation.setCurrentRow(PAGES.index(self.page))

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if not self.controller.pet.isVisible() and not self.controller.pet.tray_icon.isVisible():
            self.controller.quit()

    def navigate(self, index):
        if index < 0:
            return
        self.page = PAGES[index]
        config = self.core.app_settings()
        config['page'] = self.page
        self.core.save_settings(config)

    def refresh(self):
        palette = PALETTES[self.core.app_settings()['theme']]
        self.setStyleSheet('''
            QWidget {background: %(background)s; color: %(text)s; font-family: 'Segoe UI'; font-size: 13px;}
            QFrame#sidebar, QFrame#card {background: %(surface)s; border: 1px solid %(border)s; border-radius: 16px;}
            QFrame#sidebar {border-radius:0;}
            QFrame#card QLabel, QFrame#sidebar QLabel {background: transparent;}
            QLabel#brand {font-size:20px; font-weight:700; color:#3368A0;}
            QLabel#heading {font-size:28px; font-weight:700;}
            QLabel#subheading {font-size:17px; font-weight:600;}
            QLabel#metric {font-size:30px; font-weight:700;}
            QLabel#muted {color:%(muted)s; font-size:12px;}
            QPushButton {background:%(surface)s; border:1px solid %(border)s; border-radius:10px; padding:10px 14px; font-weight:600;}
            QPushButton:hover {border-color:#66A3BF;}
            QPushButton#primary {background:#3368A0; color:white; border-color:#3368A0;}
            QLineEdit,QTextEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:%(surface)s; border:1px solid %(border)s; border-radius:8px; padding:8px;}
            QListWidget {background:transparent; border:0; outline:0;}
            QListWidget::item {padding:14px; border-radius:10px; margin-bottom:6px;}
            QListWidget::item:selected {background:#3368A0; color:white;}
            QTableWidget {background:%(surface)s; border:1px solid %(border)s; border-radius:12px; gridline-color:%(border)s; outline:0; selection-background-color:%(selection)s; selection-color:%(text)s;}
            QTableWidget::item:selected, QTableWidget::item:selected:!active {background:%(selection)s; color:%(text)s;}
            QHeaderView::section {background:%(background)s; color:%(muted)s; border:0; padding:12px; font-weight:600;}
            QProgressBar {background:%(background)s; border:0; border-radius:3px; height:6px;}
            QProgressBar::chunk {background:#3368A0; border-radius:3px;}
            QSlider {background: transparent;}
            QSlider::groove:horizontal {height: 6px; background: %(border)s; border-radius: 3px;}
            QSlider::sub-page:horizontal {background: #3368A0; border-radius: 3px;}
            QSlider::handle:horizontal {background: #3368A0; border: 2px solid %(surface)s; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;}
            QSlider::handle:horizontal:hover {background: #66A3BF;}
        ''' % palette)
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        getattr(self, 'page_' + self.page.lower().replace(' ', '_'))()
        self.content_layout.addStretch()

    def heading(self, title, subtitle, actions=()):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        copy = QVBoxLayout()
        copy.addWidget(label(title, 'heading'))
        copy.addWidget(label(subtitle, 'muted'))
        row.addLayout(copy, 1)
        for action in actions:
            row.addWidget(action)
        self.content_layout.addWidget(widget)

    def card(self, title=None):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        if title:
            layout.addWidget(label(title, 'subheading'))
        return frame, layout

    def guard(self, callback):
        try:
            return callback()
        except Exception as error:
            QMessageBox.warning(self, 'Unable to complete action', str(error))

    def confirm(self, title, message, callback):
        if QMessageBox.question(self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.guard(callback)

    def table(self, headers, rows):
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                table.setItem(index, column, item)
            table.setRowHeight(index, 48)
        table.setMinimumHeight(min(420, max(160, 52 * (len(rows) + 1))))
        return table

    def page_dashboard(self):
        memory = self.core.get_memory_by_key('user.name')
        greeting = 'Welcome back' + (', ' + memory['memory_value'] if memory and not memory['sensitive'] else '')
        self.heading(greeting, 'A little companion. A more personal workspace.', [
            button('Add memory', self.edit_memory, icon='brain'),
            button('New command', self.edit_command, True, 'zap')])
        stats = self.core.stats()
        metrics = QWidget()
        row = QHBoxLayout(metrics)
        row.setContentsMargins(0, 0, 0, 0)
        for title, value, subtitle in [('Memory items', stats['memories'], 'Saved on this PC'), ('Registered commands', stats['commands'], 'Phrases you control'), ('Executed today', stats['today'], 'From command history')]:
            frame, layout = self.card()
            layout.addWidget(label(title, 'muted'))
            layout.addWidget(label(str(value), 'metric'))
            layout.addWidget(label(subtitle, 'muted'))
            row.addWidget(frame)
        self.content_layout.addWidget(metrics)
        frame, layout = self.card('Active companion')
        profile = self.core.active_profile()
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setMinimumHeight(120)
        from PyQt6.QtGui import QPixmap
        pix = QPixmap(str(self.core.asset_path(profile['selected_asset_id'])))
        image.setPixmap(pix.copy(0, 0, pix.height(), pix.height()).scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        layout.addWidget(image)
        layout.addWidget(label(profile['name'] + ' · ' + ('On your desktop' if self.controller.pet.isVisible() else 'Resting')))
        actions = QHBoxLayout()
        actions.addWidget(button('Launch floating pet', self.controller.show_pet, True))
        actions.addWidget(button('Hide floating pet', self.controller.hide_pet))
        layout.addLayout(actions)
        self.content_layout.addWidget(frame)
        frame, layout = self.card('Recent activity')
        records = self.core.history()[:4]
        if not records:
            layout.addWidget(label('No commands executed yet. Try a registered phrase with your pet.', 'muted'))
        for record in records:
            layout.addWidget(label(f"{self.local_time(record['executed_at'])}    {record['name']}    {record['execution_status'].title()}"))
        layout.addWidget(button('View all activity', lambda: self.navigation.setCurrentRow(4), icon='arrow-right'))
        self.content_layout.addWidget(frame)
        frame, layout = self.card('Memory overview')
        categories = self.core.categories()
        memories = self.core.memories()
        for category in categories:
            count = sum(m['category_id'] == category['id'] for m in memories)
            layout.addWidget(label(f"{category['name']}    {count}"))
            progress = QProgressBar()
            progress.setRange(0, max(1, len(memories)))
            progress.setValue(count)
            progress.setTextVisible(False)
            progress.setFixedHeight(6)
            layout.addWidget(progress)
        layout.addWidget(button('Open memory', lambda: self.navigation.setCurrentRow(1), icon='arrow-right'))
        self.content_layout.addWidget(frame)

    def page_memory(self):
        self.heading('Long-term memory', 'Structured information, saved locally. Sensitive values use Windows user encryption.', [button('Add memory', self.edit_memory, True, 'brain')])
        bar = QWidget()
        row = QHBoxLayout(bar)
        search = QLineEdit(self.memory_query)
        search.setPlaceholderText('Search title, key or description…')
        categories = QComboBox()
        categories.addItem('All categories', None)
        for category in self.core.categories():
            categories.addItem(category['name'], category['id'])
        categories.setCurrentIndex(max(0, categories.findData(self.memory_category)))
        def filter_rows():
            self.memory_query, self.memory_category = search.text(), categories.currentData()
            self.fill_memories()
        search.textChanged.connect(filter_rows)
        categories.currentIndexChanged.connect(filter_rows)
        row.addWidget(search, 2)
        row.addWidget(categories, 1)
        row.addWidget(button('New category', self.new_category))
        self.content_layout.addWidget(bar)
        self.memory_table = self.table(['Title', 'Category', 'Value', 'Enabled'], [])
        self.content_layout.addWidget(self.memory_table)
        self.fill_memories()
        self.memory_table.doubleClicked.connect(lambda: self.selected_memory(self.edit_memory))
        actions = QWidget()
        row = QHBoxLayout(actions)
        row.addWidget(button('Edit / reveal selected', lambda: self.selected_memory(self.edit_memory)))
        row.addWidget(button('Delete selected', lambda: self.selected_memory(lambda record: self.confirm('Delete memory', 'Permanently delete this memory?', lambda: self.core.delete_memory(record['id'])))))
        row.addWidget(button('Export memories', lambda: self.export_json(self.core.export_memories(), 'memories.json')))
        row.addWidget(button('Import memories', lambda: self.import_json(self.core.import_memories)))
        self.content_layout.addWidget(actions)
        self.content_layout.addWidget(label('Ordinary JSON exports exclude all sensitive categories. Database backups retain encrypted values.', 'muted'))

    def fill_memories(self):
        self.memory_records = self.core.memories(self.memory_query, self.memory_category)
        self.memory_table.setRowCount(len(self.memory_records))
        for index, record in enumerate(self.memory_records):
            for column, key in enumerate(('title', 'category', 'memory_value', 'enabled')):
                value = ('Yes' if record[key] else 'No') if key == 'enabled' else record[key]
                self.memory_table.setItem(index, column, QTableWidgetItem(str(value)))
            self.memory_table.setRowHeight(index, 48)

    def selected_memory(self, callback):
        index = self.memory_table.currentRow()
        if index >= 0:
            self.guard(lambda: callback(self.memory_records[index]))

    def new_category(self):
        name, ok = QInputDialog.getText(self, 'New category', 'Category name')
        if ok:
            sensitive = QMessageBox.question(self, 'Sensitive category', 'Encrypt values in this category with Windows user encryption?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
            self.guard(lambda: self.core.add_category(name, sensitive))

    def edit_memory(self, record=None):
        if isinstance(record, bool):
            record = None
        if record:
            record = self.core.get_memory(record['id'], reveal=True)
        dialog, form, buttons = self.dialog('Edit memory' if record else 'Add memory')
        category = QComboBox()
        for cat in self.core.categories():
            category.addItem(cat['name'], cat['id'])
        if record:
            category.setCurrentIndex(category.findData(record['category_id']))
        title = QLineEdit(record['title'] if record else '')
        value = QTextEdit(record['memory_value'] if record else '')
        value.setMaximumHeight(120)
        description = QLineEdit(record['description'] if record else '')
        enabled = QCheckBox('Available to explicit memory commands')
        enabled.setChecked(bool(record['enabled']) if record else True)
        for name, widget in [('Category', category), ('Title', title), ('Value', value), ('Description / tags', description), ('Enabled', enabled)]:
            form.addRow(name, widget)
        form.addRow(label('Memory keys are generated internally. Sensitive values stay out of search, logs, history and exports.', 'muted'))
        def save():
            def perform():
                key = record['memory_key'] if record else 'custom.' + identifier()
                self.core.save_memory(category.currentData(), title.text(), key, value.toPlainText(), description.text(), enabled.isChecked(), record['id'] if record else None)
                dialog.accept()
            self.guard(perform)
        form.addRow(buttons)
        buttons.accepted.connect(save)
        dialog.exec()

    def dialog(self, title):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(500)
        form = QFormLayout(dialog)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(14)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(dialog.reject)
        # Insert fields before this final row.
        buttons.setParent(dialog)
        return dialog, form, buttons

    def page_commands(self):
        self.heading('Commands', 'Registered phrases and natural requests for your enabled actions.', [button('New command', self.edit_command, True, 'zap')])
        records = self.core.commands()
        table = self.table(['Command', 'Phrases', 'Action', 'Enabled'], [(r['name'], ' · '.join(r['phrases']), r['target'], 'Yes' if r['enabled'] else 'No') for r in records])
        self.content_layout.addWidget(table)
        def selected(callback):
            if table.currentRow() >= 0:
                self.guard(lambda: callback(records[table.currentRow()]))
        table.doubleClicked.connect(lambda: selected(self.edit_command))
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.addWidget(button('Edit selected', lambda: selected(self.edit_command)))
        row.addWidget(button('Test selected', lambda: selected(lambda r: QMessageBox.information(self, 'Command result', self.controller.execute(r['phrases'][0], self)['message']))))
        row.addWidget(button('Delete selected', lambda: selected(lambda r: self.confirm('Delete command', 'Delete this command and all its phrases?', lambda: self.core.delete_command(r['id'])))))
        self.content_layout.addWidget(bar)
        self.content_layout.addWidget(label('Reserved: help · remember my name as <name> · what is my name. Memory writes require confirmation.', 'muted'))
        frame, layout = self.card('Test command understanding')
        self.smart_input = QLineEdit()
        self.smart_input.setMaxLength(500)
        self.smart_input.setPlaceholderText('Can you open Chrome please?')
        self.smart_result = label('Test a phrase to see its meaning. Nothing will be executed.', 'muted')
        def test_understanding():
            result = self.core.interpret(self.smart_input.text())
            intent = result.intent
            command = next((r for r in self.core.commands() if r['id'] == result.command_id), None)
            self.smart_result.setText('\n'.join([
                'Intent: ' + (intent.intent.value if intent else 'UNKNOWN'),
                'Target: ' + (intent.target or '—' if intent else '—'),
                'Resolved command: ' + (command['name'] if command else '—'),
                f'Confidence: {result.confidence:.0%}',
                'Match: ' + result.reason.value,
                'Execution: Not executed',
            ]))
        layout.addWidget(self.smart_input)
        self.smart_test_button = button('Test Understanding', test_understanding)
        layout.addWidget(self.smart_test_button)
        layout.addWidget(self.smart_result)
        self.smart_input.returnPressed.connect(test_understanding)
        self.content_layout.addWidget(frame)
        self.software_panel = SoftwareDiscoveryPanel(self)
        self.content_layout.addWidget(self.software_panel)

    def edit_command(self, record=None):
        if isinstance(record, bool):
            record = None
        dialog, form, buttons = self.dialog('Edit command' if record else 'New command')
        name = QLineEdit(record['name'] if record else '')
        action = QComboBox()
        action.addItems(['application', 'url'])
        applications = QComboBox()
        from ..services.windows_launcher import WindowsLauncher
        for key in sorted(WindowsLauncher.SUPPORTED_APPS):
            applications.addItem(key, key)
        for app in self.core.list_registered_applications():
            applications.addItem(app.name + (' (disabled)' if not app.enabled else ''), app.id)
        url = QLineEdit()
        url.setPlaceholderText('https://example.com')
        phrases = QTextEdit('\n'.join(record['phrases']) if record else '')
        phrases.setMaximumHeight(110)
        enabled = QCheckBox('Enabled')
        enabled.setChecked(bool(record['enabled']) if record else True)
        def action_changed():
            applications.setVisible(action.currentText() == 'application')
            url.setVisible(action.currentText() == 'url')
        action.currentIndexChanged.connect(action_changed)
        if record:
            action.setCurrentText(record['action_type'])
            index = applications.findData(record['target'])
            if index < 0 and record['action_type'] == 'application':
                applications.addItem('Removed application — choose a replacement', record['target'])
                index = applications.count() - 1
            applications.setCurrentIndex(index)
            url.setText(record['target'] if record['action_type'] == 'url' else '')
        for title, widget in [('Name', name), ('Action', action), ('Application', applications), ('HTTPS URL', url), ('Phrases, one per line', phrases), ('Status', enabled)]:
            form.addRow(title, widget)
        action_changed()
        def save():
            def perform():
                target = applications.currentData() if action.currentText() == 'application' else url.text().strip()
                self.core.save_command(name.text(), action.currentText(), target, [p.strip() for p in phrases.toPlainText().splitlines() if p.strip()], enabled.isChecked(), record['id'] if record else None)
                dialog.accept()
            self.guard(perform)
        form.addRow(buttons)
        buttons.accepted.connect(save)
        dialog.exec()

    def page_pet_studio(self):
        self.heading('Pet Studio', 'Make your companion feel at home.', [button('Import PNG sheet', lambda: self.guard(self.import_pet))])
        frame, layout = self.card()
        form = QFormLayout()
        profiles = QComboBox()
        records = self.core.profiles()
        for record in records:
            profiles.addItem(record['name'] + (' · active' if record['is_active'] else ''), record['id'])
        active = self.core.active_profile()
        profiles.setCurrentIndex(profiles.findData(active['id']))
        assets = QComboBox()
        for asset in self.core.assets():
            assets.addItem(asset['name'], asset['id'])
        name = QLineEdit()
        controls = {}
        for key, low, high in [('size', 96, 400), ('chat_width', 260, 600), ('text_size', 10, 24)]:
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            controls[key] = slider
        for key in ('always_on_top', 'animations'):
            controls[key] = QCheckBox()
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(180)
        chat_preview = QLabel('Try “open notepad” or “what is my name”')
        chat_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        def preview_update():
            from PyQt6.QtGui import QPixmap, QColor
            pix = QPixmap(str(self.core.asset_path(assets.currentData())))
            size = min(200, controls['size'].value())
            preview.setPixmap(pix.copy(0, 0, pix.height(), pix.height()).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
            color = QColor(DEFAULT_PET['background'])
            color.setAlphaF(DEFAULT_PET['opacity'])
            chat_preview.setStyleSheet(f'background:rgba({color.red()},{color.green()},{color.blue()},{color.alpha()}); color:white; border-radius:{DEFAULT_PET["radius"]}px; padding:12px; font-size:{controls["text_size"].value()}px;')
            chat_preview.setMaximumWidth(controls['chat_width'].value())
        def load_profile():
            record = next(r for r in records if r['id'] == profiles.currentData())
            name.setText(record['name'])
            assets.setCurrentIndex(assets.findData(record['selected_asset_id']))
            for key, field in controls.items():
                value = record['config'].get(key, DEFAULT_PET.get(key))
                if isinstance(field, QCheckBox):
                    field.setChecked(bool(value))
                elif isinstance(field, QSlider):
                    field.setValue(int(value))
            preview_update()
        form.addRow('Profile', profiles)
        form.addRow('Pet name', name)
        form.addRow('Pet image', assets)
        for key in ('size', 'chat_width', 'text_size'):
            slider = controls[key]
            val_label = QLabel(str(slider.value()))
            val_label.setFixedWidth(36)
            val_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            slider.valueChanged.connect(lambda val, lbl=val_label: lbl.setText(str(val)))
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(val_label)
            form.addRow(key.replace('_', ' ').title(), row_widget)
        for key in ('always_on_top', 'animations'):
            form.addRow(key.replace('_', ' ').title(), controls[key])
        load_profile()
        profiles.currentIndexChanged.connect(load_profile)
        assets.currentIndexChanged.connect(preview_update)
        for field in controls.values():
            if isinstance(field, QCheckBox):
                field.toggled.connect(preview_update)
            else:
                field.valueChanged.connect(preview_update)
        layout.addWidget(preview)
        layout.addWidget(chat_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(form)
        def config(existing_id=None):
            active_coords = None
            if existing_id:
                try:
                    current_rec = next((r for r in self.core.profiles() if r['id'] == existing_id), None)
                    if current_rec:
                        active_coords = (current_rec['config'].get('x'), current_rec['config'].get('y'))
                except Exception:
                    pass
            return {
                'size': controls['size'].value(),
                'chat_width': controls['chat_width'].value(),
                'text_size': controls['text_size'].value(),
                'always_on_top': controls['always_on_top'].isChecked(),
                'animations': controls['animations'].isChecked(),
                'radius': DEFAULT_PET['radius'],
                'background': DEFAULT_PET['background'],
                'opacity': DEFAULT_PET['opacity'],
                'x': active_coords[0] if active_coords else DEFAULT_PET['x'],
                'y': active_coords[1] if active_coords else DEFAULT_PET['y'],
            }
        layout.addWidget(button('Save & activate profile', lambda: self.guard(lambda: self.core.save_profile(name.text(), assets.currentData(), config(profiles.currentData()), profiles.currentData())), True))
        layout.addWidget(button('Save as new profile', lambda: self.guard(lambda: self.core.save_profile(name.text(), assets.currentData(), config()))))
        layout.addWidget(label('Size presets: Small 128 · Medium 240 · Large 320. Dragging saves the position automatically.', 'muted'))
        self.content_layout.addWidget(frame)

    def import_pet(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import horizontal PNG sprite sheet', '', 'PNG images (*.png)')
        if path:
            self.core.import_asset(path)

    @staticmethod
    def local_time(value):
        return datetime.fromisoformat(value).astimezone().strftime('%d %b %Y, %H:%M')

    def page_activity(self):
        self.heading('Activity', 'Registered command executions, separate from your memories.', [button('Clear history', lambda: self.confirm('Clear history', 'Permanently clear all command history?', self.core.clear_history))])
        filters = QWidget()
        row = QHBoxLayout(filters)
        status = QComboBox()
        status.addItems(['All statuses', 'success', 'failed'])
        status.setCurrentText(self.activity_status or 'All statuses')
        date = QLineEdit(self.activity_date)
        date.setPlaceholderText('Local date: YYYY-MM-DD (optional)')
        command = QComboBox()
        command.addItem('All commands', None)
        for record in self.core.commands():
            command.addItem(record['name'], record['id'])
        command.setCurrentIndex(max(0, command.findData(self.activity_command)))
        def apply():
            self.activity_status = '' if status.currentIndex() == 0 else status.currentText()
            self.activity_date = date.text().strip()
            self.activity_command = command.currentData()
            self.refresh()
        row.addWidget(status)
        row.addWidget(command)
        row.addWidget(date)
        row.addWidget(button('Filter', apply))
        self.content_layout.addWidget(filters)
        records = self.core.history(self.activity_status, self.activity_date, self.activity_command)
        self.content_layout.addWidget(self.table(['Command', 'Phrase', 'Executed', 'Status / reason'], [(r['name'], r['trigger_phrase'], self.local_time(r['executed_at']), r['execution_status'] + (' · ' + r['error_message'] if r['error_message'] else '')) for r in records]))

    def page_settings(self):
        self.heading('Settings', 'Application preferences and local data management.')
        frame, layout = self.card('General')
        form = QFormLayout()
        config = self.core.app_settings()
        theme = QComboBox()
        theme.addItems(['light', 'dark'])
        theme.setCurrentText(config['theme'])
        form.addRow('Theme', theme)
        voice_mode = QComboBox()
        voice_mode.addItem('Only English (Fast Vosk Streaming)', 'english')
        voice_mode.addItem('Multi-language (Tamil / English Whisper)', 'multilingual')
        current_voice = config.get('voice_mode', 'english')
        voice_mode.setCurrentIndex(1 if current_voice == 'multilingual' else 0)
        form.addRow('Voice Recognition', voice_mode)
        layout.addLayout(form)
        layout.addWidget(button('Save preferences', lambda: self.guard(lambda: self.core.save_settings(dict(config, theme=theme.currentText(), voice_mode=voice_mode.currentData()))), True))
        layout.addWidget(label('Default profile, size and animation preferences are managed in Pet Studio.', 'muted'))
        self.content_layout.addWidget(frame)
        frame, layout = self.card('Data')
        layout.addWidget(button('Export configuration', lambda: self.export_json(self.core.export_configuration(), 'configuration.json')))
        layout.addWidget(button('Import configuration', lambda: self.import_json(self.core.import_configuration)))
        layout.addWidget(button('Export memories', lambda: self.export_json(self.core.export_memories(), 'memories.json')))
        layout.addWidget(button('Create database backup', lambda: self.guard(lambda: QMessageBox.information(self, 'Backup created', str(self.core.backup())))))
        layout.addWidget(button('Restore database backup', self.restore_backup))
        layout.addWidget(button('Clear command history', lambda: self.confirm('Clear history', 'Permanently clear command history?', self.core.clear_history)))
        layout.addWidget(label('Imports are validated and do not overwrite matching records. Configuration imports switch the active profile and preferences. Restore creates a recovery snapshot first. Imported pet images must remain in the pets folder; encrypted backups require this Windows user.', 'muted'))
        self.content_layout.addWidget(frame)

    def export_json(self, payload, filename):
        path, _ = QFileDialog.getSaveFileName(self, 'Export JSON', filename, 'JSON (*.json)')
        if path:
            def save():
                # QFileDialog handles the user's overwrite confirmation.
                with Path(path).open('w', encoding='utf8') as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
            self.guard(save)

    def import_json(self, importer):
        path, _ = QFileDialog.getOpenFileName(self, 'Import JSON', '', 'JSON (*.json)')
        if path:
            def apply():
                if Path(path).stat().st_size > 10 * 1024 * 1024:
                    raise ValueError('JSON imports must be under 10 MB.')
                importer(json.loads(Path(path).read_text(encoding='utf-8-sig')))
                QMessageBox.information(self, 'Import complete', 'Validated data imported successfully.')
            self.confirm('Import data', 'Apply this import? Existing records are preserved; conflicts reject the entire import.', apply)

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Restore backup', str(self.core.root / 'backups'), 'SQLite database (*.db)')
        if path:
            self.confirm('Restore database', 'Replace the current database with this backup? A recovery backup will be created first.', lambda: self.core.restore(path))
