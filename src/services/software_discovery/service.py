"""Extensible providers and conservative merging without a persistent detection cache."""
import logging
import shutil
from pathlib import Path
from dataclasses import replace
from .models import DiscoveredApplication, DiscoverySource, ValidationStatus
from .validator import ApplicationValidator, canonical_path
from .start_menu import StartMenuDiscoveryProvider
from .registry import RegistryDiscoveryProvider

logger = logging.getLogger(__name__)


class PathDiscoveryProvider:
    NAMES = ('code.exe', 'git.exe', 'python.exe', 'node.exe', 'chrome.exe')

    def discover(self):
        for name in self.NAMES:
            target = shutil.which(name)
            if target:
                yield DiscoveredApplication.candidate(name[:-4], target, DiscoverySource.PATH)


class ApplicationDeduplicator:
    def merge(self, candidates):
        result, paths, identities, names, path_cache = [], {}, {}, {}, {}
        for candidate in candidates:
            value = candidate.executable_path
            if value not in path_cache:
                path_cache[value] = canonical_path(value)
            path = path_cache[value]
            identity = None
            if candidate.launchable and value:
                try:
                    stat = Path(value).stat()
                    if stat.st_ino:
                        identity = (stat.st_dev, stat.st_ino)
                except OSError:
                    pass
            index = paths.get(path) if path else None
            if index is None and identity:
                index = identities.get(identity)
            if index is None:
                matches = [i for i in names.get(candidate.normalized_name, [])
                           if (not path or not result[i].executable_path)
                           and (not result[i].publisher or not candidate.publisher or result[i].publisher == candidate.publisher)]
                if len(matches) == 1:
                    index = matches[0]
            if index is None:
                index = len(result)
                result.append(candidate)
            else:
                existing = result[index]
                # Prefer a valid executable-only launch, then richer display metadata.
                preferred, other = (candidate, existing) if candidate.launchable and not existing.launchable else (existing, candidate)
                result[index] = replace(preferred, publisher=preferred.publisher or other.publisher,
                    version=preferred.version or other.version, icon_path=preferred.icon_path or other.icon_path,
                    sources=tuple(dict.fromkeys(existing.sources + candidate.sources)))
            if path:
                paths[path] = index
            if identity:
                identities[identity] = index
            if index not in names.setdefault(candidate.normalized_name, []):
                names[candidate.normalized_name].append(index)
        return sorted(result, key=lambda item: item.normalized_name)


class SoftwareDiscoveryService:
    def __init__(self, providers=None):
        self.providers = providers if providers is not None else [StartMenuDiscoveryProvider(), RegistryDiscoveryProvider(), PathDiscoveryProvider()]
        self.validator = ApplicationValidator()
        self.errors = []

    def discover(self, cancelled=lambda: False):
        logger.info('Software discovery started')
        self.errors = []
        candidates = []
        for provider in self.providers:
            if cancelled():
                break
            try:
                for candidate in provider.discover():
                    if cancelled():
                        break
                    try:
                        validated = self.validator.validate(candidate)
                        if candidate.validation_status == ValidationStatus.INVALID_PATH:
                            validated = replace(validated, validation_status=ValidationStatus.INVALID_PATH, launchable=False)
                        candidates.append(validated)
                    except (OSError, ValueError, TypeError):
                        logger.warning('Ignoring malformed software candidate')
            except Exception:
                self.errors.append(type(provider).__name__)
                logger.warning('Software discovery provider failed: %s', type(provider).__name__)
        result = ApplicationDeduplicator().merge(candidates)
        logger.info('Software discovery completed: %d candidates, %d valid, %d ignored',
                    len(result), sum(item.launchable for item in result), sum(not item.launchable for item in result))
        return result
