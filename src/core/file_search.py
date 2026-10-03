"""Short-lived search conversation, separate from filename interpretation and I/O."""
import time
import uuid
import hashlib
from dataclasses import replace
from ..services.file_search import FileSearchResponse


class FileSearchSession:
    def __init__(self, lifetime=300, record_open=None):
        self.lifetime = lifetime
        self.record_open = record_open
        self.clear()

    def clear(self):
        self.token = None
        self.created = 0
        self.response = FileSearchResponse()
        self.suggested = None
        self.selected = None
        self.page = 0
        self.pending = False
        self.order = "opened"

    def begin(self):
        self.clear()
        self.token = str(uuid.uuid4())
        self.created = time.monotonic()
        self.pending = True
        return self.token

    def active(self):
        if self.token and time.monotonic() - self.created < self.lifetime:
            return True
        self.clear()
        return False

    @staticmethod
    def reply(success, message, **extra):
        return dict(success=success, message=message, pet_state='success' if success else 'idle',
                    file_search=True, **extra)

    @staticmethod
    def opened_key(item):
        return (item.opened is None, -(item.opened or 0), -item.modified, item.path.casefold())

    @staticmethod
    def result_id(item):
        return hashlib.sha256(item.path.casefold().encode('utf-8')).hexdigest()

    def present(self, result):
        if self.active() and not self.pending:
            result.update(file_results=[dict(id=self.result_id(item), path=item.path,
                is_folder=item.is_folder, modified=item.modified, opened=item.opened,
                opened_source=item.opened_source) for item in self.response.results],
                search_token=self.token, search_sort=self.order,
                search_partial=self.response.partial, search_backend=self.response.backend, search_notice=self.response.notice,
                search_remaining_ms=max(1, int((self.lifetime - (time.monotonic() - self.created)) * 1000)))
        return result

    def open_identified(self, token, result_id, launcher):
        if not self.active() or token != self.token or self.pending:
            return self.reply(False, 'This search expired. Search again.')
        index = next((i for i, item in enumerate(self.response.results) if self.result_id(item) == result_id), None)
        if index is None:
            return self.present(self.reply(False, 'This result is no longer available. Search again.'))
        return self.open_result(index, launcher)

    def sort_results(self, token, order):
        if not self.active() or token != self.token or self.pending:
            return self.reply(False, 'This search expired. Search again.')
        if order not in ('opened', 'modified'):
            return self.present(self.reply(False, 'Choose Recently opened or Recently changed.'))
        selected = self.response.results[self.selected] if self.selected is not None else None
        suggested = self.response.results[self.suggested] if self.suggested is not None else None
        key = self.opened_key if order == 'opened' else lambda item: (-item.modified, item.path.casefold())
        self.response = replace(self.response, results=tuple(sorted(self.response.results, key=key)))
        self.selected = self.response.results.index(selected) if selected else None
        self.suggested = self.response.results.index(suggested) if suggested else None
        self.order = order
        return self.present(self.reply(True, f'Found {len(self.response.results)} results.' +
            (' Search was incomplete.' if self.response.partial else '') +
            ('\n' + self.response.notice if self.response.notice else '')))

    def finish(self, token, response, intent, launcher):
        if not self.active() or token != self.token:
            return None
        self.response = response
        self.pending = False
        results = response.results
        if not results:
            message = ('No matching results in the searched locations.' if response.partial else 'No matching files or folders found.')
            if response.partial:
                message += ' Search was incomplete. Narrow the folders in Settings or enable Everything.'
            if response.notice:
                message += '\n' + response.notice
            return self.present(self.reply(False, message, search_backend=response.backend, search_partial=response.partial))
        self.selected = 0
        salesforce = [index for index, item in enumerate(results) if item.project == 'Salesforce']
        kind = 'folder' if dict(intent.filters).get('kind') == 'folder' else 'file'
        count = len(results)
        message = f'Found {"at least " if response.partial else ""}{count} {kind}{"s" if count != 1 else ""}.'
        if count == 1 and not response.partial and intent.action == 'FIND_AND_OPEN':
            opened = self.open_result(0, launcher)
            opened['message'] = message + '\n' + opened['message']
            return opened
        if count > 1 and len(salesforce) == 1:
            self.suggested = salesforce[0]
            self.selected = self.suggested
            message += f' Do you want the one from your Salesforce project?\n{results[self.suggested].path}\nSay Yes, Open the most recent one, or Show results.'
        else:
            message += (f' The most recently opened result is in {results[0].path}.' if results[0].opened else f' The most recent one is in {results[0].path}.') + '\nSay Open it or Show results.'
        if response.partial:
            message += '\nSearch was incomplete; this is the most recent among these results.'
        if response.notice:
            message += '\n' + response.notice
        return self.present(self.reply(True, message, search_backend=response.backend, search_partial=response.partial))

    def followup(self, intent, launcher):
        if intent.action == 'CANCEL':
            self.clear()
            return self.reply(True, 'File selection cancelled.')
        if self.active() and self.pending:
            return dict(self.reply(False, 'The file search is still running. I will show the results when it finishes.'), pet_state='working')
        if not self.active() or not self.response.results:
            return self.reply(False, 'Search for a file or folder first, for example /package.xml.')
        results = self.response.results
        if intent.action == 'CONFIRM':
            if self.suggested is None:
                return self.reply(False, 'Use Open it or Open <result number> to choose a search result.')
            return self.open_result(self.suggested, launcher)
        if intent.action == 'LIST':
            self.page = 0
            return self.list_results()
        if intent.action in ('NEXT', 'PREVIOUS'):
            self.page = max(0, min((len(results) - 1) // 5,
                self.page + (1 if intent.action == 'NEXT' else -1)))
            return self.list_results()
        if intent.action == 'OPEN_RESULT':
            return self.open_result(self.selected or 0, launcher)
        if intent.action == 'OPEN_RECENT':
            return self.open_result(max(range(len(results)), key=lambda i: results[i].modified), launcher)
        if intent.action == 'SELECT':
            try:
                index = int(intent.target) - 1
            except (TypeError, ValueError):
                return self.reply(False, 'Choose a result number from the last search.')
            return self.open_result(index, launcher)
        if intent.action == 'SELECT_PROJECT':
            query = (intent.query or '').casefold()
            matches = [index for index, item in enumerate(results) if query and query == (item.project or '').casefold()]
            if not matches:
                matches = [index for index, item in enumerate(results) if query and query in item.path.casefold()]
            if len(matches) == 1:
                return self.open_result(matches[0], launcher)
            return self.reply(False, 'That description does not identify one result. Say Show results, then Open <number>.')
        return self.reply(False, 'Use Open it, Yes, Show results, or Open <number>.')

    def list_results(self):
        # Keep the speech bubble usable; numbered pages expose every retained result.
        start = self.page * 5
        return self.present(self.reply(True, '\n'.join(f'{index + 1}. {item.path}' for index, item in
                          enumerate(self.response.results[start:start + 5], start)) +
                          '\nSay Open <number>.' +
                          (' Use Next results / Previous results for more.' if len(self.response.results) > 5 else '')))

    def open_result(self, index, launcher):
        if not 0 <= index < len(self.response.results):
            return self.reply(False, 'Choose a result number from the last search.')
        item = self.response.results[index]
        try:
            success, message = launcher.open_local_result(item.path, is_folder=item.is_folder)
        except Exception:
            success, message = False, 'This result could not be opened. Search again.'
        if success:
            self.selected = index
            self.suggested = None
            stamp = time.time()
            if self.record_open:
                try:
                    self.record_open(item, stamp)
                except Exception:
                    message += "\nPet could not save the open history."
            items = list(self.response.results)
            items[index] = replace(item, opened=stamp, opened_source='Pet')
            self.response = replace(self.response, results=tuple(items))
            self.sort_results(self.token, self.order)
        return self.present(self.reply(success, message))
