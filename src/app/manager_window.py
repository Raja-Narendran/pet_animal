"""Native Manager with seven pages, shared services, and Figma-inspired tokens."""
import json
import re
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QListWidget, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QComboBox, QDialog, QFormLayout,
    QLayout, QDialogButtonBox, QTextEdit, QPlainTextEdit, QCheckBox, QFileDialog,
    QMessageBox, QProgressBar, QSlider)
from ..core.application import DEFAULT_PET
from ..core.memory import MemoryConflict
from ..config.settings import settings
from .software_discovery import SoftwareDiscoveryState, SoftwareDiscoveryPanel


PALETTES = {
    'light': dict(background='#F7F9FC', surface='#FFFFFF', text='#1F2937', muted='#64748B', border='#E2E8F0', selection='#D1D5DB'),
    'dark': dict(background='#111827', surface='#1F2937', text='#F7F9FC', muted='#A6B5C9', border='#374151', selection='#4B5563'),
}
PAGES = ['Dashboard', 'Memory', 'Commands', 'Workflows', 'Pet Studio', 'Activity', 'Settings']


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
        self.memory_type = self.memory_scope = self.memory_state = None
        self.memory_sort = 'updated'
        self.memory_selected_id = None
        self.activity_status = self.activity_date = ''
        self.activity_command = None
        self.workflows_panel = None
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
        self.content_scroll = scroll
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        panel = getattr(self, "workflows_panel", None)
        if panel is not None:
            panel.set_compact(self.width() < 1100)

    def closeEvent(self, event):
        event.ignore()
        if self.page == "Workflows" and self.workflows_panel and not self.workflows_panel.can_leave():
            return
        self.hide()
        if not self.controller.pet.isVisible() and not self.controller.pet.tray_icon.isVisible():
            self.controller.quit()

    def navigate(self, index):
        if index < 0:
            return
        if PAGES[index] != self.page and self.page == "Workflows" and self.workflows_panel and not self.workflows_panel.can_leave():
            self.navigation.blockSignals(True)
            self.navigation.setCurrentRow(PAGES.index(self.page))
            self.navigation.blockSignals(False)
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
            QLineEdit,QTextEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:%(surface)s; border:1px solid %(border)s; border-radius:8px; padding:8px;}
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
                if item.widget() is not self.workflows_panel:
                    item.widget().deleteLater()
        getattr(self, 'page_' + self.page.lower().replace(' ', '_'))()
        if self.page != "Workflows":
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
        memory = self.core.get_memory_by_key('user.name', consume=False)
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
        self.heading('Personal memory', 'Your profile, preferences and knowledge, saved locally and under your control.', [button('Add memory', self.edit_memory, True, 'brain')])
        filters = QWidget()
        rows = QVBoxLayout(filters)
        rows.setContentsMargins(0, 0, 0, 0)
        search_row, filter_row = QHBoxLayout(), QHBoxLayout()
        self.memory_search = QLineEdit(self.memory_query)
        self.memory_search.setObjectName('memorySearch')
        self.memory_search.setPlaceholderText('Search title, key or value…')
        self.memory_categories = QComboBox()
        self.memory_categories.addItem('All categories', None)
        for category in self.core.categories():
            self.memory_categories.addItem(category['name'], category['id'])
        self.memory_categories.setCurrentIndex(max(0, self.memory_categories.findData(self.memory_category)))
        self.memory_scopes = QComboBox()
        self.memory_scopes.setObjectName('memoryScopes')
        self.memory_scopes.addItem('All scopes', None)
        self.memory_scopes.addItem('Global', 'GLOBAL')
        self.memory_scopes.addItem('Temporary', 'TEMPORARY')
        self.memory_scopes.setCurrentIndex(max(0, self.memory_scopes.findData(self.memory_scope)))
        self.memory_states = QComboBox()
        for title, state in [('All states', None), ('Enabled', 'enabled'), ('Disabled', 'disabled'), ('Sensitive', 'sensitive'), ('Expired', 'expired')]:
            self.memory_states.addItem(title, state)
        self.memory_states.setCurrentIndex(max(0, self.memory_states.findData(self.memory_state)))
        self.memory_usage = QComboBox()
        for title, order in [('Recently updated', 'updated'), ('Recently used', 'recently_used'), ('Most used', 'most_used')]:
            self.memory_usage.addItem(title, order)
        self.memory_usage.setCurrentIndex(max(0, self.memory_usage.findData(self.memory_sort)))
        def filter_rows():
            self.memory_query = self.memory_search.text()
            self.memory_category = self.memory_categories.currentData()
            self.memory_scope = self.memory_scopes.currentData()
            self.memory_state = self.memory_states.currentData()
            self.memory_sort = self.memory_usage.currentData()
            self.guard(self.fill_memories)
        self.memory_search.textChanged.connect(filter_rows)
        for choice in (self.memory_categories, self.memory_scopes, self.memory_states, self.memory_usage):
            choice.currentIndexChanged.connect(filter_rows)
        search_row.addWidget(self.memory_search, 2)
        search_row.addWidget(self.memory_categories, 1)
        for choice in (self.memory_scopes, self.memory_states, self.memory_usage):
            filter_row.addWidget(choice)
        rows.addLayout(search_row)
        rows.addLayout(filter_row)
        self.content_layout.addWidget(filters)
        health = self.core.memory_service.memory_health()
        self.memory_health_label = label(' · '.join(f"{name}: {health[key]}" for name, key in [('Total', 'total'), ('Active', 'active'), ('Disabled', 'disabled'), ('Sensitive', 'sensitive')]), 'muted')
        self.content_layout.addWidget(self.memory_health_label)
        self.memory_table = self.table(['Title', 'Category', 'Value', 'Scope', 'Used', 'Enabled'], [])
        self.memory_table.setObjectName('memoryTable')
        self.memory_table.setWordWrap(False)
        self.memory_table.itemSelectionChanged.connect(self.show_selected_memory)
        self.memory_table.doubleClicked.connect(lambda: self.selected_memory(self.edit_memory))
        self.content_layout.addWidget(self.memory_table)
        self.memory_details, self.memory_details_layout = self.card('Memory details')
        self.content_layout.addWidget(self.memory_details)
        self.fill_memories()
        actions = QWidget()
        row = QHBoxLayout(actions)
        row.addWidget(button('Safe export', lambda: self.export_json(self.core.export_memories(), 'memories.json')))
        row.addWidget(button('Import memories', self.import_memory_json))
        row.addWidget(button('Full encrypted backup', self.backup_memory_database))
        row.addWidget(button('Clean expired memories', self.clean_expired_memories))
        self.content_layout.addWidget(actions)
        self.content_layout.addWidget(label('Safe JSON exports exclude sensitive categories. Full SQLite backups retain values encrypted for this Windows user.', 'muted'))

    def fill_memories(self):
        state = self.memory_state
        self.memory_records = self.core.memory_service.list_memories(
            self.memory_query, self.memory_category,
            memory_scope=self.memory_scope, enabled=True if state == 'enabled' else False if state == 'disabled' else None,
            sensitive=True if state == 'sensitive' else None, expired=True if state == 'expired' else None,
            include_expired=True, sort=self.memory_sort)
        self.memory_table.blockSignals(True)
        self.memory_table.setRowCount(len(self.memory_records))
        self.memory_table.setMinimumHeight(min(420, max(160, 52 * (len(self.memory_records) + 1))))
        selected_row = -1
        for index, record in enumerate(self.memory_records):
            values = (record['title'], record['category'], record['memory_value'],
                      record['memory_scope'].replace('_', ' ').title(), record['access_count'],
                      'Yes' if record['enabled'] else 'No')
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.memory_table.setItem(index, column, item)
            self.memory_table.setRowHeight(index, 48)
            if record['id'] == self.memory_selected_id:
                selected_row = index
        if selected_row >= 0:
            self.memory_table.selectRow(selected_row)
        else:
            self.memory_table.clearSelection()
            self.memory_table.setCurrentCell(-1, -1)
        self.memory_table.blockSignals(False)
        self.show_selected_memory()

    def selected_memory(self, callback):
        index = self.memory_table.currentRow()
        if 0 <= index < len(self.memory_records):
            self.guard(lambda: callback(self.memory_records[index]))

    def show_selected_memory(self):
        while self.memory_details_layout.count() > 1:
            item = self.memory_details_layout.takeAt(1)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        index = self.memory_table.currentRow()
        if not 0 <= index < len(self.memory_records):
            self.memory_details_layout.addWidget(label('Select a memory to inspect its value, provenance and usage.', 'muted'))
            return
        record = self.core.get_memory(self.memory_records[index]['id'])
        if not record:
            return
        self.memory_selected_id = record['id']
        self.memory_value_revealed = False
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        self.memory_detail_value = QTextEdit()
        self.memory_detail_value.setPlainText(record['memory_value'])
        self.memory_detail_value.setObjectName('memoryDetailValue')
        self.memory_detail_value.setReadOnly(True)
        self.memory_detail_value.setMaximumHeight(100)
        form.addRow('Title', label(record['title']))
        form.addRow('Key', label(record['memory_key']))
        form.addRow('Value', self.memory_detail_value)
        if record['sensitive']:
            self.memory_reveal_button = button('Reveal value', lambda: self.reveal_memory_value(record['id']))
            form.addRow('', self.memory_reveal_button)
        category = next((cat['name'] for cat in self.core.categories() if cat['id'] == record['category_id']), '')
        fields = [('Category', category),
                  ('Scope', record['memory_scope'].replace('_', ' ').title()),
                  ('Created', self.local_time(record['created_at'])),
                  ('Updated', self.local_time(record['updated_at'])),
                  ('Last used', self.local_time(record['last_accessed_at']) if record['last_accessed_at'] else 'Never'),
                  ('Usage count', str(record['access_count'])),
                  ('Sensitive', 'Yes — Windows user encryption' if record['sensitive'] else 'No')]
        for name, value in fields:
            form.addRow(name, label(value))
        self.memory_details_layout.addWidget(body)
        actions = QWidget()
        row = QHBoxLayout(actions)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(button('Edit memory', lambda: self.guard(lambda: self.edit_memory(record))))
        row.addWidget(button('Disable' if record['enabled'] else 'Enable', lambda: self.guard(lambda: self.core.memory_service.update_memory(record['id'], enabled=not bool(record['enabled'])))))
        row.addWidget(button('Delete memory', lambda: self.confirm('Delete memory', 'Permanently delete this memory?', lambda: self.core.delete_memory(record['id']))))
        self.memory_details_layout.addWidget(actions)

    def reveal_memory_value(self, memory_id):
        def reveal():
            if self.memory_value_revealed:
                self.memory_detail_value.setPlainText('••••••••')
                self.memory_value_revealed = False
                self.memory_reveal_button.setText('Reveal value')
                return
            record = self.core.get_memory(memory_id, reveal=True)
            if record:
                self.memory_detail_value.setPlainText(record['memory_value'])
                self.memory_value_revealed = True
                self.memory_reveal_button.setText('Hide value')
        self.guard(reveal)

    def _existing_default_titles(self):
        records = self.core.memories()
        has_name = False
        has_address = False
        has_email = False
        for r in records:
            t = (r.get('title') or '').strip().lower()
            k = (r.get('memory_key') or '').strip().lower()
            if t in ('name', 'my name', 'full name', 'user name') or k in ('user.name', 'name', 'my.name'):
                has_name = True
            if t in ('address', 'my address', 'home address') or k in ('address', 'user.address', 'my.address', 'home.address'):
                has_address = True
            if t in ('email', 'email id', 'email-id', 'emailid', 'my email', 'my email id') or k in ('email', 'email.id', 'email_id', 'emailid', 'user.email', 'my.email'):
                has_email = True
        return has_name, has_address, has_email

    def edit_memory(self, record=None):
        if isinstance(record, bool):
            record = None
        if record:
            record = self.core.get_memory(record['id'])
        dialog, form, buttons = self.dialog('Edit memory' if record else 'Add memory')
        dialog.resize(500, 440)
        category = QComboBox()
        category.setObjectName('memoryCategory')
        for cat in self.core.categories():
            category.addItem(cat['name'], cat['id'])
        if record:
            category.setCurrentIndex(category.findData(record['category_id']))
        else:
            personal_idx = next((i for i in range(category.count()) if 'personal' in category.itemText(i).lower()), -1)
            if personal_idx >= 0:
                category.setCurrentIndex(personal_idx)
        title = QLineEdit(record['title'] if record else '')
        title.setObjectName('memoryTitle')
        key = QLineEdit(record['memory_key'] if record else '')
        key.setObjectName('memoryKey')
        key.setPlaceholderText('Auto-generated from title')

        # Auto-create key according to title when adding new memory
        key_manually_edited = [False]

        title_option = None
        id_title = None
        id_title_label = None
        title_label = None
        if not record:
            has_name, has_address, has_email = self._existing_default_titles()
            default_options = []
            if not has_name:
                default_options.append('Name')
            if not has_address:
                default_options.append('Address')
            default_options.append('IDs')
            default_options.append('Mobile number')
            if not has_email:
                default_options.append('Email ID')
            default_options.append('Custom')

            title_option = QComboBox()
            title_option.setObjectName('memoryTitleOption')
            for opt in default_options:
                title_option.addItem(opt, opt)

            id_title = QLineEdit()
            id_title.setObjectName('memoryIdTitle')
            id_title.setPlaceholderText('Enter ID title (e.g. Passport, Driving License, Voter ID, Aadhaar)')
            id_title_label = QLabel('ID Title')

            title_label = QLabel('Title')

            title_option_label = QLabel('Title')

            password_app = QLineEdit()
            password_app.setObjectName('memoryPasswordApp')
            password_app.setPlaceholderText('e.g. Google, GitHub, Netflix, Instagram, Office')
            password_app_label = QLabel('Website or app name')

            def on_title_changed(text):
                clean = text.strip()
                cat_name = category.currentText().lower()
                is_personal = ('personal' in cat_name)
                is_password = ('password' in cat_name)
                if is_personal and clean and clean not in ('Name', 'Address', 'Mobile number', 'Email ID') and title_option.currentText() != 'IDs':
                    if title_option.currentText() != 'Custom':
                        title_option.blockSignals(True)
                        title_option.setCurrentText('Custom')
                        title_option.blockSignals(False)
                        title_label.setVisible(True)
                        title.setVisible(True)
                        title.setReadOnly(False)
                if not key_manually_edited[0]:
                    if is_personal and title_option and title_option.currentText() == 'Name':
                        key.setText('user.name')
                    elif is_personal and title_option and title_option.currentText() == 'Email ID':
                        key.setText('email.id')
                    elif is_personal and title_option and title_option.currentText() == 'Mobile number':
                        key.setText('mobile.number')
                    elif is_password and password_app.text().strip():
                        t = password_app.text().strip()
                        full = t if 'password' in t.lower() else f"{t} Password"
                        key.setText(re.sub(r'[^a-z0-9_.]+', '.', full.lower()).strip('.'))
                    else:
                        slug = re.sub(r'[^a-z0-9_.]+', '.', text.strip().lower()).strip('.')
                        key.setText(slug)
            title.textChanged.connect(on_title_changed)
            key.textEdited.connect(lambda: key_manually_edited.__setitem__(0, True))

            def on_password_app_changed(text):
                clean = text.strip()
                if clean:
                    t = clean if 'password' in clean.lower() else f"{clean} Password"
                    title.setText(t)
                    slug = re.sub(r'[^a-z0-9_.]+', '.', t.lower()).strip('.')
                    key.setText(slug if slug else 'password')
                else:
                    title.setText('')
                    key.setText('')

            password_app.textChanged.connect(on_password_app_changed)

            def apply_option(option):
                personal_cat_index = next((i for i in range(category.count()) if 'personal' in category.itemText(i).lower()), -1)
                if option in ('Name', 'Address', 'IDs', 'Mobile number', 'Email ID'):
                    if personal_cat_index >= 0 and category.currentIndex() != personal_cat_index:
                        category.blockSignals(True)
                        category.setCurrentIndex(personal_cat_index)
                        category.blockSignals(False)

                if option == 'Name':
                    title.setText('Name')
                    key.setText('user.name')
                    value.setPlaceholderText('Enter your full name')
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                elif option == 'Address':
                    title.setText('Address')
                    key.setText('address')
                    value.setPlaceholderText('Enter your address')
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                elif option == 'Mobile number':
                    title.setText('Mobile number')
                    key.setText('mobile.number')
                    value.setPlaceholderText('Enter mobile number')
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                elif option == 'Email ID':
                    title.setText('Email ID')
                    key.setText('email.id')
                    value.setPlaceholderText('Enter email address')
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                elif option == 'IDs':
                    clean = id_title.text().strip()
                    title.setText(clean if clean else 'ID')
                    slug = re.sub(r'[^a-z0-9_.]+', '.', clean.lower()).strip('.') if clean else 'id'
                    key.setText(slug if slug else 'id')
                    value.setPlaceholderText('Enter ID number / detail')
                    id_title_label.setVisible(True)
                    id_title.setVisible(True)
                    title_label.setVisible(False)
                    title.setVisible(False)
                    id_title.setFocus()
                elif option == 'Custom':
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(True)
                    title.setVisible(True)
                    title.setReadOnly(False)
                    title.setPlaceholderText('Enter memory title')
                    value.setPlaceholderText('Enter memory value')
                    if title.text() in ('Name', 'Address', 'Mobile number', 'Email ID', 'ID'):
                        title.setText('')
                        key.setText('')
                    title.setFocus()

            title_option.currentTextChanged.connect(apply_option)

            def on_id_title_changed(text):
                if title_option.currentText() == 'IDs':
                    clean = text.strip()
                    if clean:
                        title.setText(clean)
                        slug = re.sub(r'[^a-z0-9_.]+', '.', clean.lower()).strip('.')
                        key.setText(slug if slug else 'id')
                    else:
                        title.setText('ID')
                        key.setText('id')

            id_title.textChanged.connect(on_id_title_changed)

            def on_category_changed():
                cat_name = category.currentText().lower()
                is_personal = ('personal' in cat_name)
                is_password = ('password' in cat_name)

                title_option_label.setVisible(is_personal)
                title_option.setVisible(is_personal)

                password_app_label.setVisible(is_password)
                password_app.setVisible(is_password)

                if is_personal:
                    id_title_label.setVisible(title_option.currentText() == 'IDs')
                    id_title.setVisible(title_option.currentText() == 'IDs')
                    title_label.setVisible(title_option.currentText() == 'Custom')
                    title.setVisible(title_option.currentText() == 'Custom')
                    apply_option(title_option.currentText())
                elif is_password:
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                    value.setPlaceholderText('Enter password')
                    password_app.setFocus()
                    if password_app.text().strip():
                        on_password_app_changed(password_app.text())
                    elif title.text().strip() and not title.text().endswith(' Password'):
                        password_app.setText(title.text().strip())
                else:
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(True)
                    title.setVisible(True)
                    title.setReadOnly(False)
                    title.setPlaceholderText('Enter memory title')
                    if title.text() in ('Name', 'Address', 'Mobile number', 'Email ID', 'ID') or title.text().endswith(' Password'):
                        title.setText('')
                        key.setText('')
                    value.setPlaceholderText('Enter memory value')

            category.currentIndexChanged.connect(on_category_changed)

        sensitive = bool(record and record['sensitive'])
        value = QTextEdit()
        value.setPlainText('' if sensitive else record['memory_value'] if record else '')
        value.setObjectName('memoryValue')
        value.setMaximumHeight(120)
        if sensitive:
            value.setPlaceholderText('Encrypted value is preserved. Reveal it or enter a replacement.')
        value_changed = [False]
        value.textChanged.connect(lambda: value_changed.__setitem__(0, True))

        scope = QComboBox()
        scope.setObjectName('memoryScope')
        scope.addItem('Global', 'GLOBAL')
        scope.addItem('Temporary', 'TEMPORARY')
        if record:
            current_scope = 'TEMPORARY' if record['memory_scope'] == 'TEMPORARY' else 'GLOBAL'
            scope.setCurrentIndex(scope.findData(current_scope))

        enabled = QCheckBox('Available to memory commands and retrieval')
        enabled.setChecked(bool(record['enabled']) if record else True)

        if not record:
            form.addRow('Category', category)
            form.addRow(title_option_label, title_option)
            form.addRow(id_title_label, id_title)
            form.addRow(password_app_label, password_app)
            form.addRow(title_label, title)
            form.addRow('Key', key)
            form.addRow('Value', value)
            on_category_changed()
        else:
            for name, widget in [('Category', category), ('Title', title), ('Key', key), ('Value', value)]:
                form.addRow(name, widget)

        if sensitive:
            def reveal_edit():
                revealed = self.core.get_memory(record['id'], reveal=True)
                value.setPlainText(revealed['memory_value'])
            form.addRow('', button('Reveal encrypted value', lambda: self.guard(reveal_edit)))
        form.addRow('Scope', scope)
        form.addRow('Enabled', enabled)

        def save():
            def perform():
                target_key = key.text().strip()
                target_title = title.text().strip()
                cat_name = category.currentText().lower()
                is_personal = ('personal' in cat_name)
                is_password = ('password' in cat_name)

                if not record and is_personal and title_option and title_option.currentText() == 'IDs':
                    id_entered = id_title.text().strip()
                    if not id_entered:
                        raise ValueError('Please enter a title for the ID (e.g. Passport, Driving License).')
                    target_title = id_entered

                if not record and is_password:
                    app_entered = password_app.text().strip()
                    if app_entered:
                        target_title = app_entered if 'password' in app_entered.lower() else f"{app_entered} Password"
                    elif not target_title:
                        raise ValueError('Please enter the website or app name.')

                if not target_title:
                    raise ValueError('Please enter a title for the memory.')

                if not target_key:
                    target_key = re.sub(r'[^a-z0-9_.]+', '.', target_title.lower()).strip('.')
                fields = dict(category_id=category.currentData(), title=target_title, key=target_key,
                              enabled=enabled.isChecked(), memory_scope=scope.currentData())
                if not sensitive or value_changed[0]:
                    fields['value'] = value.toPlainText()
                def apply(confirmed=False):
                    if record:
                        return self.core.memory_service.update_memory(record['id'], confirmed=confirmed, **fields)
                    return self.core.memory_service.create_memory(**fields)
                try:
                    apply()
                except MemoryConflict as conflict:
                    existing = conflict.existing
                    message = f"The saved memory “{existing['title']}” conflicts with these changes ({conflict.conflict_type.value.replace('_', ' ').lower()}). Replace the existing information?"
                    if QMessageBox.question(dialog, 'Replace saved memory', message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                        return
                    if record:
                        apply(True)
                    else:
                        self.core.memory_service.update_memory(existing['id'], confirmed=True, **fields)
                dialog.accept()
            self.guard(perform)
        form.addRow(buttons)
        buttons.accepted.connect(save)
        dialog.exec()

    def add_memory_relationship(self, record):
        dialog, form, buttons = self.dialog('Add memory relationship')
        form.addRow('From', label(record['title']))
        relation_type = QLineEdit()
        relation_type.setPlaceholderText('e.g. works_on, prefers, uses')
        target = QComboBox()
        for item in self.core.memories():
            if item['id'] != record['id']:
                target.addItem(item['title'] + ' · ' + item['memory_key'], item['id'])
        form.addRow('Relationship', relation_type)
        form.addRow('To', target)
        form.addRow(buttons)
        def save():
            def apply():
                self.core.memory_service.create_relationship(record['id'], relation_type.text(), target.currentData())
                dialog.accept()
            self.guard(apply)
        buttons.accepted.connect(save)
        dialog.exec()

    def clean_expired_memories(self):
        def clean():
            count = self.core.memory_service.expire_memories(delete=True)
            QMessageBox.information(self, 'Expired memories cleaned', f'{count} expired memories removed.')
        self.confirm('Clean expired memories', 'Permanently remove expired memories and their relationships?', clean)

    def backup_memory_database(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Full encrypted database backup', str(self.core.root / 'backups' / 'personal-memory.db'), 'SQLite database (*.db)')
        if path:
            self.guard(lambda: QMessageBox.information(self, 'Backup created', str(self.core.backup(path))))

    def import_memory_json(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import memories', '', 'JSON (*.json)')
        if not path:
            return
        def preview():
            if Path(path).stat().st_size > 10 * 1024 * 1024:
                raise ValueError('JSON imports must be under 10 MB.')
            payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            summary = self.core.memory_service.preview_import(payload)
            message = '\n'.join(f"{summary[key]} {title}" for key, title in [('new', 'new memories'), ('duplicates', 'duplicates'), ('conflicts', 'conflicts'), ('invalid', 'invalid records')])
            if summary['invalid']:
                QMessageBox.warning(self, 'Import summary', message + '\n\nFix invalid records before importing.')
                return
            if summary['conflicts']:
                message += '\n\nReplace conflicting memories with the imported records?'
            else:
                message += '\n\nApply this import? Duplicate memories will be kept.'
            def apply():
                self.core.memory_service.import_memories(payload, confirm_conflicts=bool(summary['conflicts']))
                QMessageBox.information(self, 'Import complete', 'Validated memories imported successfully.')
            self.confirm('Import summary', message, apply)
        self.guard(preview)

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

    def page_workflows(self):
        if self.workflows_panel is None:
            from .workflow_panel import WorkflowPanel
            self.workflows_panel = WorkflowPanel(self)
        self.workflows_panel.set_compact(self.width() < 1100)
        self.workflows_panel.refresh()
        self.content_layout.addWidget(self.workflows_panel, 1)
        self.workflows_panel.show()

    def open_workflow(self, routine_id):
        self.controller.show_manager('Workflows')
        if self.page == 'Workflows' and self.workflows_panel.can_leave():
            self.workflows_panel.open_routine(routine_id)

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
        row.addWidget(button('Edit in Workflows', lambda: selected(lambda r: self.open_workflow(r['target']) if r['action_type'] == 'routine' else None)))
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
                *(('File request: ' + json.dumps(intent.to_dict(), ensure_ascii=False),)
                  if intent and intent.intent.value == 'FILE_SEARCH' else ()),
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
        if record and record["action_type"] == "routine":
            self.open_workflow(record["target"])
            return
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
        table = self.table(['Command', 'Phrase', 'Executed', 'Status / reason'], [(r['name'], r['trigger_phrase'], self.local_time(r['executed_at']), r['execution_status'] + (' · ' + r['error_message'] if r['error_message'] else '')) for r in records])
        self.content_layout.addWidget(table)
        def details():
            if table.currentRow() < 0:
                return
            record = records[table.currentRow()]
            runs = self.core.rows('SELECT * FROM workflow_runs WHERE history_id=?', (record['id'],))
            if not runs:
                return
            steps = self.core.rows('SELECT * FROM workflow_step_runs WHERE run_id=? ORDER BY position', (runs[0]['id'],))
            QMessageBox.information(self, 'Routine run details', runs[0]['name'] + ' · ' + runs[0]['status'] + '\n' + '\n'.join(
                f"{s['position'] + 1}. {s['step_type']}: {s['status']}" + (' · ' + s['outcome'] if s['outcome'] else '') for s in steps))
        table.doubleClicked.connect(details)
        self.content_layout.addWidget(button('Routine run details', details))

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
        frame, layout = self.card('Local file search')
        search_config = self.core.file_search_settings()
        roots = QPlainTextEdit('\n'.join(search_config['roots']))
        roots.setPlaceholderText('One local folder per line, for example D:\\Projects.\nLeave blank to search local disks.')
        roots.setMaximumHeight(95)
        layout.addWidget(label('Search folders (one per line)', 'muted'))
        layout.addWidget(roots)
        def add_search_folder():
            folder = QFileDialog.getExistingDirectory(self, 'Choose a search folder')
            if folder:
                roots.appendPlainText(folder)
        layout.addWidget(button('Add folder', add_search_folder))
        es_path = QLineEdit(search_config['everything_executable'])
        es_path.setPlaceholderText('Optional es.exe path; blank uses automatic detection')
        layout.addWidget(label('Everything command-line client', 'muted'))
        layout.addWidget(es_path)
        def choose_es():
            path, _ = QFileDialog.getOpenFileName(self, 'Choose Everything es.exe', '', 'Everything CLI (es.exe)')
            if path:
                es_path.setText(path)
        layout.addWidget(button('Choose es.exe', choose_es))
        layout.addWidget(button('Save search settings', lambda: self.guard(lambda: self.core.save_file_search_settings(
            [line.strip() for line in roots.toPlainText().splitlines() if line.strip()], es_path.text())), True))
        layout.addWidget(label('Type /package.xml or Find pet folder. Everything and es.exe are optional; Everything must be running. Without them, a bounded background scan searches local filenames. Partial results are marked. Queries and result paths are not saved in command history.', 'muted'))
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
