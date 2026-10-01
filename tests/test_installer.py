import zipfile
import pytest
from release.installer import unpack


def test_installer_rejects_path_traversal(tmp_path):
    archive = tmp_path / 'malicious.zip'
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('../outside.txt', 'bad')
    with pytest.raises(ValueError):
        unpack(archive, tmp_path / 'installation')
    assert not (tmp_path / 'outside.txt').exists()


def test_installer_unpacks_safe_archive(tmp_path):
    archive = tmp_path / 'app.zip'
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('pet-animal.exe', 'fixture')
        package.writestr('_internal/assets/ui/plus.svg', 'fixture')
    unpack(archive, tmp_path / 'installation')
    assert (tmp_path / 'installation/pet-animal.exe').read_text() == 'fixture'
