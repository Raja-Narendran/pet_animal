"""On-demand, deterministic activity statistics; saves only approved candidates."""
import json
from collections import defaultdict
from datetime import datetime, timedelta
import uuid

from .models import MemorySource, MemoryType


class HabitEngine:
    COMMAND_THRESHOLD = 5
    APPLICATION_THRESHOLD = 10
    COOLDOWN_DAYS = 30
    WINDOW_DAYS = 90

    def __init__(self, service):
        self.service = service

    def list_candidates(self, status='PENDING'):
        if status is not None and status not in ('PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED'):
            raise ValueError('Invalid habit candidate status.')
        sql = 'SELECT * FROM habit_candidates'
        args = ()
        if status:
            sql += ' WHERE status=?'
            args = (status,)
        return self.service._rows(sql + ' ORDER BY evidence_count DESC,last_seen_at DESC,id', args)

    def analyze(self):
        now = datetime.fromisoformat(self.service.now())
        cutoff = (now - timedelta(days=self.WINDOW_DAYS)).isoformat()
        # Join configured commands. Unknown input, free-text web searches, failed launches,
        # memory queries and confirmations are never habit evidence.
        evidence = self.service._rows('''SELECT h.command_id,h.executed_at,c.action_type,c.action_config
               FROM command_history h JOIN commands c ON c.id=h.command_id
               WHERE h.execution_status='success' AND h.executed_at>=? AND c.enabled=1
               ORDER BY h.executed_at''', (cutoff,))
        groups = defaultdict(list)
        values = {}
        for record in evidence:
            command_id = record['command_id']
            phrase = self.service.db.execute('SELECT normalized_phrase FROM command_phrases WHERE command_id=? ORDER BY rowid LIMIT 1', (command_id,)).fetchone()
            if not phrase or record['action_type'] not in ('application', 'url'):
                continue
            key = 'habit.frequent_command.' + command_id
            groups[('COMMAND', key)].append(record['executed_at'])
            values[key] = phrase[0]
            if record['action_type'] == 'application':
                try:
                    target = json.loads(record['action_config'])['target']
                except (ValueError, KeyError, TypeError):
                    continue
                if not isinstance(target, str):
                    continue
                key = 'habit.frequent_application.' + target
                groups[('APPLICATION', key)].append(record['executed_at'])
                values[key] = target
        with self.service.db:
            self.service.db.execute("UPDATE habit_candidates SET status='EXPIRED' WHERE status='PENDING' AND last_seen_at<?", (cutoff,))
            for (kind, key), times in sorted(groups.items()):
                threshold = self.APPLICATION_THRESHOLD if kind == 'APPLICATION' else self.COMMAND_THRESHOLD
                count = len(times)
                if count < threshold:
                    continue
                previous = self.service.db.execute('SELECT * FROM habit_candidates WHERE candidate_key=?', (key,)).fetchone()
                if previous and previous['status'] == 'ACCEPTED':
                    continue
                if previous and previous['status'] == 'REJECTED':
                    rejected = datetime.fromisoformat(previous['rejected_at'])
                    if now - rejected < timedelta(days=self.COOLDOWN_DAYS) or count < previous['evidence_count'] + threshold or times[-1] <= previous['rejected_at']:
                        continue
                confidence = min(0.95, 0.7 + 0.1 * count / threshold)
                if previous:
                    self.service.db.execute("UPDATE habit_candidates SET confidence=?,evidence_count=?,first_seen_at=?,last_seen_at=?,status='PENDING',rejected_at=NULL WHERE id=?",
                                            (confidence, count, times[0], times[-1], previous['id']))
                else:
                    self.service.db.execute('''INSERT INTO habit_candidates(id,candidate_type,candidate_key,candidate_value,confidence,evidence_count,first_seen_at,last_seen_at)
                                           VALUES (?,?,?,?,?,?,?,?)''', (str(uuid.uuid4()), kind, key, values[key], confidence, count, times[0], times[-1]))
        self.service.changed()
        return self.list_candidates()

    def _pending(self, candidate_id):
        row = self.service.db.execute("SELECT * FROM habit_candidates WHERE id=? AND status='PENDING'", (candidate_id,)).fetchone()
        if not row:
            raise ValueError('Choose a pending habit candidate.')
        return dict(row)

    def accept(self, candidate_id, confirmed=False):
        candidate = self._pending(candidate_id)
        category = self.service.db.execute("SELECT id FROM memory_categories WHERE name='Custom' AND sensitive=0").fetchone()
        if category is None:
            category = self.service.db.execute('SELECT id FROM memory_categories WHERE sensitive=0 ORDER BY name LIMIT 1').fetchone()
        if category is None:
            raise ValueError('Create a non-sensitive category first.')
        title = ('Frequently opened application' if candidate['candidate_type'] == 'APPLICATION' else 'Frequently used command')
        memory_id = self.service.create_memory(category[0], title, candidate['candidate_key'], candidate['candidate_value'],
                         description=f"Approved activity pattern based on {candidate['evidence_count']} successful executions.",
                         memory_type=MemoryType.HABIT, source=MemorySource.HABIT_ENGINE,
                         confidence=candidate['confidence'], importance=0.5, tags=['activity', 'habit'], confirmed=confirmed)
        with self.service.db:
            self.service.db.execute("UPDATE habit_candidates SET status='ACCEPTED',memory_id=? WHERE id=?", (memory_id, candidate_id))
        self.service.changed()
        return memory_id

    def reject(self, candidate_id):
        self._pending(candidate_id)
        with self.service.db:
            self.service.db.execute("UPDATE habit_candidates SET status='REJECTED',rejected_at=? WHERE id=?", (self.service.now(), candidate_id))
        self.service.changed()
