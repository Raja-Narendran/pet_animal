"""Manager review controls; the discovery worker never touches SQLite."""
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTextEdit, QCheckBox
from .manager_ui.widgets import ComboBox as QComboBox, button, label, actions
from ..services.software_discovery import SoftwareDiscoveryService, ApplicationValidator, ValidationStatus
from ..services.software_discovery.validator import canonical_path


class SoftwareDiscoveryWorker(QThread):
    completed = pyqtSignal(object, str)

    def __init__(self, service, parent):
        super().__init__(parent)
        self.service = service

    def run(self):
        try:
            results = self.service.discover(cancelled=self.isInterruptionRequested)
            message = f'{len(results)} applications detected.'
            if self.service.errors:
                message += ' Some sources were unavailable: ' + ', '.join(self.service.errors)
            self.completed.emit(results, message)
        except Exception:
            self.completed.emit([], 'Discovery failed. Try Refresh Installed Software again.')


class SoftwareDiscoveryState(QObject):
    updated = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.core = parent.core
        self.results = []
        self.message = 'Refresh to detect and add all valid applications with launch commands.'
        self.worker = None
        self.busy = False

    def start(self):
        if self.busy:
            return
        self.busy = True
        self.message = 'Scanning installed software…'
        self.worker = SoftwareDiscoveryWorker(SoftwareDiscoveryService(), self)
        self.worker.completed.connect(self._complete)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.updated.emit()

    def _complete(self, results, message):
        self.results, self.message = results, message
        if results:
            summary = self.core.register_discovered_applications(results)
            self.message = (message + f" {summary['added']} added; {summary['already_added']} already added; "
                            f"{summary['commands_created']} launch commands created; {summary['invalid']} invalid; "
                            f"{summary['failed']} could not be added.")

    def _finished(self):
        if self.worker is None:
            return
        self.busy = False
        self.worker.deleteLater()
        self.worker = None
        self.updated.emit()

    def shutdown(self):
        if self.worker is not None:
            self.worker.completed.disconnect()
            self.worker.finished.disconnect()
            self.worker.requestInterruption()
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None
            self.busy = False


class SoftwareDiscoveryPanel(QWidget):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager, self.core, self.state = manager, manager.core, manager.software_state
        self.query, self.filter = '', 'All'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        registered, discovered = QWidget(), QWidget()
        tabs.addTab(registered, 'Applications')
        tabs.addTab(discovered, 'Discover Software')
        known_layout, scan_layout = QVBoxLayout(registered), QVBoxLayout(discovered)
        self.registered_table = self._table(['Application', 'Executable', 'Aliases', 'Status'])
        known_layout.addWidget(self.registered_table)
        known_actions = []
        known_actions.append(button('Enable / Disable', lambda: self._selected_application(self._toggle), icon='check_circle'))
        known_actions.append(button('Rename / Edit aliases', lambda: self._selected_application(self._edit), icon='edit'))
        known_actions.append(button('Remove', lambda: self._selected_application(self._remove), icon='delete'))
        known_layout.addWidget(actions(known_actions))
        known_layout.addWidget(label('Use New command above to configure phrases for any approved application.', 'muted'))
        controls = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search application name or publisher…')
        self.search.textChanged.connect(self._search)
        controls.addWidget(self.search, 1)
        self.filter_box = QComboBox()
        self.filter_box.addItems(['All', 'Launchable', 'Already Added', 'Needs Review', 'Invalid'])
        self.filter_box.currentTextChanged.connect(self._filter)

        self.refresh_button = button('Refresh Installed Software', self.state.start, icon='refresh')
        self.refresh_button.setToolTip('Scan installed software and add all valid applications with launch commands.')
        controls.addWidget(actions([self.filter_box, self.refresh_button]))
        scan_layout.addLayout(controls)
        self.status = label(self.state.message, 'muted')
        scan_layout.addWidget(self.status)
        self.discovery_table = self._table(['Application', 'Publisher / version', 'Executable', 'Source', 'Status'])
        scan_layout.addWidget(self.discovery_table)
        self.add_button = button('Add to Pet Animal', self._approve_selected, True)
        scan_layout.addWidget(self.add_button)
        self.discovery_table.itemSelectionChanged.connect(self._selection_changed)
        scan_layout.addWidget(label('Refresh adds all valid applications automatically. Unsupported entries are skipped; existing application settings are preserved.', 'muted'))
        self.manager.subscribe_page(self.state.updated, self.render)
        self.render()

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setWordWrap(False)
        table.setShowGrid(False)
        table.setMinimumWidth(0)
        table.setMinimumHeight(210)
        return table

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or '—'))
                item.setToolTip(str(value or ''))
                table.setItem(row, column, item)
            table.setRowHeight(row, 48)

    def _search(self, value):
        self.query = value.casefold()
        self.render()

    def _filter(self, value):
        self.filter = value
        self.render()

    def render(self):
        self.applications = self.core.list_registered_applications()
        paths = {canonical_path(app.executable_path) for app in self.applications}
        def added(candidate):
            return bool(candidate.executable_path and canonical_path(candidate.executable_path) in paths)
        def keep(candidate):
            if self.query not in (candidate.name + ' ' + (candidate.publisher or '')).casefold():
                return False
            return (self.filter == 'All' or self.filter == 'Already Added' and added(candidate)
                    or self.filter == 'Launchable' and candidate.launchable and not added(candidate)
                    or self.filter == 'Needs Review' and candidate.validation_status == ValidationStatus.REQUIRES_REVIEW
                    or self.filter == 'Invalid' and not candidate.launchable and candidate.validation_status != ValidationStatus.REQUIRES_REVIEW)
        self.candidates = [candidate for candidate in self.state.results if keep(candidate)]
        self._fill(self.registered_table, [(app.name, app.executable_path, ', '.join(app.aliases),
            'Needs repair' if app.needs_repair or ApplicationValidator.validate_registered_path(app.executable_path)[0] != ValidationStatus.VALID
            else 'Enabled' if app.enabled else 'Disabled') for app in self.applications])
        self._fill(self.discovery_table, [(candidate.name, ' / '.join(filter(None, [candidate.publisher, candidate.version])),
            candidate.executable_path, ', '.join(source.value for source in candidate.sources),
            'Already Added' if added(candidate) else candidate.validation_status.value) for candidate in self.candidates])
        self.status.setText(self.state.message)
        self.refresh_button.setEnabled(not self.state.busy)
        self._selection_changed()

    def _selection_changed(self):
        index = self.discovery_table.currentRow()
        candidate = self.candidates[index] if 0 <= index < len(self.candidates) else None
        already_added = candidate and any(canonical_path(app.executable_path) == canonical_path(candidate.executable_path) for app in self.applications)
        self.add_button.setEnabled(bool(candidate and candidate.launchable and not already_added and not self.state.busy))

    def _selected_application(self, callback):
        index = self.registered_table.currentRow()
        if 0 <= index < len(self.applications):
            self.manager.guard(lambda: callback(self.applications[index]))

    def _toggle(self, app):
        self.core.set_application_enabled(app.id, not app.enabled)

    def _remove(self, app):
        self.manager.confirm('Remove application', f'Remove {app.name} from Pet Animal? Its commands will be disabled. Installed software stays on your computer.',
                             lambda: self.core.unregister_application(app.id))

    def _edit(self, app):
        dialog, form, buttons = self.manager.dialog('Application details')
        name, aliases = QLineEdit(app.name), QTextEdit('\n'.join(app.aliases))
        aliases.setMaximumHeight(130)
        form.addRow('Display name', name)
        form.addRow('Aliases, one per line', aliases)
        form.addRow(buttons)
        def save():
            self.core.update_application(app.id, name.text(), aliases.toPlainText().splitlines())
            dialog.accept()
        buttons.accepted.connect(lambda: self.manager.guard(save))
        dialog.exec()

    def _approve_selected(self):
        index = self.discovery_table.currentRow()
        if not 0 <= index < len(self.candidates):
            return
        candidate = self.candidates[index]
        if not candidate.launchable:
            return
        dialog, form, buttons = self.manager.dialog('Approve application')
        form.addRow(label(candidate.name))
        form.addRow('Executable', label(candidate.executable_path))
        form.addRow('Publisher', label(candidate.publisher or 'Unknown'))
        aliases = QTextEdit(candidate.name.casefold())
        aliases.setMaximumHeight(90)
        form.addRow('Aliases, one per line', aliases)
        create = QCheckBox('Create a command for this application')
        create.setChecked(True)
        form.addRow(create)
        name = QLineEdit('Open ' + candidate.name)
        phrases = QTextEdit('\n'.join(verb + ' ' + candidate.name.casefold() for verb in ('open', 'launch', 'start')))
        phrases.setMaximumHeight(110)
        form.addRow('Command name', name)
        form.addRow('Phrases, one per line', phrases)
        create.toggled.connect(name.setEnabled)
        create.toggled.connect(phrases.setEnabled)
        buttons.button(buttons.StandardButton.Save).setText('Approve and add')
        form.addRow(buttons)
        def save():
            self.core.register_application(candidate, aliases.toPlainText().splitlines(), name.text(),
                [phrase.strip() for phrase in phrases.toPlainText().splitlines() if phrase.strip()] if create.isChecked() else None)
            dialog.accept()
        buttons.accepted.connect(lambda: self.manager.guard(save))
        dialog.exec()
