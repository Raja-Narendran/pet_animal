"""Explainable exact/structured retrieval over the local memory service."""
import math
from datetime import datetime

from .models import MemoryMatch, MemoryQuery, MemoryType
from .service import checked_text, labels, normalize


class MemoryRetriever:
    def __init__(self, service):
        self.service = service

    def _match(self, row, reason, base, consume, reveal=False):
        stamp = datetime.fromisoformat(self.service.now())
        age = max(0, (stamp - datetime.fromisoformat(row['updated_at'])).total_seconds() / 86400)
        bonus = (2 * row['importance'] + row['confidence'] + 0.5 / (1 + age)
                 + min(0.5, math.log1p(row['access_count']) / 10))
        if consume:
            if not self.service.record_access(row['id']):
                return None
            row = self.service.get_memory(row['id'], reveal=reveal)
        return MemoryMatch(row['id'], row['memory_key'], row['memory_value'], round(base + bonus, 6),
                           reason, bool(row['sensitive']), row['confidence'], row)

    def get_by_key(self, key, consume=True, reveal=False):
        query = normalize(checked_text(key, 'Key', 200))
        row = self.service.find_existing(query, reveal=reveal)
        if row is None or not self.service.applicable(row):
            return None
        reason = 'EXACT_KEY' if normalize(row['memory_key']) == query else 'ALIAS'
        return self._match(row, reason, 100 if reason == 'EXACT_KEY' else 90, consume, reveal=reveal)

    def consume(self, memory_id):
        row = self.service.get_memory(memory_id)
        if not row or not self.service.applicable(row):
            return None
        return self._match(row, 'EXACT_KEY', 100, True)

    def preference_exists(self, key):
        # A saved preference blocks a built-in fallback even while disabled, expired,
        # or owned by a different profile. Retrieval still enforces its scope.
        return self.service.find_existing(key) is not None

    def resolve_preference(self, key, consume=False, min_confidence=0.8):
        match = self.get_by_key(key, consume=False)
        if not match or match.sensitive or match.confidence < min_confidence or match.memory['memory_type'] != MemoryType.PREFERENCE.value:
            return None
        return self.consume(match.memory_id) if consume else match

    def retrieve_relevant(self, query, consume=True):
        if isinstance(query, str):
            query = MemoryQuery(text=query)
        if not isinstance(query, MemoryQuery) or isinstance(query.limit, bool) or not isinstance(query.limit, int) or not 1 <= query.limit <= 100:
            raise ValueError('Invalid memory query or result limit.')
        term = normalize(checked_text(query.text, 'Search', 1000, empty=True))
        tags = labels(query.tags, 'Tags')
        rows = self.service.list_memories(memory_type=query.memory_type, memory_scope=query.memory_scope,
                                         enabled=True, include_expired=False,
                                         include_system=query.memory_type == MemoryType.SYSTEM)
        ranked = []
        for row in rows:
            if not self.service.applicable(row):
                continue
            if tags and not set(tags).intersection(row['tags']):
                continue
            key = normalize(row['memory_key'])
            title = normalize(row['title'])
            if term and term == key:
                reason, base = 'EXACT_KEY', 100
            elif term and term in row['aliases']:
                reason, base = 'ALIAS', 90
            elif term and term == title:
                reason, base = 'TITLE', 80
            elif term and term in row['tags']:
                reason, base = 'TAG', 60
            elif term:
                searchable = [title, key, normalize(row['description']), *row['aliases'], *row['tags']]
                if not row['sensitive']:
                    searchable.append(normalize(row['memory_value']))
                if not any(term in field for field in searchable):
                    continue
                reason, base = 'TEXT', 40
            elif tags:
                reason, base = 'TAG', 60
            elif query.memory_type:
                reason, base = 'TYPE', 70
            else:
                reason, base = 'IMPORTANCE', 0
            match = self._match(row, reason, base, False)
            ranked.append(match)
        ranked.sort(key=lambda m: (-m.score, m.key, m.memory_id))
        selected = ranked[:query.limit]
        if consume:
            consumed = []
            for match in selected:
                item = self._match(match.memory, match.match_reason,
                                   {'EXACT_KEY':100,'ALIAS':90,'TITLE':80,'TYPE':70,'TAG':60,'TEXT':40,'IMPORTANCE':0}[match.match_reason], True)
                if item:
                    consumed.append(item)
            return consumed
        return selected

    def search(self, query, consume=True, limit=20, memory_type=None, memory_scope=None):
        return self.retrieve_relevant(MemoryQuery(query, memory_type, memory_scope, limit=limit), consume=consume)

    def retrieve_by_type(self, memory_type, consume=True, limit=20):
        return self.retrieve_relevant(MemoryQuery(memory_type=MemoryType(memory_type), limit=limit), consume=consume)

    def retrieve_by_tags(self, tags, consume=True, limit=20):
        return self.retrieve_relevant(MemoryQuery(tags=tuple(tags), limit=limit), consume=consume)

    def retrieve_relationships(self, memory_id, consume=True, limit=20):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('Invalid memory result limit.')
        source = self.service.get_memory(memory_id)
        if not source or not self.service.applicable(source):
            return []
        result, seen = [], set()
        for edge in self.service.get_relationships(memory_id):
            other_id = edge['target_memory_id'] if edge['source_memory_id'] == memory_id else edge['source_memory_id']
            row = self.service.get_memory(other_id)
            if other_id not in seen and row and self.service.applicable(row):
                result.append(self._match(row, 'RELATIONSHIP', 50, False))
                seen.add(other_id)
        result.sort(key=lambda m: (-m.score, m.key, m.memory_id))
        return [self._match(m.memory, 'RELATIONSHIP', 50, consume) for m in result[:limit]]
