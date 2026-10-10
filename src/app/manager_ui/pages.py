"""Stitch page layouts wired exclusively to existing Manager handlers and services."""
import json
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPlainTextEdit, QCheckBox, QMessageBox, QFileDialog, QProgressBar, QHeaderView, QSizePolicy, QFrame, QPushButton
from ...core.application import DEFAULT_PET
from ..software_discovery import SoftwareDiscoveryPanel
from .widgets import label, button, badge, ResponsiveRow, actions as action_bar, Toggle, NoScrollSlider, SegmentedControl
from .widgets import ComboBox as QComboBox
from .icons import inline_svg_icon, GEAR_SVG, MOON_SVG, SUN_SVG, SPOTIFY_SVG, YOUTUBE_SVG, LIGHTNING_SVG, GLOBE_SVG, DOT_SVG, INFO_SVG, SAVE_TRAY_SVG

def page_dashboard(self):
    memory = self.core.get_memory_by_key('user.name', consume=False)
    greeting = 'Welcome back' + (', ' + memory['memory_value'] if memory and not memory['sensitive'] else '')
    self.heading(greeting, 'A little companion. A more personal workspace.', [
        button('Add memory', self.edit_memory, icon='add'),
        button('New command', self.edit_command, True, 'terminal')])
    stats = self.core.stats()
    cards = []
    for title, key, caption, glyph in [('Memory items', 'memories', 'Saved on this PC', 'psychology'),
            ('Registered commands', 'commands', 'Phrases you control', 'terminal'),
            ('Executed today', 'today', 'From command history', 'history')]:
        frame, layout = self.card()
        top = QHBoxLayout()
        symbol = QLabel()
        symbol.setProperty("iconName", glyph)
        top.addWidget(symbol)
        top.addWidget(label(title.upper(), 'eyebrow'), 1)
        layout.addLayout(top)
        layout.addWidget(label(str(stats[key]), 'metric'))
        layout.addWidget(label(caption, 'muted'))
        cards.append(frame)
    self.content_layout.addWidget(ResponsiveRow(self, cards))
    profile = self.core.active_profile()
    frame, layout = self.card('Active companion')
    image = QLabel()
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image.setFixedSize(120, 120)
    from PyQt6.QtGui import QPixmap
    try:
        pix = QPixmap(str(self.core.asset_path(profile['selected_asset_id'])))
        image.setPixmap(pix.copy(0, 0, pix.height(), pix.height()).scaled(110, 110,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
    except ValueError:
        image.setText('Preview unavailable')
    identity = QWidget()
    copy = QVBoxLayout(identity)
    copy.setContentsMargins(0, 0, 0, 0)
    copy.addWidget(label(profile['name'], 'subheading'))
    copy.addWidget(badge('On your desktop' if self.controller.pet.isVisible() else 'Resting',
        'success' if self.controller.pet.isVisible() else 'neutral'))
    asset = next((a for a in self.core.assets() if a['id'] == profile['selected_asset_id']), None)
    copy.addWidget(label('Asset: ' + (asset['name'] if asset else 'Unavailable'), 'muted'))
    copy.addWidget(label('Ctrl + Windows voice shortcut ' +
        ('enabled' if self.core.app_settings().get('voice_hotkey_enabled') else 'disabled'), 'muted'))
    companion = QWidget()
    companion_row = QHBoxLayout(companion)
    companion_row.setContentsMargins(0, 0, 0, 0)
    companion_row.addWidget(image)
    companion_row.addWidget(identity, 1)
    controls = action_bar([
        button('Launch floating pet', self.controller.show_pet, True, 'play_arrow'),
        button('Hide floating pet', self.controller.hide_pet, icon='visibility_off'),
        button('Customize in Studio', lambda: self.navigate_to('Pet Studio'), icon='palette')])
    layout.addWidget(ResponsiveRow(self, (companion, controls), (3, 2)))
    self.content_layout.addWidget(frame)
    activity, layout = self.card('Recent Activity')
    records = self.core.history()[:4]
    if not records:
        layout.addWidget(label('No commands executed yet. Try a registered phrase with your pet.', 'muted'))
    for record in records:
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label(record['name']))
        copy.addWidget(label(self.local_time(record['executed_at']), 'muted'))
        row.addLayout(copy, 1)
        row.addWidget(badge(record['execution_status'].title(),
            'success' if record['execution_status'] == 'success' else 'danger'))
        layout.addLayout(row)
    layout.addStretch()
    layout.addWidget(button('View all activity', lambda: self.navigate_to('Activity'), icon='arrow_forward'))
    overview, layout = self.card('Memory Breakdown & Health')
    memories = self.core.memories()
    for category in self.core.categories():
        count = sum(m['category_id'] == category['id'] for m in memories)
        line = QHBoxLayout()
        line.addWidget(label(category['name']), 1)
        line.addWidget(badge(str(count) + ' items', 'secure' if category['sensitive'] else 'neutral'))
        layout.addLayout(line)
        progress = QProgressBar()
        progress.setRange(0, max(1, len(memories)))
        progress.setValue(count)
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        progress.setProperty('secure', bool(category['sensitive']))
        layout.addWidget(progress)
    layout.addStretch()
    layout.addWidget(button('Open memory', lambda: self.navigate_to('Memory'), icon='arrow_forward'))
    self.content_layout.addWidget(ResponsiveRow(self, (activity, overview)))


def page_memory(self):
    self.heading('Personal memory', 'Your profile, preferences and knowledge, saved locally and under your control.', [button('Add memory', self.edit_memory, True, 'brain')])
    filters, rows = self.card()
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
    for title, state in [('All states', None), ('Enabled', 'enabled'), ('Disabled', 'disabled')]:
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
    self.memory_health_label.hide()
    rows.addWidget(self.memory_health_label)
    metrics = action_bar([badge(f"{name}: {health[key]}", tone) for name, key, tone in
        [('Total', 'total', 'neutral'), ('Active', 'active', 'success'), ('Disabled', 'disabled', 'neutral'), ('Sensitive', 'sensitive', 'secure')]])
    rows.addWidget(metrics)
    self.memory_table = self.table(['Title', 'Category', 'Value', 'Scope', 'Used', 'Enabled'], [])
    self.memory_table.setObjectName('memoryTable')
    self.memory_table.setWordWrap(False)
    self.memory_table.itemSelectionChanged.connect(self.show_selected_memory)
    self.memory_table.doubleClicked.connect(lambda: self.selected_memory(self.edit_memory))
    self.memory_details, self.memory_details_layout = self.card('Memory details')
    self.memory_inspector_row = ResponsiveRow(self, (self.memory_table, self.memory_details), (2, 1))
    self.content_layout.addWidget(self.memory_inspector_row)
    self.memory_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.fill_memories()
    toolbar, toolbar_layout = self.card()
    toolbar_layout.addWidget(action_bar([
        button('Safe export', lambda: self.export_json(self.core.export_memories(), 'memories.json'), icon='download'),
        button('Import memories', self.import_memory_json, icon='upload_file'),
        button('Full encrypted backup', self.backup_memory_database, icon='lock'),
        button('Clean expired memories', self.clean_expired_memories, icon='delete')]))
    toolbar_layout.addWidget(label('Safe JSON exports exclude sensitive categories. Full SQLite backups retain values encrypted for this Windows user.', 'muted'))
    self.content_layout.addWidget(toolbar)



def page_commands(self):
    self.heading('Commands', 'Registered phrases and natural requests for your enabled actions.',
        [button('New command', self.edit_command, True, 'add')])
    types = {'application': 'Application', 'url': 'HTTPS URL', 'routine': 'Workflow routine'}
    filters, filter_layout = self.card()
    self.command_search = QLineEdit(self.command_query)
    self.command_search.setObjectName('commandSearch')
    self.command_search.setPlaceholderText('Search commands, phrases or targets…')
    self.command_types = QComboBox()
    self.command_types.addItem('All types', None)
    for kind, title in types.items(): self.command_types.addItem(title, kind)
    self.command_types.setCurrentIndex(max(0, self.command_types.findData(self.command_type)))
    self.command_states = QComboBox()
    for title, value in [('All states', None), ('Enabled', True), ('Disabled', False)]:
        self.command_states.addItem(title, value)
    self.command_states.setCurrentIndex(max(0, self.command_states.findData(self.command_state)))
    filter_layout.addWidget(ResponsiveRow(self, (self.command_search, self.command_types, self.command_states), (3, 1, 1)))
    counts = self.core.commands()
    filter_layout.addWidget(action_bar([badge(f'Total: {len(counts)}'),
        badge(f"Enabled: {sum(bool(r['enabled']) for r in counts)}", 'success'),
        badge(f"Disabled: {sum(not r['enabled'] for r in counts)}")]))
    self.content_layout.addWidget(filters)
    self.command_table = table = self.table(['Command', 'Type', 'Trigger phrases', 'Target', 'Status', 'Actions'], [])
    table.setObjectName('commandTable')
    table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(5, 112)
    self.content_layout.addWidget(table)
    self.command_action_buttons = ()
    def selected_record():
        row = table.currentRow()
        record = self.command_records[row] if 0 <= row < len(self.command_records) else None
        for control in self.command_action_buttons:
            control.setEnabled(record is not None)
        if self.command_action_buttons:
            self.command_workflow_button.setEnabled(record is not None and record['action_type'] == 'routine')
        if record:
            self.command_selected_id = record['id']
        return record
    def selected(callback):
        record = selected_record()
        if record: self.guard(lambda: callback(record))
    def execute(record):
        self.command_selected_id = record['id']
        result = self.controller.execute(record['phrases'][0], self)
        QMessageBox.information(self, 'Command result', result['message'])
    def remove(record):
        self.confirm('Delete command', 'Delete this command and all its phrases?', lambda: self.core.delete_command(record['id']))
    def toggle(record, enabled):
        self.command_selected_id = record['id']
        if record['action_type'] == 'routine':
            self.core.workflows.set_enabled(record['target'], enabled)
        else:
            self.core.save_command(record['name'], record['action_type'], record['target'], record['phrases'], enabled, record['id'])
    def fill(*_):
        from PyQt6.QtWidgets import QTableWidgetItem
        self.command_query = self.command_search.text()
        self.command_type = self.command_types.currentData()
        self.command_state = self.command_states.currentData()
        query = self.command_query.strip().casefold()
        self.command_records = [r for r in self.core.commands() if
            (self.command_type is None or r['action_type'] == self.command_type) and
            (self.command_state is None or bool(r['enabled']) == self.command_state) and
            query in (' '.join([r['name'], r['target'], *r['phrases']])).casefold()]
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(self.command_records))
        table.clearSelection()
        table.setCurrentCell(-1, -1)
        for row, record in enumerate(self.command_records):
            target = record['target']
            if record['action_type'] == 'application':
                app = self.core.get_registered_application(target)
                if app: target = app.executable_path
            elif record['action_type'] == 'routine':
                routine = self.core.workflows.get(target)
                if routine: target = f"{len(routine['steps'])} automated steps"
            values = [record['name'], types.get(record['action_type'], record['action_type']),
                ' · '.join(record['phrases']), target, '', '']
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value)); item.setToolTip(str(value))
                item.setData(Qt.ItemDataRole.UserRole, record['id'])
                table.setItem(row, column, item)
            enabled = Toggle('On' if record['enabled'] else 'Off')
            enabled.setChecked(bool(record['enabled']))
            enabled.setAccessibleName('Enable ' + record['name'])
            enabled.toggled.connect(lambda state, r=record: self.guard(lambda: toggle(r, state)))
            table.setCellWidget(row, 4, enabled)
            tools = QWidget()
            tools_layout = QHBoxLayout(tools)
            tools_layout.setContentsMargins(2, 2, 2, 2);tools_layout.setSpacing(2)
            for title, glyph, callback in [('Test command', 'play_arrow', execute), ('Edit command', 'edit', self.edit_command), ('Delete command', 'delete', remove)]:
                control = button('', lambda checked=False, r=record, cb=callback: self.guard(lambda: cb(r)), icon=glyph)
                control.setFixedSize(32, 34);control.setMinimumHeight(34)
                control.setToolTip(title);control.setAccessibleName(title + ': ' + record['name'])
                tools_layout.addWidget(control)
            table.setCellWidget(row, 5, tools)
            table.setRowHeight(row, 52)
            if record['id'] == getattr(self, 'command_selected_id', None): table.selectRow(row)
        table.setMinimumHeight(min(420, max(160, 52 * (len(self.command_records) + 1))))
        table.blockSignals(False)
        selected_record()
        from .icons import apply_icons
        apply_icons(table, self.core.app_settings()['theme'])
    table.itemSelectionChanged.connect(selected_record)
    table.doubleClicked.connect(lambda: selected(self.edit_command))
    self.command_search.textChanged.connect(fill)
    self.command_types.currentIndexChanged.connect(fill)
    self.command_states.currentIndexChanged.connect(fill)
    fill()
    delete = button('Delete selected', lambda: selected(remove), icon='delete');delete.setObjectName('danger')
    self.command_workflow_button = button('Edit in Workflows', lambda: selected(lambda r: self.open_workflow(r['target'])), icon='account_tree')
    self.command_action_buttons = (
        button('Edit selected', lambda: selected(self.edit_command), icon='edit'),
        self.command_workflow_button,
        button('Test selected', lambda: selected(execute), icon='play_arrow'), delete)
    self.content_layout.addWidget(action_bar(self.command_action_buttons))
    selected_record()
    self.content_layout.addWidget(label('Reserved: help · remember my name as <name> · what is my name. Memory writes require confirmation.', 'muted'))
    discovery, discovery_layout = self.card('Software Discovery & Scanner')
    self.software_panel = SoftwareDiscoveryPanel(self)
    discovery_layout.addWidget(self.software_panel)
    self.content_layout.addWidget(discovery)


def page_pet_studio(self):
    from .preview import SpritePreview
    self.heading('Pet Studio', 'Companion personalization, geometry and sprite sheet management.',
        [button('Import PNG sheet', lambda: self.guard(self.import_pet), icon='upload_file')])
    profiles = QComboBox()
    records = self.core.profiles()
    for record in records:
        profiles.addItem(record['name'] + (' · active' if record['is_active'] else ''), record['id'])
    active = self.core.active_profile()
    profiles.setCurrentIndex(profiles.findData(active['id']))
    assets = QComboBox()
    for asset in self.core.assets(): assets.addItem(asset['name'], asset['id'])
    name = QLineEdit()
    controls = {}
    for key, low, high in [('size', 96, 400), ('chat_width', 260, 600), ('text_size', 10, 24)]:
        slider = NoScrollSlider(Qt.Orientation.Horizontal);slider.setRange(low, high)
        slider.setObjectName('studio_' + key);controls[key] = slider
    for key in ('always_on_top', 'animations'): controls[key] = Toggle()
    stage, stage_layout = self.card('Companion Appearance & Live Preview')
    preview = SpritePreview()
    chat_preview = label('Try “open notepad” or “what is my name”')
    chat_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chat_preview.setMinimumHeight(42)
    stage_layout.addWidget(preview, alignment=Qt.AlignmentFlag.AlignCenter)
    stage_layout.addWidget(chat_preview, alignment=Qt.AlignmentFlag.AlignCenter)
    stage_layout.addWidget(label('Preview changes stay here until you save and activate the profile.', 'muted'))
    self.content_layout.addWidget(stage)
    def preview_update():
        from PyQt6.QtGui import QColor
        try:
            preview.configure(self.core.asset_path(assets.currentData()), controls['size'].value(), controls['animations'].isChecked())
        except ValueError:
            preview.stop();preview.clear();preview.setText('Preview unavailable')
        color = QColor(DEFAULT_PET['background']);color.setAlphaF(DEFAULT_PET['opacity'])
        chat_preview.setStyleSheet(f'background:rgba({color.red()},{color.green()},{color.blue()},{color.alpha()}); color:white; border-radius:{DEFAULT_PET["radius"]}px; padding:10px 18px; font-size:{controls["text_size"].value()}px;')
        chat_preview.setFixedWidth(controls['chat_width'].value())
    def load_profile():
        record = next(r for r in records if r['id'] == profiles.currentData())
        name.setText(record['name']);assets.setCurrentIndex(assets.findData(record['selected_asset_id']))
        for key, field in controls.items():
            value = record['config'].get(key, DEFAULT_PET.get(key))
            if isinstance(field, QCheckBox): field.setChecked(bool(value))
            else: field.setValue(int(value))
        preview_update()
    identity, identity_layout = self.card('Profile & Identity')
    form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    form.addRow('Profile', profiles);form.addRow('Pet name', name);form.addRow('Pet image', assets)
    identity_layout.addLayout(form)
    identity_layout.addWidget(label('Use the built-in Husky or import a validated horizontal PNG strip.', 'muted'))
    geometry, geometry_layout = self.card('Geometry & Scale')
    for key, title, caption in [('size', 'Pet render size', '96–400 px'),
            ('chat_width', 'Chat bubble width', '260–600 px'), ('text_size', 'Speech text size', '10–24 px')]:
        group = QWidget();group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        line = QHBoxLayout();line.addWidget(label(title), 1)
        val_label = QLabel(str(controls[key].value()));val_label.setFixedWidth(36)
        val_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls[key].valueChanged.connect(lambda val, lbl=val_label: lbl.setText(str(val)))
        line.addWidget(val_label);group_layout.addLayout(line)
        group_layout.addWidget(controls[key]);group_layout.addWidget(label(caption, 'muted'))
        geometry_layout.addWidget(group)
    self.content_layout.addWidget(ResponsiveRow(self, (identity, geometry)))
    behavior, behavior_layout = self.card('Desktop Behavior')
    switches = QFormLayout()
    switches.addRow('Always on top', controls['always_on_top']);switches.addRow('Animations', controls['animations'])
    behavior_layout.addLayout(switches)
    self.content_layout.addWidget(behavior)
    load_profile()
    profiles.currentIndexChanged.connect(load_profile)
    assets.currentIndexChanged.connect(preview_update)
    for field in controls.values():
        if isinstance(field, QCheckBox): field.toggled.connect(preview_update)
        else: field.valueChanged.connect(preview_update)
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

    footer, footer_layout = self.card('PNG Sprite Sheet Requirements')
    footer_layout.addWidget(label('Horizontal strip of 1–64 square frames · 16–512 px per frame · PNG up to 8 MB.', 'muted'))
    footer_layout.addWidget(action_bar([
        button('Save as new profile', lambda: self.guard(lambda: self.core.save_profile(name.text(), assets.currentData(), config())), icon='add'),
        button('Save & activate profile', lambda: self.guard(lambda: self.core.save_profile(name.text(), assets.currentData(), config(profiles.currentData()), profiles.currentData())), True, 'save')]))
    self.content_layout.addWidget(footer)


def page_activity(self):
    self.heading('Activity', 'Registered command executions, separate from your memories.', [button('Clear history', lambda: self.confirm('Clear history', 'Permanently clear all command history?', self.core.clear_history))])
    filters, filter_layout = self.card()
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
    filter_layout.addWidget(ResponsiveRow(self, (status, command, date), (1, 1, 2)))
    filter_layout.addWidget(button('Filter', apply, icon='search'))
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
    self.heading('Settings', 'Application preferences, speech engines and local data management.')
    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(16)
    config = self.core.app_settings()
    is_dark = config.get('theme', 'dark') == 'dark'
    lbl_color = '#e2e8f0' if is_dark else '#1f2937'
    muted_color = '#94a3b8' if is_dark else '#64748b'
    dpr = self.devicePixelRatioF()

    frame = QFrame()
    frame.setObjectName('preferencesCard')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    # Header with gear icon, title, and divider
    header_row = QHBoxLayout()
    header_row.setSpacing(8)
    gear_lbl = QLabel()
    gear_lbl.setPixmap(inline_svg_icon(GEAR_SVG.format(color='#38bdf8' if is_dark else '#2563eb'), 18, dpr).pixmap(18, 18))
    header_lbl = QLabel('GENERAL & SPEECH PREFERENCES')
    header_lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; letter-spacing: 0.5px; color: {'#f1f5f9' if is_dark else '#1f2937'};")
    header_row.addWidget(gear_lbl)
    header_row.addWidget(header_lbl, 1)
    layout.addLayout(header_row)

    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setFrameShadow(QFrame.Shadow.Plain)
    divider.setStyleSheet(f"color: {'#1e293b' if is_dark else '#e2e8f0'}; background-color: {'#1e293b' if is_dark else '#e2e8f0'}; height: 1px; border: none;")
    divider.setFixedHeight(1)
    layout.addWidget(divider)

    # 1. Theme
    theme_top = QHBoxLayout()
    theme_label = QLabel('Theme')
    theme_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {lbl_color};")
    theme_status = QLabel('Dark selected' if config['theme'] == 'dark' else 'Light selected')
    theme_status.setStyleSheet("font-size: 12px; font-weight: 500; color: #38bdf8;")
    theme_top.addWidget(theme_label)
    theme_top.addStretch()
    theme_top.addWidget(theme_status)
    layout.addLayout(theme_top)

    theme = SegmentedControl(is_dark=is_dark)
    moon_act = inline_svg_icon(MOON_SVG.format(color='#ffffff'), 18, dpr)
    moon_inact = inline_svg_icon(MOON_SVG.format(color='#94a3b8' if is_dark else '#64748b'), 18, dpr)
    sun_act = inline_svg_icon(SUN_SVG.format(color='#ffffff'), 18, dpr)
    sun_inact = inline_svg_icon(SUN_SVG.format(color='#94a3b8' if is_dark else '#64748b'), 18, dpr)
    theme.addItem('dark', 'dark', display_text='Dark', icon_active=moon_act, icon_inactive=moon_inact)
    theme.addItem('light', 'light', display_text='Light', icon_active=sun_act, icon_inactive=sun_inact)
    theme.setCurrentText(config['theme'])

    def on_theme_change():
        theme_status.setText(f"{theme.currentText().capitalize()} selected")
    theme.currentIndexChanged.connect(on_theme_change)
    layout.addWidget(theme)

    # 2. Default music player
    music_label = QLabel('Default music player')
    music_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {lbl_color};")
    layout.addWidget(music_label)

    music_player = SegmentedControl(is_dark=is_dark)
    spotify_ic = inline_svg_icon(SPOTIFY_SVG, 20, dpr)
    youtube_ic = inline_svg_icon(YOUTUBE_SVG, 20, dpr)
    music_player.addItem('Spotify', 'spotify', display_text='Spotify', icon=spotify_ic)
    music_player.addItem('YouTube', 'youtube', display_text='YouTube', icon=youtube_ic)
    idx = music_player.findData(config['default_music_player'])
    music_player.setCurrentIndex(idx if idx >= 0 else 0)
    layout.addWidget(music_player)

    # 3. Spotify open using
    spotify_label = QLabel('Spotify open using')
    spotify_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {lbl_color};")
    layout.addWidget(spotify_label)

    spotify_mode = SegmentedControl(is_dark=is_dark)
    lightn_act = inline_svg_icon(LIGHTNING_SVG.format(color='#ffffff'), 18, dpr)
    lightn_inact = inline_svg_icon(LIGHTNING_SVG.format(color='#94a3b8' if is_dark else '#64748b'), 18, dpr)
    globe_act = inline_svg_icon(GLOBE_SVG.format(color='#ffffff'), 18, dpr)
    globe_inact = inline_svg_icon(GLOBE_SVG.format(color='#94a3b8' if is_dark else '#64748b'), 18, dpr)
    spotify_mode.addItem('Auto (App then Web)', 'auto', display_text='Auto (App then Web)', icon_active=lightn_act, icon_inactive=lightn_inact)
    spotify_mode.addItem('Browser Only', 'browser', display_text='Browser Only', icon_active=globe_act, icon_inactive=globe_inact)
    idx = spotify_mode.findData(config['spotify_open_mode'])
    spotify_mode.setCurrentIndex(idx if idx >= 0 else 0)
    layout.addWidget(spotify_mode)

    spotify_notice = QLabel('Spotify opens song search results. Select a song and press Play.')
    spotify_notice.setStyleSheet(f"font-size: 12px; color: {muted_color};")
    spotify_notice.setWordWrap(True)
    layout.addWidget(spotify_notice)

    # 4. Voice Recognition Engine
    voice_label = QLabel('Voice Recognition Engine')
    voice_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {lbl_color};")
    layout.addWidget(voice_label)

    voice_mode = SegmentedControl(is_dark=is_dark)
    voice_mode.addItem('Google Web Speech', 'google', display_text='Google Web Speech')
    voice_mode.addItem('Multi-Language', 'multilingual', display_text='Multi-Language')
    current_voice = config.get('voice_mode', 'google')
    idx = voice_mode.findData(current_voice)
    voice_mode.setCurrentIndex(idx if idx >= 0 else voice_mode.findData('google'))
    layout.addWidget(voice_mode)

    # 5. Google Language
    google_language_container = QWidget()
    google_layout = QVBoxLayout(google_language_container)
    google_layout.setContentsMargins(0, 0, 0, 0)
    google_layout.setSpacing(8)

    google_language_label = QLabel('Google Language')
    google_language_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {lbl_color};")
    google_layout.addWidget(google_language_label)

    google_language = SegmentedControl(is_dark=is_dark)
    dot_act = inline_svg_icon(DOT_SVG.format(color='#ffffff'), 14, dpr)
    dot_inact = inline_svg_icon(DOT_SVG.format(color='#94a3b8' if is_dark else '#64748b'), 14, dpr)
    google_language.addItem('English (India)', 'en-IN', display_text='English (India)', icon_active=dot_act, icon_inactive=dot_inact)
    google_language.addItem('Tamil (India)', 'ta-IN', display_text='தமிழ் (Tamil)')
    idx = google_language.findData(config.get('google_voice_language', 'en-IN'))
    google_language.setCurrentIndex(idx if idx >= 0 else 0)
    google_layout.addWidget(google_language)

    notice_row = QHBoxLayout()
    notice_row.setSpacing(6)
    google_notice_icon = QLabel()
    google_notice_icon.setPixmap(inline_svg_icon(INFO_SVG.format(color='#38bdf8'), 16, dpr).pixmap(16, 16))
    google_notice = QLabel('Sends recorded audio to Google; requires internet')
    google_notice.setStyleSheet(f"font-size: 12px; color: {muted_color};")
    google_notice.setWordWrap(True)
    notice_row.addWidget(google_notice_icon)
    notice_row.addWidget(google_notice, 1)
    google_layout.addLayout(notice_row)

    layout.addWidget(google_language_container)

    def update_google_options():
        visible = voice_mode.currentData() == 'google'
        for w in (google_language_container, google_language_label, google_language, google_notice_icon, google_notice):
            w.setVisible(visible)
    voice_mode.currentIndexChanged.connect(update_google_options)
    update_google_options()

    # Save preferences button
    save_btn = QPushButton('Save preferences')
    save_btn.setObjectName('savePreferencesBtn')
    save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    save_btn.setIcon(inline_svg_icon(SAVE_TRAY_SVG, 20, dpr))
    save_btn.setIconSize(QSize(20, 20))
    save_btn.setFixedHeight(46)
    layout.addWidget(save_btn)

    voice_hotkey = Toggle('Enable Ctrl + Windows for voice input')
    voice_hotkey.setChecked(config.get('voice_hotkey_enabled', False))
    hotkeys, hotkey_layout = self.card('Audio Triggers & Hotkeys')
    hotkey_layout.addWidget(voice_hotkey)
    hotkey_layout.addWidget(label('Hold Ctrl + Windows to speak. Release either key to submit.', 'muted'))
    hotkey_status = QLabel('')
    hotkey_status.setWordWrap(True)
    hotkey_status.setVisible(False)
    def update_hotkey_status(status):
        if not status or 'ready' in status.lower() or status in ('Voice shortcut is disabled.', 'Starting voice shortcut...'):
            hotkey_status.setText('')
            hotkey_status.setVisible(False)
        else:
            hotkey_status.setText(status)
            hotkey_status.setVisible(True)
    update_hotkey_status(getattr(self.controller, 'voice_hotkey_status', ''))
    self.subscribe_page(self.controller.voice_hotkey_status_changed, update_hotkey_status)
    hotkey_layout.addWidget(hotkey_status)

    def do_save():
        self.core.save_settings(dict(
            config,
            default_music_player=music_player.currentData(),
            spotify_open_mode=spotify_mode.currentData(),
            theme=theme.currentText(),
            voice_mode=voice_mode.currentData(),
            google_voice_language=google_language.currentData(),
            voice_hotkey_enabled=voice_hotkey.isChecked()
        ))

    save_btn.clicked.connect(lambda: self.guard(do_save))
    left_layout.addWidget(frame)
    left_layout.addWidget(hotkeys)
    frame, layout = self.card('Local Desktop Search')
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
    left_layout.addWidget(frame)
    left_layout.addStretch()
    frame, layout = self.card('Data Vault')
    layout.addWidget(button('Export configuration', lambda: self.export_json(self.core.export_configuration(), 'configuration.json')))
    layout.addWidget(button('Import configuration', lambda: self.import_json(self.core.import_configuration)))
    layout.addWidget(button('Export memories', lambda: self.export_json(self.core.export_memories(), 'memories.json')))
    layout.addWidget(button('Create database backup', lambda: self.guard(lambda: QMessageBox.information(self, 'Backup created', str(self.core.backup())))))
    layout.addWidget(button('Restore database backup', self.restore_backup))
    layout.addWidget(button('Clear command history', lambda: self.confirm('Clear history', 'Permanently clear command history?', self.core.clear_history)))
    layout.addWidget(label('Imports are validated and do not overwrite matching records. Configuration imports switch the active profile and preferences. Restore creates a recovery snapshot first. Imported pet images must remain in the pets folder; encrypted backups require this Windows user.', 'muted'))
    self.content_layout.addWidget(ResponsiveRow(self, (left, frame), (3, 2)))

