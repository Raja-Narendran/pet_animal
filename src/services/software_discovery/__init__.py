"""Offline detection; discovery never grants permission to launch software."""
from .models import DiscoveredApplication, RegisteredApplication, DiscoverySource, ValidationStatus
from .validator import ApplicationValidator
from .service import SoftwareDiscoveryService

__all__ = ['DiscoveredApplication', 'RegisteredApplication', 'DiscoverySource',
           'ValidationStatus', 'ApplicationValidator', 'SoftwareDiscoveryService']
