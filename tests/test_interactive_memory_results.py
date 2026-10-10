"""Memory phrase recognition, private results and actual Qt clipboard interactions."""
import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from src.commands.interpreter import IntentType, RuleBasedIntentInterpreter
from src.config.settings import settings
from src.core.application import ApplicationCore
from src.core.memory.conversation import mask_password


@pytest.fixture
def core(tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    instance = ApplicationCore(tmp_path / 'data', launcher)
    yield instance
    instance.close()


def password(core, name='Google', value='1234567098', **metadata):
    category = next(row['id'] for row in core.categories() if row['name'] == 'Password')
    return core.save_memory(category, name + ' Password', name.lower().replace(' ', '.') + '.password',
                            value, **metadata)


def card(core, name='SBI Debit', value=None, **metadata):
    category = next(row['id'] for row in core.categories() if row['name'] == 'Credit and Debit card details')
    return core.save_memory(category, name, name.lower().replace(' ', '.') + '.card',
        value or 'Card Number: 4532 1111 2222 3333\nExpiry Date: 08/29\nCVV Number: 456', **metadata)


@pytest.mark.parametrize('phrase,kind,action', [
    ('my google password', 'password', 'LOOKUP'),
    ("What is my Google's password?", 'password', 'LOOKUP'),
    ('Please show me my office password', 'password', 'LOOKUP'),
    ('password for google', 'password', 'LOOKUP'),
    ('list my passwords', 'password', 'LIST'),
    ('show me all my passwords', 'password', 'LIST'),
    ('list my card details', 'card', 'LIST'),
    ('show my credit and debit cards', 'card', 'LIST'),
    ('my SBI debit card', 'card', 'LOOKUP'),
    ('show me my SBI debit card details', 'card', 'LOOKUP'),
    ('my SBI debit card number', 'card', 'LOOKUP'),
    ('CVV of my SBI debit card', 'card', 'LOOKUP'),
    ('my SBI debit card expiry date', 'card', 'LOOKUP'),
])
def test_phrases(phrase, kind, action):
    parsed = RuleBasedIntentInterpreter().interpret(phrase)
    assert parsed.matched and parsed.intent.intent == IntentType.MEMORY_QUERY
    assert parsed.intent.action == action
    assert (parsed.intent.target if action == 'LIST' else dict(parsed.intent.filters)['kind']) == kind


@pytest.mark.parametrize('phrase', ['do not show my google password', 'never list my passwords'])
def test_negation_does_not_retrieve(core, phrase):
    password(core)
    assert not core.execute(phrase)['success']
    assert core.memory_conversation.token is None


def test_named_password_semi_masked_with_full_copy_and_no_plaintext_payload(core):
    memory_id = password(core)
    before = core.db.total_changes
    assert core.interpret('my google password').matched
    assert core.db.total_changes == before
    result = core.execute('my google password')
    assert result['memory_view'] == 'detail'
    assert result['memory_items'][0]['preview'] == '123****098'
    assert '1234567098' not in json.dumps(result)
    assert '1234567098' not in repr(core.memory_conversation.__dict__)
    ciphertext = core.db.execute('SELECT memory_value FROM memories WHERE id=?', (memory_id,)).fetchone()[0]
    assert ciphertext.startswith('dpapi:') and '1234567098' not in ciphertext
    assert core.memory_conversation.copy_value(result['memory_token'], memory_id, 'value') == '1234567098'
    assert core.get_memory(memory_id)['memory_value'] == '••••••••'
    assert not core.history() and not core.launcher.mock_calls


@pytest.mark.parametrize('value', ['1', '123', '123456', '1234567', '123456789', '1234567890'])
def test_short_password_masks_never_show_entire_secret(value):
    masked = mask_password(value)
    assert value not in masked and '****' in masked
    if len(value) <= 6:
        assert masked == '****'


def test_password_list_never_decrypts_or_counts_access(core, monkeypatch):
    google = password(core)
    office = password(core, 'Office', 'OfficeSecret')
    decrypt = MagicMock(side_effect=AssertionError('Listings must not decrypt'))
    monkeypatch.setattr('src.core.secrets.decrypt', decrypt)
    result = core.execute('list my passwords')
    assert [row['title'] for row in result['memory_items']] == ['Google Password', 'Office Password']
    assert all(row['copy_field'] == 'value' and row['preview'] == '' for row in result['memory_items'])
    assert core.get_memory(google)['access_count'] == core.get_memory(office)['access_count'] == 0
    assert not core.history()
    decrypt.assert_not_called()


def test_cards_list_select_and_copy_individual_fields(core):
    first, second = card(core), card(core, 'HDFC Credit')
    result = core.execute('list my card details')
    assert len(result['memory_items']) == 2
    assert all(row['copy_field'] is None for row in result['memory_items'])
    token = result['memory_token']
    with pytest.raises(ValueError, match='copy button'):
        core.memory_conversation.copy_value(token, first, 'cvv')
    details = core.memory_conversation.select(token, first)
    assert details['memory_can_back']
    assert [row['title'] for row in details['memory_items']] == ['Card number', 'CVV', 'Expiry']
    assert details['memory_items'][0]['preview'] == '**** 3333'
    assert details['memory_items'][1]['preview'] == '****'
    for field, value in [('card_number', '4532 1111 2222 3333'), ('cvv', '456'), ('expiry', '08/29')]:
        assert core.memory_conversation.copy_value(token, first, field) == value
        assert value not in json.dumps(details)
    back = core.memory_conversation.list(token)
    assert back['memory_view'] == 'list'
    with pytest.raises(ValueError, match='copy button'):
        core.memory_conversation.copy_value(token, first, 'cvv')
    assert not core.history() and not core.launcher.mock_calls


@pytest.mark.parametrize('phrase,field', [
    ('my sbi debit card number', 'card_number'),
    ('my sbi debit cvv', 'cvv'),
    ('expiry of my sbi debit card', 'expiry'),
])
def test_specific_card_field_requests(core, phrase, field):
    memory_id = card(core)
    result = core.execute(phrase)
    assert len(result['memory_items']) == 1
    assert result['memory_items'][0]['copy_field'] == field
    with pytest.raises(ValueError):
        core.memory_conversation.copy_value(result['memory_token'], memory_id, 'value')


def test_aliases_exact_matching_and_duplicate_names_offer_choices(core, monkeypatch):
    first = password(core, aliases=['work login'])
    assert core.execute('my work login password')['memory_items'][0]['memory_id'] == first
    category = core.get_memory(first)['category_id']
    second = core.save_memory(category, 'Google Password', 'google.work.password', 'OtherSecret')
    decrypt = MagicMock(side_effect=AssertionError('Ambiguous matches must not decrypt'))
    monkeypatch.setattr('src.core.secrets.decrypt', decrypt)
    choices = core.execute('my google password')
    assert {row['memory_id'] for row in choices['memory_items']} == {first, second}
    assert choices['memory_view'] == 'list'
    assert not core.execute('my goo password')['success']
    decrypt.assert_not_called()


def test_empty_lists_do_not_open_a_copy_session(core):
    for phrase in ('list my passwords', 'list my cards', 'my missing password'):
        result = core.execute(phrase)
        assert not result['success'] and 'memory_items' not in result
        assert core.memory_conversation.token is None
    assert not core.history()


@pytest.mark.parametrize('condition', ['disabled', 'expired', 'other_profile'])
def test_unavailable_memories_never_decrypt(core, monkeypatch, condition):
    metadata = {'enabled': False} if condition == 'disabled' else {
        'lifetime': 'temporary', 'expires_at': '2000-01-01T00:00:00+00:00'
    } if condition == 'expired' else {'memory_scope': 'PROFILE', 'scope_id': 'other'}
    password(core, **metadata)
    decrypt = MagicMock(side_effect=AssertionError('Unavailable memories must not decrypt'))
    monkeypatch.setattr('src.core.secrets.decrypt', decrypt)
    assert not core.execute('list my passwords')['success']
    assert not core.execute('my google password')['success']
    assert not core.execute('what is my google.password')['success']
    decrypt.assert_not_called()


@pytest.mark.parametrize('condition', ['new_command', 'deleted', 'disabled', 'edited', 'profile', 'expired', 'wrong_token', 'wrong_id'])
def test_stale_or_forged_copy_actions_are_rejected(core, monkeypatch, condition):
    memory_id = password(core)
    result = core.execute('list my passwords')
    token, key = result['memory_token'], memory_id
    if condition == 'new_command':
        core.execute('help')
    elif condition == 'deleted':
        core.delete_memory(memory_id)
    elif condition == 'disabled':
        core.memory_service.update_memory(memory_id, enabled=False)
    elif condition == 'edited':
        core.memory_service.update_memory(memory_id, value='ChangedSecret', confirmed=True)
    elif condition == 'profile':
        core.memory_service.set_profile('different')
    elif condition == 'expired':
        monkeypatch.setattr('src.core.memory.conversation.time.monotonic', lambda: core.memory_conversation.deadline + 1)
    elif condition == 'wrong_token':
        token = 'forged-token'
    else:
        key = 'unlisted-id'
    decrypt = MagicMock(side_effect=AssertionError('Rejected actions must not decrypt'))
    monkeypatch.setattr('src.core.secrets.decrypt', decrypt)
    with pytest.raises(ValueError):
        core.memory_conversation.copy_value(token, key, 'value')
    decrypt.assert_not_called()


def test_partial_legacy_and_malformed_cards(core):
    partial = card(core, 'Partial', 'Card Number: 1234 5678 9012')
    result = core.execute('my partial card')
    assert result['memory_items'][1]['preview'] == 'Not saved'
    assert result['memory_items'][1]['copy_field'] is None
    legacy = card(core, 'Legacy', 'Legacy saved details')
    result = core.execute('my legacy card')
    assert result['memory_items'][0]['title'] == 'Saved details'
    assert core.memory_conversation.copy_value(result['memory_token'], legacy, 'value') == 'Legacy saved details'
    card(core, 'Broken', 'CVV: 123\nCVV: 456')
    assert not core.execute('my broken card')['success']


@pytest.mark.parametrize('phrase', ['my google password', 'list my passwords', 'list my card details'])
def test_new_memory_phrases_reserved_from_command_registration(core, phrase):
    with pytest.raises(ValueError, match='reserved'):
        core.save_command('Hijack', 'application', 'notepad', [phrase])


@pytest.fixture
def controller(core, qtbot, tmp_path, monkeypatch):
    from src.app.controller import ApplicationController
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    instance = ApplicationController(core)
    for widget in (instance.pet, instance.manager, instance.pet.response_bubble):
        qtbot.addWidget(widget)
    instance.manager.hide()
    instance.pet.show()
    previous_clipboard = QApplication.clipboard().text()
    yield instance
    QApplication.clipboard().setText(previous_clipboard)
    core.listeners.clear()
    QApplication.instance().aboutToQuit.disconnect(instance.shutdown)
    instance.shutdown()
    core.close = lambda: None
    instance.pet.hide()
    instance.manager.hide()


def test_balloon_named_and_list_password_copy_to_real_clipboard(controller, qtbot):
    core = controller.core
    google, office = password(core), password(core, 'Office', '<b>OfficeSecret</b>')
    controller.submit('my google password')
    bubble = controller.pet.response_bubble
    assert bubble.memory_mode and bubble.isVisible()
    previews = [label.text() for label in bubble.findChildren(QLabel)]
    assert '123****098' in previews and '1234567098' not in previews
    qtbot.mouseClick(bubble.memory_copy_buttons[(google, 'value')], Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == '1234567098'
    assert bubble.memory_hint.text() == 'Copied to clipboard.'
    controller.submit('list my passwords')
    qtbot.mouseClick(bubble.memory_copy_buttons[(office, 'value')], Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == '<b>OfficeSecret</b>'
    assert bubble.memory_mode
    qtbot.mouseClick(bubble.memory_select_buttons[google], Qt.MouseButton.LeftButton)
    assert bubble.memory_back_button.isVisible()
    qtbot.mouseClick(bubble.memory_back_button, Qt.MouseButton.LeftButton)
    assert len(bubble.memory_copy_buttons) == 2
    assert not core.history()


def test_balloon_cards_select_back_and_copy_fields(controller, qtbot):
    first, second = card(controller.core), card(controller.core, 'HDFC Credit')
    controller.submit('list my card details')
    bubble = controller.pet.response_bubble
    assert not bubble.memory_copy_buttons
    qtbot.mouseClick(bubble.memory_select_buttons[first], Qt.MouseButton.LeftButton)
    for field, value in [('card_number', '4532 1111 2222 3333'), ('cvv', '456'), ('expiry', '08/29')]:
        qtbot.mouseClick(bubble.memory_copy_buttons[(first, field)], Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text() == value
    qtbot.mouseClick(bubble.memory_back_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(bubble.memory_select_buttons[second], Qt.MouseButton.LeftButton)
    assert (second, 'cvv') in bubble.memory_copy_buttons


def test_failed_copy_keeps_clipboard_and_close_escape_and_new_command_clear(controller, qtbot):
    memory_id = password(controller.core)
    bubble = controller.pet.response_bubble
    controller.submit('list my passwords')
    QApplication.clipboard().setText('existing clipboard')
    controller.core.delete_memory(memory_id)
    qtbot.mouseClick(bubble.memory_copy_buttons[(memory_id, 'value')], Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == 'existing clipboard'
    assert 'unavailable' in bubble.memory_hint.text()
    controller.submit('help')
    assert not bubble.memory_mode and not bubble.memory_copy_buttons
    password(controller.core)
    controller.submit('list my passwords')
    qtbot.keyClick(controller.pet.command_box.input_field, Qt.Key.Key_Escape)
    assert not bubble.isVisible() and controller.core.memory_conversation.token is None
    controller.submit('list my passwords')
    qtbot.mouseClick(bubble.memory_close_button, Qt.MouseButton.LeftButton)
    assert not bubble.isVisible() and not bubble.memory_copy_buttons


def test_memory_balloon_scroll_screen_edges_and_timeout(controller, qtbot):
    for index in range(7):
        password(controller.core, 'Account ' + str(index))
    controller.submit('list my passwords')
    bubble = controller.pet.response_bubble
    assert bubble.memory_list.count() == 7 and bubble.memory_list.height() == 266
    assert bubble.memory_list.verticalScrollBar().maximum() > 0
    screen = QApplication.primaryScreen().availableGeometry()
    controller.pet.move(screen.bottomRight())
    bubble.update_position()
    assert screen.contains(bubble.geometry())
    bubble.auto_hide_timer.start(30)
    qtbot.waitUntil(lambda: not bubble.isVisible())
    assert not bubble.memory_mode and not bubble.memory_copy_buttons
    assert controller.core.memory_conversation.token is None


def test_hidden_pet_dismisses_memory_balloon(controller):
    password(controller.core)
    controller.submit('list my passwords')
    controller.pet.hide()
    assert not controller.pet.response_bubble.isVisible()
    assert controller.core.memory_conversation.token is None


def test_single_card_list_still_offers_back_and_previous_selection_cannot_copy(core):
    first = card(core)
    result = core.execute('list my cards')
    details = core.memory_conversation.select(result['memory_token'], first)
    assert details['memory_can_back']
    second = card(core, 'Second')
    result = core.execute('list my cards')
    core.memory_conversation.select(result['memory_token'], first)
    core.memory_conversation.select(result['memory_token'], second)
    with pytest.raises(ValueError, match='copy button'):
        core.memory_conversation.copy_value(result['memory_token'], first, 'cvv')


def test_dpapi_failure_copy_is_private_and_does_not_change_clipboard(controller, qtbot, monkeypatch):
    memory_id = password(controller.core)
    controller.submit('list my passwords')
    QApplication.clipboard().setText('preserve me')
    monkeypatch.setattr('src.core.secrets.decrypt', MagicMock(side_effect=ValueError('Windows could not unlock this memory for the current user.')))
    bubble = controller.pet.response_bubble
    qtbot.mouseClick(bubble.memory_copy_buttons[(memory_id, 'value')], Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == 'preserve me'
    assert 'could not unlock' in bubble.memory_hint.text()


def test_session_does_not_retain_plaintext_in_an_unencrypted_custom_password_category(core):
    core.add_category('Work Passwords', sensitive=False)
    category = next(row['id'] for row in core.categories() if row['name'] == 'Work Passwords')
    core.save_memory(category, 'Other Password', 'other.password', 'PrivateUnencryptedExample')
    result = core.execute('list my passwords')
    assert 'PrivateUnencryptedExample' not in repr(core.memory_conversation.__dict__)
    assert 'PrivateUnencryptedExample' not in json.dumps(result)


def test_app_shortcut_replaces_memory_copy_authority(core):
    memory_id = password(core)
    result = core.execute('list my passwords')
    assert core.execute_application_shortcut('notepad')['success']
    with pytest.raises(ValueError, match='expired'):
        core.memory_conversation.copy_value(result['memory_token'], memory_id, 'value')


def test_expiry_during_list_and_copy_never_returns_stale_data(core, monkeypatch):
    memory_id = password(core)
    result = core.execute('list my passwords')
    deadline = core.memory_conversation.deadline
    moments = iter([deadline - 1, deadline + 1])
    monkeypatch.setattr('src.core.memory.conversation.time.monotonic', lambda: next(moments))
    with pytest.raises(ValueError, match='expired'):
        core.memory_conversation.list(result['memory_token'])
    monkeypatch.undo()
    result = core.execute('list my passwords')
    decrypt = __import__('src.core.secrets', fromlist=['decrypt']).decrypt
    def expires_while_decrypting(value):
        data = decrypt(value)
        core.memory_conversation.deadline = 0
        return data
    monkeypatch.setattr('src.core.secrets.decrypt', expires_while_decrypting)
    with pytest.raises(ValueError, match='expired'):
        core.memory_conversation.copy_value(result['memory_token'], memory_id, 'value')


def test_long_unicode_and_literal_names_fit_balloon(controller, qtbot):
    name = '<b>資料' + 'LongAccountName' * 8 + '</b>'
    memory_id = password(controller.core, name=name)
    # A custom alias remains a concise way to request an unusually long name.
    controller.core.memory_service.update_memory(memory_id, aliases=['long account'])
    controller.submit('my long account password')
    bubble = controller.pet.response_bubble
    assert bubble.width() <= 380
    assert QApplication.primaryScreen().availableGeometry().contains(bubble.geometry())
    assert bubble.label.textFormat() == Qt.TextFormat.PlainText
    controller.submit('list my passwords')
    assert len(bubble.memory_select_buttons[memory_id].text()) < len(name)
