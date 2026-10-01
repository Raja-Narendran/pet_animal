"""Build-time preparation only. The application never downloads speech models."""
from pathlib import Path
import hashlib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
NAME = 'vosk-model-small-en-us-0.15'
URL = 'https://alphacephei.com/vosk/models/' + NAME + '.zip'
SHA256 = '30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498'


def configure_endpoint(model):
    """Every speech endpoint must wait for 1.5 seconds of trailing silence."""
    config = model / 'conf/model.conf'
    lines = config.read_text(encoding='utf-8').splitlines()
    keys = [f'--endpoint.rule{rule}.min-trailing-silence=' for rule in (2, 3, 4, 5)]
    lines = [line for line in lines if not any(line.startswith(key) for key in keys)]
    lines.extend(key + '1.5' for key in keys)
    config.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def prepare():
    destination = ROOT / 'assets/speech'
    model = destination / NAME
    if (model / 'am/final.mdl').is_file() and (model / 'conf/model.conf').is_file():
        configure_endpoint(model)
        return model
    archive_path = ROOT / 'build' / (NAME + '.zip')
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        urllib.request.urlretrieve(URL, archive_path)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != SHA256:
        raise ValueError('Offline speech model checksum does not match the pinned release.')
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Offline speech model archive is corrupt.')
        for entry in archive.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError('Unsafe model archive path.')
            if not entry.is_dir():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
    configure_endpoint(model)
    return model


if __name__ == '__main__':
    print('Prepared offline voice model:', prepare())
