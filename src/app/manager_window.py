"""Native Manager with seven pages, shared services, and Stitch design tokens."""
import json
import re
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidgetItem, QListWidget, QScrollArea, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit, QComboBox, QDialog, QFormLayout, QLayout, QDialogButtonBox, QTextEdit, QCheckBox, QFileDialog, QMessageBox, QSizePolicy
from ..core.memory import MemoryConflict
from .software_discovery import SoftwareDiscoveryState
from .manager_ui.widgets import ComboBox as QComboBox
from .manager_ui.preview import SpritePreview
from .manager_ui import pages
from .manager_ui.theme import PALETTES, stylesheet, load_font
from .manager_ui.icons import icon, apply_icons, NAV_ICONS
from .manager_ui.widgets import label, button, card, heading, FlowLayout


PAGES = ['Dashboard', 'Memory', 'Commands', 'Workflows', 'Pet Studio', 'Activity', 'Settings']


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
        self.responsive_rows = []
        self.page_subscriptions = []
        self.command_query = ""
        self.command_type = self.command_state = None
        load_font()
        root = QWidget()
        root.setObjectName("managerBackground")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(12, 32, 12, 16)
        brand = QWidget()
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(0, 0, 0, 0)
        paw = QLabel()
        paw.setProperty('iconName', 'pets')
        paw.setProperty('iconSize', 28)
        brand_row.addWidget(paw)
        brand_row.addWidget(label('PET ANIMAL', 'brand'), 1)
        nav.addWidget(brand)
        nav.addWidget(label('Your desktop companion', 'muted'))
        nav.addSpacing(28)
        self.navigation = QListWidget()
        self.navigation.setObjectName("managerNavigation")
        self.navigation.setIconSize(QSize(20, 20))
        for name in PAGES:
            self.navigation.addItem(QListWidgetItem(name))
        self.navigation.currentRowChanged.connect(self.navigate)
        nav.addWidget(self.navigation)
        nav.addWidget(button('Open floating pet', self.controller.show_pet, True, 'pets'))
        shell.addWidget(sidebar)
        scroll = QScrollArea()
        self.content_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content = QWidget()
        self.content.setObjectName("managerContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(24, 32, 24, 24)
        self.content_layout.setSpacing(16)
        self.content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(self.content)
        shell.addWidget(scroll, 1)
        self.core.listeners.append(self.refresh)
        self.navigation.setCurrentRow(PAGES.index(self.page))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for row in getattr(self, "responsive_rows", []):
            row.set_compact(self.width() < 1100)
        panel = getattr(self, "workflows_panel", None)
        if panel is not None:
            panel.set_compact(self.width() < 1100)

    def hideEvent(self, event):
        for preview in self.findChildren(SpritePreview):
            preview.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        for preview in self.findChildren(SpritePreview):
            if preview.isVisibleTo(self) and preview.animated and len(preview.frames) > 1:
                preview.timer.start()

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
        theme = self.core.app_settings()['theme']
        self.setStyleSheet(stylesheet(theme))
        for signal, callback in self.page_subscriptions:
            try:
                signal.disconnect(callback)
            except (TypeError, RuntimeError):
                pass
        self.page_subscriptions.clear()
        self.responsive_rows.clear()
        for index, name in enumerate(NAV_ICONS):
            self.navigation.item(index).setIcon(icon(name, PALETTES[theme]['accent'], dpr=self.devicePixelRatioF()))
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                for preview in item.widget().findChildren(SpritePreview):
                    preview.stop()
                item.widget().hide()
                if item.widget() is not self.workflows_panel:
                    item.widget().deleteLater()
        getattr(self, 'page_' + self.page.lower().replace(' ', '_'))()
        if self.page != "Workflows":
            self.content_layout.addStretch()
        apply_icons(self, theme)

    def heading(self, title, subtitle, actions=()):
        return heading(self, title, subtitle, actions)

    def card(self, title=None):
        return card(title)

    def navigate_to(self, page):
        self.navigation.setCurrentRow(PAGES.index(page))

    def subscribe_page(self, signal, callback):
        signal.connect(callback)
        self.page_subscriptions.append((signal, callback))

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
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setMinimumWidth(0)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                table.setItem(index, column, item)
            table.setRowHeight(index, 48)
        table.setMinimumHeight(min(420, max(160, 52 * (len(rows) + 1))))
        return table

    def page_dashboard(self):
        return pages.page_dashboard(self)

    def page_memory(self):
        return pages.page_memory(self)

    def fill_memories(self):
        state = self.memory_state
        self.memory_records = self.core.memory_service.list_memories(
            self.memory_query, self.memory_category,
            memory_scope=self.memory_scope, state=state,
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
                if record['sensitive'] and column == 2:
                    from PyQt6.QtGui import QColor
                    color = PALETTES[self.core.app_settings()['theme']]['secure']
                    item.setForeground(QColor(color))
                    item.setIcon(icon('lock', color, 16))
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
        self.memory_value_revealed = False
        while self.memory_details_layout.count() > 1:
            item = self.memory_details_layout.takeAt(1)
            if item.widget():
                for preview in item.widget().findChildren(SpritePreview):
                    preview.stop()
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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        row = FlowLayout(actions)
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
                self.memory_reveal_button.setProperty('iconName', 'visibility')
                apply_icons(self.memory_details, self.core.app_settings()['theme'])
                return
            record = self.core.get_memory(memory_id, reveal=True)
            if record:
                self.memory_detail_value.setPlainText(record['memory_value'])
                self.memory_value_revealed = True
                self.memory_reveal_button.setText('Hide value')
            glyph = 'visibility_off' if self.memory_value_revealed else 'visibility'
            self.memory_reveal_button.setProperty('iconName', glyph)
            apply_icons(self.memory_details, self.core.app_settings()['theme'])
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

    @staticmethod
    def _parse_card_value(val_str):
        num = ''
        exp = ''
        cvv = ''
        if not val_str:
            return num, exp, cvv
        for line in val_str.splitlines():
            line = line.strip()
            if not line:
                continue
            m_num = re.match(r'^(?:card\s*number|card\s*no\.?|card)\s*:\s*(.*)$', line, re.IGNORECASE)
            if m_num:
                num = m_num.group(1).strip()
                continue
            m_exp = re.match(r'^(?:expiry\s*date|expiry|exp\s*date|exp)\s*:\s*(.*)$', line, re.IGNORECASE)
            if m_exp:
                exp = m_exp.group(1).strip()
                continue
            m_cvv = re.match(r'^(?:cvv\s*number|cvv\s*no\.?|cvv|cvc)\s*:\s*(.*)$', line, re.IGNORECASE)
            if m_cvv:
                cvv = m_cvv.group(1).strip()
                continue
        if not num and not exp and not cvv and val_str.strip():
            num = val_str.strip()
        return num, exp, cvv

    def edit_memory(self, record=None):
        if isinstance(record, bool):
            record = None
        if record:
            record = self.core.get_memory(record['id'])
        dialog, form, buttons = self.dialog('Edit memory' if record else 'Add memory')
        dialog.resize(500, 480)
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

        sensitive = bool(record and record['sensitive'])
        value = QTextEdit()
        value.setPlainText('' if sensitive else record['memory_value'] if record else '')
        value.setObjectName('memoryValue')
        value.setMaximumHeight(120)
        if sensitive:
            value.setPlaceholderText('Encrypted value is preserved. Reveal it or enter a replacement.')
        value_changed = [False]
        value.textChanged.connect(lambda: value_changed.__setitem__(0, True))

        value_label = QLabel('Value')

        card_title = QLineEdit(record['title'] if record else '')
        card_title.setObjectName('memoryCardTitle')
        card_title.setPlaceholderText('e.g. HDFC Credit Card, SBI Debit Card, Visa')
        card_title_label = QLabel('Card name or bank')

        card_number = QLineEdit()
        card_number.setObjectName('memoryCardNumber')
        card_number.setPlaceholderText('Enter card number (e.g. 1234 5678 9012 3456)')
        card_number_label = QLabel('Card number')

        card_expiry = QLineEdit()
        card_expiry.setObjectName('memoryCardExpiry')
        card_expiry.setPlaceholderText('MM/YY (e.g. 12/28)')
        card_expiry_label = QLabel('Expiry date')

        card_cvv = QLineEdit()
        card_cvv.setObjectName('memoryCardCvv')
        card_cvv.setPlaceholderText('Enter CVV (e.g. 123)')
        card_cvv_label = QLabel('CVV number')

        def update_card_value():
            c_num = card_number.text().strip()
            c_exp = card_expiry.text().strip()
            c_cvv = card_cvv.text().strip()
            lines = []
            if c_num:
                lines.append(f"Card Number: {c_num}")
            if c_exp:
                lines.append(f"Expiry Date: {c_exp}")
            if c_cvv:
                lines.append(f"CVV Number: {c_cvv}")
            value.blockSignals(True)
            value.setPlainText('\n'.join(lines))
            value.blockSignals(False)
            if c_num or c_exp or c_cvv:
                value_changed[0] = True

        card_number.textChanged.connect(lambda _: update_card_value())
        card_expiry.textChanged.connect(lambda _: update_card_value())
        card_cvv.textChanged.connect(lambda _: update_card_value())

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
                is_card = ('card' in cat_name or 'credit' in cat_name or 'debit' in cat_name)
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
                    elif is_card and card_title.text().strip():
                        t = card_title.text().strip()
                        full = t if t.lower().endswith('card') else f"{t} Card"
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

            def on_card_title_changed(text):
                clean = text.strip()
                if clean:
                    t = clean if clean.lower().endswith('card') else f"{clean} Card"
                    title.setText(t)
                    slug = re.sub(r'[^a-z0-9_.]+', '.', t.lower()).strip('.')
                    key.setText(slug if slug else 'card')
                else:
                    title.setText('')
                    key.setText('')

            card_title.textChanged.connect(on_card_title_changed)

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
                is_card = ('card' in cat_name or 'credit' in cat_name or 'debit' in cat_name)

                title_option_label.setVisible(is_personal)
                title_option.setVisible(is_personal)

                password_app_label.setVisible(is_password)
                password_app.setVisible(is_password)

                card_title_label.setVisible(is_card)
                card_title.setVisible(is_card)
                card_number_label.setVisible(is_card)
                card_number.setVisible(is_card)
                card_expiry_label.setVisible(is_card)
                card_expiry.setVisible(is_card)
                card_cvv_label.setVisible(is_card)
                card_cvv.setVisible(is_card)

                if is_personal:
                    id_title_label.setVisible(title_option.currentText() == 'IDs')
                    id_title.setVisible(title_option.currentText() == 'IDs')
                    title_label.setVisible(title_option.currentText() == 'Custom')
                    title.setVisible(title_option.currentText() == 'Custom')
                    value_label.setVisible(True)
                    value.setVisible(True)
                    apply_option(title_option.currentText())
                elif is_password:
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                    value_label.setVisible(True)
                    value.setVisible(True)
                    value.setPlaceholderText('Enter password')
                    password_app.setFocus()
                    if password_app.text().strip():
                        on_password_app_changed(password_app.text())
                    elif title.text().strip() and not title.text().endswith(' Password'):
                        password_app.setText(title.text().strip())
                elif is_card:
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(False)
                    title.setVisible(False)
                    value_label.setVisible(False)
                    value.setVisible(False)
                    card_title.setFocus()
                    if card_title.text().strip():
                        on_card_title_changed(card_title.text())
                    elif title.text().strip() and not (title.text().endswith(' Password') or title.text().endswith(' Card')):
                        card_title.setText(title.text().strip())
                else:
                    id_title_label.setVisible(False)
                    id_title.setVisible(False)
                    title_label.setVisible(True)
                    title.setVisible(True)
                    title.setReadOnly(False)
                    title.setPlaceholderText('Enter memory title')
                    if title.text() in ('Name', 'Address', 'Mobile number', 'Email ID', 'ID') or title.text().endswith(' Password') or title.text().endswith(' Card'):
                        title.setText('')
                        key.setText('')
                    value_label.setVisible(True)
                    value.setVisible(True)
                    value.setPlaceholderText('Enter memory value')

            category.currentIndexChanged.connect(on_category_changed)

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
            form.addRow(card_title_label, card_title)
            form.addRow(title_label, title)
            form.addRow('Key', key)
            form.addRow(card_number_label, card_number)
            form.addRow(card_expiry_label, card_expiry)
            form.addRow(card_cvv_label, card_cvv)
            form.addRow(value_label, value)
            on_category_changed()
        else:
            cat_name = category.currentText().lower()
            is_card = ('card' in cat_name or 'credit' in cat_name or 'debit' in cat_name)
            if is_card:
                if sensitive:
                    card_number.setPlaceholderText('Encrypted value is preserved. Reveal it or enter replacement.')
                    card_expiry.setPlaceholderText('MM/YY')
                    card_cvv.setPlaceholderText('CVV')
                form.addRow('Category', category)
                form.addRow('Title', title)
                form.addRow('Key', key)
                form.addRow(card_number_label, card_number)
                form.addRow(card_expiry_label, card_expiry)
                form.addRow(card_cvv_label, card_cvv)
                form.addRow(value_label, value)
                value_label.setVisible(False)
                value.setVisible(False)
            else:
                for name, widget in [('Category', category), ('Title', title), ('Key', key), (value_label, value)]:
                    form.addRow(name, widget)

        if sensitive:
            def reveal_edit():
                revealed = self.core.get_memory(record['id'], reveal=True)
                val_text = revealed['memory_value']
                value.setPlainText(val_text)
                cat_name = category.currentText().lower()
                if 'card' in cat_name or 'credit' in cat_name or 'debit' in cat_name:
                    c_num, c_exp, c_cvv = self._parse_card_value(val_text)
                    card_number.blockSignals(True)
                    card_expiry.blockSignals(True)
                    card_cvv.blockSignals(True)
                    card_number.setText(c_num)
                    card_expiry.setText(c_exp)
                    card_cvv.setText(c_cvv)
                    card_number.blockSignals(False)
                    card_expiry.blockSignals(False)
                    card_cvv.blockSignals(False)
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
                is_card = ('card' in cat_name or 'credit' in cat_name or 'debit' in cat_name)

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

                if not record and is_card:
                    c_entered = card_title.text().strip()
                    if c_entered:
                        target_title = c_entered if c_entered.lower().endswith('card') else f"{c_entered} Card"
                    elif not target_title:
                        raise ValueError('Please enter the card name or bank.')

                if not target_title:
                    raise ValueError('Please enter a title for the memory.')

                if not target_key:
                    target_key = re.sub(r'[^a-z0-9_.]+', '.', target_title.lower()).strip('.')
                fields = dict(category_id=category.currentData(), title=target_title, key=target_key,
                              enabled=enabled.isChecked(), memory_scope=scope.currentData())

                if not record and is_card:
                    c_num = card_number.text().strip()
                    c_exp = card_expiry.text().strip()
                    c_cvv = card_cvv.text().strip()
                    if not c_num and not c_exp and not c_cvv and value.toPlainText().strip():
                        c_num, c_exp, c_cvv = self._parse_card_value(value.toPlainText())
                    if not c_num:
                        raise ValueError('Please enter the card number.')
                    if not c_exp:
                        raise ValueError('Please enter the expiry date.')
                    if not c_cvv:
                        raise ValueError('Please enter the CVV number.')
                    fields['value'] = f"Card Number: {c_num}\nExpiry Date: {c_exp}\nCVV Number: {c_cvv}"
                elif record and is_card and value_changed[0]:
                    c_num = card_number.text().strip()
                    c_exp = card_expiry.text().strip()
                    c_cvv = card_cvv.text().strip()
                    if not c_num and not c_exp and not c_cvv and value.toPlainText().strip():
                        c_num, c_exp, c_cvv = self._parse_card_value(value.toPlainText())
                    if not c_num:
                        raise ValueError('Please enter the card number.')
                    if not c_exp:
                        raise ValueError('Please enter the expiry date.')
                    if not c_cvv:
                        raise ValueError('Please enter the CVV number.')
                    fields['value'] = f"Card Number: {c_num}\nExpiry Date: {c_exp}\nCVV Number: {c_cvv}"
                elif not sensitive or value_changed[0]:
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
        return pages.page_commands(self)

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
        return pages.page_pet_studio(self)

    def import_pet(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import horizontal PNG sprite sheet', '', 'PNG images (*.png)')
        if path:
            self.core.import_asset(path)

    @staticmethod
    def local_time(value):
        return datetime.fromisoformat(value).astimezone().strftime('%d %b %Y, %H:%M')

    def page_activity(self):
        return pages.page_activity(self)

    def page_settings(self):
        return pages.page_settings(self)

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
