"""Download pinned multilingual speech assets at setup/build time only."""
from pathlib import Path
import hashlib
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
REVISION = '536b0662742c02347bc0e980a01041f333bce120'
FILES = {
    'model.bin': ('sha256', '3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671'),
    'config.json': ('git', 'e5047537059bd8f182d9ca64c470201585015187'),
    'tokenizer.json': ('git', '7818adb6de9fa3064d3ff81226fdd675be1f6344'),
    'vocabulary.txt': ('git', 'c9074644d9d1205686f16d411564729461324b75'),
}


def checksum(path, kind):
    digest = hashlib.sha256() if kind == 'sha256' else hashlib.sha1()
    if kind == 'git':
        digest.update(('blob ' + str(path.stat().st_size) + '\0').encode())
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare():
    destination = ROOT / 'assets/speech/whisper-small'
    destination.mkdir(parents=True, exist_ok=True)
    for name, (kind, expected) in FILES.items():
        target = destination / name
        if target.exists() and checksum(target, kind) == expected:
            continue
        partial = target.with_suffix(target.suffix + '.part')
        url = 'https://huggingface.co/Systran/faster-whisper-small/resolve/' + REVISION + '/' + name + '?download=true'
        print('Preparing local multilingual model:', name, flush=True)
        urllib.request.urlretrieve(url, partial)
        if checksum(partial, kind) != expected:
            raise ValueError('Speech model checksum mismatch: ' + name)
        partial.replace(target)
    return destination


if __name__ == '__main__':
    print('Prepared multilingual offline model:', prepare())
