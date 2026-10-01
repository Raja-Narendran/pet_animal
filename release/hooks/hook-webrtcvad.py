"""The maintained wheels use a different distribution name from webrtcvad."""
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata('webrtcvad-wheels')
hiddenimports = ['_webrtcvad']
