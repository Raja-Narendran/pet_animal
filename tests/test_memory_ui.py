"""Personal Memory Manager interactions use isolated data and mocked launchers."""
import copy
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QFileDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTextEdit

from src.app.manager_window import ManagerWindow
from src.core.application import ApplicationCore
from src.core import secrets


@pytest.fixture
def manager(qtbot, tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    core = ApplicationCore(tmp_path / 'data', launcher)
    window = ManagerWindow(core, MagicMock())
    qtbot.addWidget(window)
    window.navigation.setCurrentRow(1)
    yield window
    window.software_state.shutdown()
    core.listeners.clear()
    window.hide()
    core.close()


def category(manager, sensitive=False):
    return next(c['id'] for c in manager.core.categories() if bool(c['sensitive']) == sensitive)


def create(manager, key, value='A remembered value', **fields):
    return manager.core.memory_service.create_memory(category(manager), key, key, value, **fields)


def select(manager, memory_id):
    index = next(i for i, record in enumerate(manager.memory_records) if record['id'] == memory_id)
    manager.memory_table.selectRow(index)


def modal_save(dialog):
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()


def test_filters_search_metadata_and_manager_never_consume_memories(manager):
    profile = create(manager, 'user.nickname', memory_type='PROFILE', tags=['identity'], aliases=['my nickname'])
    preference = create(manager, 'preferred.browser', 'chrome', memory_type='PREFERENCE')
    disabled = create(manager, 'project.path', 'K:/project', memory_type='KNOWLEDGE', enabled=False)
    create(manager, 'system.private_state', memory_type='SYSTEM')
    assert {r['id'] for r in manager.memory_records} == {profile, preference, disabled}
    manager.memory_search.setText('nickname')
    assert [r['id'] for r in manager.memory_records] == [profile]
    manager.memory_search.clear()
    manager.memory_scopes.setCurrentText('Global')
    manager.memory_states.setCurrentText('Disabled')
    assert [r['id'] for r in manager.memory_records] == [disabled]
    manager.memory_states.setCurrentIndex(0)
    select(manager, profile)
    manager.refresh()
    manager.navigation.setCurrentRow(0)
    manager.navigation.setCurrentRow(1)
    assert manager.core.get_memory(profile)['access_count'] == 0
    assert manager.core.get_memory(preference)['access_count'] == 0
    assert manager.core.get_memory(disabled)['access_count'] == 0
    assert 'Total: 4' in manager.memory_health_label.text()


def test_usage_sorting_and_details_display_provenance(manager):
    first = create(manager, 'user.name', 'Naren', memory_type='PROFILE', tags=['personal'], aliases=['my name'])
    second = create(manager, 'preferred.editor', 'vscode', memory_type='PREFERENCE')
    manager.core.get_memory_by_key('user.name')
    manager.core.get_memory_by_key('user.name')
    manager.core.get_memory_by_key('preferred.editor')
    manager.memory_usage.setCurrentText('Most used')
    assert manager.memory_records[0]['id'] == first
    select(manager, first)
    details = ' '.join(item.text() for item in manager.memory_details.findChildren(QLabel))
    for value in ('Global', 'Last used', 'Usage count'):
        assert value in details
    assert manager.memory_detail_value.toPlainText() == 'Naren'
    assert manager.core.get_memory(first)['access_count'] == 2
    assert manager.core.get_memory(second)['access_count'] == 1


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI')
def test_sensitive_details_and_edits_require_explicit_reveal(manager, monkeypatch):
    memory_id = manager.core.memory_service.create_memory(category(manager, True), 'Private value', 'private.note', 'private-ui-secret')
    encrypted = manager.core.db.execute('SELECT memory_value FROM memories WHERE id=?', (memory_id,)).fetchone()[0]
    decrypt = MagicMock(wraps=secrets.decrypt)
    monkeypatch.setattr(secrets, 'decrypt', decrypt)
    select(manager, memory_id)
    assert manager.memory_detail_value.toPlainText() == '••••••••'
    assert decrypt.call_count == 0
    def edit_title():
        dialog = QApplication.activeModalWidget()
        assert not dialog.findChild(QTextEdit, 'memoryValue').toPlainText()
        assert decrypt.call_count == 0
        dialog.findChild(QLineEdit, 'memoryTitle').setText('Updated private title')
        modal_save(dialog)
    QTimer.singleShot(0, edit_title)
    manager.edit_memory(manager.core.get_memory(memory_id))
    assert decrypt.call_count == 0
    assert manager.core.db.execute('SELECT memory_value FROM memories WHERE id=?', (memory_id,)).fetchone()[0] == encrypted
    select(manager, memory_id)
    manager.reveal_memory_value(memory_id)
    assert manager.memory_detail_value.toPlainText() == 'private-ui-secret'
    assert decrypt.call_count == 1
    manager.reveal_memory_value(memory_id)
    assert manager.memory_detail_value.toPlainText() == '••••••••'
    assert decrypt.call_count == 1
    assert manager.core.get_memory(memory_id)['access_count'] == 0



def test_memory_value_and_metadata_render_as_literal_text(manager):
    from PyQt6.QtCore import Qt
    literal = '<b>private</b> & <tag>'
    memory_id = manager.core.memory_service.create_memory(category(manager), literal, 'note.literal', literal,
                                                          memory_type='NOTE', aliases=['<b>alias</b>'])
    select(manager, memory_id)
    assert manager.memory_detail_value.toPlainText() == literal
    title_label = next(item for item in manager.memory_details.findChildren(QLabel) if item.text() == literal)
    assert title_label.textFormat() == Qt.TextFormat.PlainText
    def inspect_then_cancel():
        dialog = QApplication.activeModalWidget()
        assert dialog.findChild(QTextEdit, 'memoryValue').toPlainText() == literal
        dialog.reject()
    QTimer.singleShot(0, inspect_then_cancel)
    manager.edit_memory(manager.core.get_memory(memory_id))
    record = manager.core.get_memory(memory_id)
    assert record['memory_value'] == literal
    assert record['access_count'] == 0


def test_add_dialog_saves_metadata_tags_and_aliases(manager):
    def add():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QLineEdit, 'memoryTitle').setText('My browser')
        assert dialog.findChild(QLineEdit, 'memoryKey').text() == 'my.browser'
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('chrome')
        dialog.findChild(QComboBox, 'memoryScope').setCurrentText('Global')
        modal_save(dialog)
    QTimer.singleShot(0, add)
    manager.edit_memory()
    record = manager.core.get_memory_by_key('my.browser', consume=False)
    assert record['memory_scope'] == 'GLOBAL'
    assert record['memory_value'] == 'chrome'


def test_edit_conflicting_value_cancel_then_confirm(manager, monkeypatch):
    memory_id = create(manager, 'preferred.browser', 'chrome', memory_type='PREFERENCE')
    questions = []
    def reject(*args):
        questions.append(args[2])
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, 'question', reject)
    def edit_cancel():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('edge')
        modal_save(dialog)
        dialog.reject()
    QTimer.singleShot(0, edit_cancel)
    manager.edit_memory(manager.core.get_memory(memory_id))
    assert manager.core.get_memory(memory_id)['memory_value'] == 'chrome'
    assert questions and 'conflicts' in questions[0]
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    def edit_confirm():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('edge')
        modal_save(dialog)
    QTimer.singleShot(0, edit_confirm)
    manager.edit_memory(manager.core.get_memory(memory_id))
    assert manager.core.get_memory(memory_id)['memory_value'] == 'edge'



def test_details_toggle_and_delete_are_user_controlled(manager, monkeypatch):
    memory_id = create(manager, 'project.description', source='IMPORT')
    select(manager, memory_id)
    next(b for b in manager.memory_details.findChildren(QPushButton) if b.text() == 'Disable').click()
    disabled = manager.core.get_memory(memory_id)
    assert not disabled['enabled']
    assert disabled['source'] == 'IMPORT'
    select(manager, memory_id)
    next(b for b in manager.memory_details.findChildren(QPushButton) if b.text() == 'Enable').click()
    assert manager.core.get_memory(memory_id)['enabled']
    select(manager, memory_id)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    next(b for b in manager.memory_details.findChildren(QPushButton) if b.text() == 'Delete memory').click()
    assert manager.core.get_memory(memory_id) is not None
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    next(b for b in manager.memory_details.findChildren(QPushButton) if b.text() == 'Delete memory').click()
    assert manager.core.get_memory(memory_id) is None


def test_relationship_dialog_and_deletion(manager, monkeypatch):
    first = create(manager, 'project.pet_animal', 'Pet Animal')
    second = create(manager, 'preferred.editor', 'vscode', memory_type='PREFERENCE')
    def add():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QLineEdit).setText('uses')
        target = dialog.findChild(QComboBox)
        target.setCurrentIndex(target.findData(second))
        modal_save(dialog)
    QTimer.singleShot(0, add)
    manager.add_memory_relationship(manager.core.get_memory(first))
    relationships = manager.core.memory_service.get_relationships(first)
    assert len(relationships) == 1
    assert relationships[0]['target_memory_id'] == second
    manager.core.memory_service.delete_relationship(relationships[0]['id'])
    assert manager.core.memory_service.get_relationships(first) == []


def test_activity_patterns_not_present_in_memory_ui(manager):
    assert not hasattr(manager, 'render_habit_candidates')
    assert not hasattr(manager, 'analyze_memory_habits')
    assert not hasattr(manager, 'confirm_habit_candidate')
    assert not hasattr(manager, 'habit_candidates')
    assert not hasattr(manager.core, 'habit_engine')


def test_expired_filter_and_cleanup_require_confirmation(manager, monkeypatch):
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    memory_id = create(manager, 'context.old', memory_type='CONTEXT', memory_scope='TEMPORARY', lifetime='temporary', expires_at=expired)
    create(manager, 'user.nickname', memory_type='PROFILE')
    state_options = [manager.memory_states.itemText(i) for i in range(manager.memory_states.count())]
    assert state_options == ['All states', 'Enabled', 'Disabled']
    assert 'Expired' not in state_options
    assert 'Sensitive' not in state_options
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    manager.clean_expired_memories()
    assert manager.core.get_memory(memory_id) is not None
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    manager.clean_expired_memories()
    assert manager.core.get_memory(memory_id) is None


def test_import_summary_cancel_then_confirm_conflicts(manager, monkeypatch, tmp_path):
    memory_id = create(manager, 'preferred.browser', 'chrome', memory_type='PREFERENCE')
    payload = copy.deepcopy(manager.core.export_memories())
    payload['memories'][0]['memory_value'] = 'edge'
    new = copy.deepcopy(payload['memories'][0])
    new['memory_key'] = 'preferred.editor'
    new['memory_value'] = 'vscode'
    new['aliases'] = []
    payload['memories'].append(new)
    path = tmp_path / 'import.json'
    path.write_text(json.dumps(payload), encoding='utf8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    questions = []
    def reject(*args):
        questions.append(args[2])
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, 'question', reject)
    manager.import_memory_json()
    assert manager.core.get_memory(memory_id)['memory_value'] == 'chrome'
    assert manager.core.get_memory_by_key('preferred.editor', consume=False) is None
    assert '1 new memories' in questions[0] and '1 conflicts' in questions[0]
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    manager.import_memory_json()
    assert manager.core.get_memory(memory_id)['memory_value'] == 'edge'
    assert manager.core.get_memory_by_key('preferred.editor', consume=False)['memory_value'] == 'vscode'


def test_invalid_import_blocks_confirmation_and_mutation(manager, monkeypatch, tmp_path):
    create(manager, 'user.nickname', 'Nova', memory_type='PROFILE')
    payload = manager.core.export_memories()
    payload['memories'][0]['importance'] = 5
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(payload), encoding='utf8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    warning = MagicMock()
    question = MagicMock()
    monkeypatch.setattr(QMessageBox, 'warning', warning)
    monkeypatch.setattr(QMessageBox, 'question', question)
    manager.import_memory_json()
    assert warning.call_count == 1
    assert '1 invalid records' in warning.call_args.args[2]
    assert not question.called
    assert len(manager.core.memories()) == 1


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI')
def test_safe_export_and_full_backup_preserve_security(manager, monkeypatch, tmp_path):
    create(manager, 'user.nickname', 'Nova', memory_type='PROFILE')
    private = manager.core.memory_service.create_memory(category(manager, True), 'Private note', 'private.note', 'private-backup-secret')
    exported = tmp_path / 'memories.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(exported), ''))
    manager.export_json(manager.core.export_memories(), 'memories.json')
    payload = json.loads(exported.read_text(encoding='utf8'))
    assert payload['version'] == 2
    assert [r['memory_key'] for r in payload['memories']] == ['user.nickname']
    assert 'private-backup-secret' not in exported.read_text(encoding='utf8')
    backup = tmp_path / 'full-memory.db'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(backup), ''))
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    manager.backup_memory_database()
    with sqlite3.connect(backup) as database:
        encrypted = database.execute('SELECT memory_value FROM memories WHERE id=?', (private,)).fetchone()[0]
    assert encrypted.startswith('dpapi:')
    assert 'private-backup-secret' not in encrypted


def test_add_memory_default_title_options_and_existing_filtering(manager):
    # In fresh state, all 5 defaults + Custom should be present
    options_found = []
    def inspect_defaults():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        options = [combo.itemText(i) for i in range(combo.count())]
        options_found.extend(options)
        dialog.reject()

    QTimer.singleShot(0, inspect_defaults)
    manager.edit_memory()
    assert options_found == ['Name', 'Address', 'IDs', 'Mobile number', 'Email ID', 'Custom']

    # Add Name
    def add_name():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        combo.setCurrentText('Name')
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('Raja Naren')
        modal_save(dialog)

    QTimer.singleShot(0, add_name)
    manager.edit_memory()
    assert manager.core.get_memory_by_key('user.name', consume=False)['memory_value'] == 'Raja Naren'

    # Now Name should be absent from options
    options_after_name = []
    def inspect_after_name():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        options_after_name.extend([combo.itemText(i) for i in range(combo.count())])
        dialog.reject()

    QTimer.singleShot(0, inspect_after_name)
    manager.edit_memory()
    assert 'Name' not in options_after_name
    assert options_after_name == ['Address', 'IDs', 'Mobile number', 'Email ID', 'Custom']

    # Add Address
    def add_address():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        combo.setCurrentText('Address')
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('123 Main Street')
        modal_save(dialog)

    QTimer.singleShot(0, add_address)
    manager.edit_memory()
    assert manager.core.get_memory_by_key('address', consume=False)['memory_value'] == '123 Main Street'

    # Add Email ID
    def add_email():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        combo.setCurrentText('Email ID')
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('naren@example.com')
        modal_save(dialog)

    QTimer.singleShot(0, add_email)
    manager.edit_memory()
    assert manager.core.get_memory_by_key('email.id', consume=False)['memory_value'] == 'naren@example.com'

    # Now Name, Address, and Email ID should ALL be excluded from options
    options_after_all_three = []
    def inspect_after_all():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        options_after_all_three.extend([combo.itemText(i) for i in range(combo.count())])
        dialog.reject()

    QTimer.singleShot(0, inspect_after_all)
    manager.edit_memory()
    assert options_after_all_three == ['IDs', 'Mobile number', 'Custom']


def test_add_memory_id_asks_its_title(manager):
    def add_passport():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, 'memoryTitleOption')
        combo.setCurrentText('IDs')
        id_input = dialog.findChild(QLineEdit, 'memoryIdTitle')
        assert id_input.isVisible()
        id_input.setText('Passport')
        assert dialog.findChild(QLineEdit, 'memoryKey').text() == 'passport'
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('Z1234567')
        modal_save(dialog)

    QTimer.singleShot(0, add_passport)
    manager.edit_memory()
    record = manager.core.get_memory_by_key('passport', consume=False)
    assert record is not None
    assert record['title'] == 'Passport'
    assert record['memory_value'] == 'Z1234567'


def test_add_memory_defaults_only_for_personal_category(manager):
    def inspect_category_switch():
        dialog = QApplication.activeModalWidget()
        cat_combo = dialog.findChild(QComboBox, 'memoryCategory')
        title_option = dialog.findChild(QComboBox, 'memoryTitleOption')
        title_input = dialog.findChild(QLineEdit, 'memoryTitle')

        # Initially Personal Information is active: default options visible
        assert 'personal' in cat_combo.currentText().lower()
        assert title_option.isVisible()

        # Switch to Important Notes category: default options should NOT be visible, regular title input visible
        cat_combo.setCurrentText('Important Notes')
        assert not title_option.isVisible()
        assert title_input.isVisible()
        title_input.setText('Sprint Goals')
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('Ship Pet Animal 2.0')
        modal_save(dialog)

    QTimer.singleShot(0, inspect_category_switch)
    manager.edit_memory()
    record = manager.core.get_memory_by_key('sprint.goals', consume=False)
    assert record is not None
    assert record['title'] == 'Sprint Goals'
    assert record['memory_value'] == 'Ship Pet Animal 2.0'


def test_add_memory_password_category_asks_website_or_app_name(manager):
    def inspect_password_category():
        dialog = QApplication.activeModalWidget()
        cat_combo = dialog.findChild(QComboBox, 'memoryCategory')
        title_option = dialog.findChild(QComboBox, 'memoryTitleOption')
        password_app = dialog.findChild(QLineEdit, 'memoryPasswordApp')
        title_input = dialog.findChild(QLineEdit, 'memoryTitle')

        # Switch to Password category
        cat_combo.setCurrentText('Password')
        assert not title_option.isVisible()
        assert not title_input.isVisible()
        assert password_app.isVisible()

        # Enter website or app name
        password_app.setText('Office')
        assert dialog.findChild(QLineEdit, 'memoryKey').text() == 'office.password'
        dialog.findChild(QTextEdit, 'memoryValue').setPlainText('SuperSecret999!')
        modal_save(dialog)

    QTimer.singleShot(0, inspect_password_category)
    manager.edit_memory()
    record = manager.core.get_memory_by_key('office.password', consume=False, reveal=True)
    assert record is not None
    assert record['title'] == 'Office Password'
    assert record['memory_value'] == 'SuperSecret999!'


def test_add_memory_card_category_asks_card_number_expiry_and_cvv(manager):
    def inspect_card_category():
        dialog = QApplication.activeModalWidget()
        cat_combo = dialog.findChild(QComboBox, 'memoryCategory')
        title_option = dialog.findChild(QComboBox, 'memoryTitleOption')
        password_app = dialog.findChild(QLineEdit, 'memoryPasswordApp')
        card_title = dialog.findChild(QLineEdit, 'memoryCardTitle')
        card_num = dialog.findChild(QLineEdit, 'memoryCardNumber')
        card_exp = dialog.findChild(QLineEdit, 'memoryCardExpiry')
        card_cvv = dialog.findChild(QLineEdit, 'memoryCardCvv')
        val_edit = dialog.findChild(QTextEdit, 'memoryValue')

        # Switch to Credit and Debit card details category
        cat_combo.setCurrentText('Credit and Debit card details')
        assert not title_option.isVisible()
        assert not password_app.isVisible()
        assert not val_edit.isVisible()
        assert card_title.isVisible()
        assert card_num.isVisible()
        assert card_exp.isVisible()
        assert card_cvv.isVisible()

        # Enter details
        card_title.setText('SBI Debit')
        assert dialog.findChild(QLineEdit, 'memoryKey').text() == 'sbi.debit.card'
        card_num.setText('4532 1111 2222 3333')
        card_exp.setText('08/29')
        card_cvv.setText('456')
        modal_save(dialog)

    QTimer.singleShot(0, inspect_card_category)
    manager.edit_memory()
    record = manager.core.get_memory_by_key('sbi.debit.card', consume=False, reveal=True)
    assert record is not None
    assert record['title'] == 'SBI Debit Card'
    assert record['memory_value'] == "Card Number: 4532 1111 2222 3333\nExpiry Date: 08/29\nCVV Number: 456"
    assert record['sensitive'] == 1


def test_add_memory_card_category_validation(manager, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, message: warnings.append(message))

    # Test missing card number
    def test_missing_card_num():
        dialog = QApplication.activeModalWidget()
        cat_combo = dialog.findChild(QComboBox, 'memoryCategory')
        cat_combo.setCurrentText('Credit and Debit card details')
        card_title = dialog.findChild(QLineEdit, 'memoryCardTitle')
        card_title.setText('HDFC Card')
        modal_save(dialog)
        assert any('Please enter the card number' in w for w in warnings)
        dialog.reject()

    QTimer.singleShot(0, test_missing_card_num)
    manager.edit_memory()

    # Test missing expiry date
    warnings.clear()
    def test_missing_expiry():
        dialog = QApplication.activeModalWidget()
        cat_combo = dialog.findChild(QComboBox, 'memoryCategory')
        cat_combo.setCurrentText('Credit and Debit card details')
        dialog.findChild(QLineEdit, 'memoryCardTitle').setText('HDFC Card')
        dialog.findChild(QLineEdit, 'memoryCardNumber').setText('1234 5678 9012 3456')
        modal_save(dialog)
        assert any('Please enter the expiry date' in w for w in warnings)
        dialog.reject()

    QTimer.singleShot(0, test_missing_expiry)
    manager.edit_memory()

    # Test missing CVV
    warnings.clear()
    def test_missing_cvv():
        dialog = QApplication.activeModalWidget()
        cat_combo = dialog.findChild(QComboBox, 'memoryCategory')
        cat_combo.setCurrentText('Credit and Debit card details')
        dialog.findChild(QLineEdit, 'memoryCardTitle').setText('HDFC Card')
        dialog.findChild(QLineEdit, 'memoryCardNumber').setText('1234 5678 9012 3456')
        dialog.findChild(QLineEdit, 'memoryCardExpiry').setText('12/28')
        modal_save(dialog)
        assert any('Please enter the CVV number' in w for w in warnings)
        dialog.reject()

    QTimer.singleShot(0, test_missing_cvv)
    manager.edit_memory()



def test_edit_memory_card_category_reveal_and_modify(manager, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    card_cat = next(c['id'] for c in manager.core.categories() if 'card' in c['name'].lower())
    saved_val = "Card Number: 5555 4444 3333 2222\nExpiry Date: 04/30\nCVV Number: 789"
    mem_id = manager.core.memory_service.create_memory(card_cat, 'ICICI Visa Card', 'icici.visa.card', saved_val)


    def edit_card():
        dialog = QApplication.activeModalWidget()
        card_num = dialog.findChild(QLineEdit, 'memoryCardNumber')
        card_exp = dialog.findChild(QLineEdit, 'memoryCardExpiry')
        card_cvv = dialog.findChild(QLineEdit, 'memoryCardCvv')
        val_edit = dialog.findChild(QTextEdit, 'memoryValue')

        # Before reveal, fields should not show secret
        assert not val_edit.toPlainText()
        assert not card_num.text()

        # Reveal
        buttons = dialog.findChildren(QPushButton)
        reveal_btn = next((b for b in buttons if 'Reveal' in b.text()), None)
        assert reveal_btn is not None
        reveal_btn.click()

        # After reveal, fields are populated
        assert card_num.text() == '5555 4444 3333 2222'
        assert card_exp.text() == '04/30'
        assert card_cvv.text() == '789'

        # Modify CVV
        card_cvv.setText('999')
        modal_save(dialog)

    QTimer.singleShot(0, edit_card)
    manager.edit_memory(manager.core.get_memory(mem_id))

    updated = manager.core.get_memory(mem_id, reveal=True)
    assert updated['memory_value'] == "Card Number: 5555 4444 3333 2222\nExpiry Date: 04/30\nCVV Number: 999"




