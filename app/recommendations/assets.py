"""Explicit, reproducible preparation of optional public CPU embedding assets.

The application never calls this downloader. Run it before serving AI requests:
    python -m app.recommendations.assets prepare --model minilm
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

from app.config import ROOT

DEFAULT_ROOT = ROOT / 'instance' / 'ai-models'
PROFILES = {
    'minilm': {
        'repository': 'Xenova/all-MiniLM-L6-v2',
        'revision': 'da5f6eac91a9596269707e15ec694e50e25a0d14',
        'pooling': 'mean', 'max_tokens': 256, 'dimension': 384,
        'query_prefix': '', 'license': 'Apache-2.0',
        'upstream': 'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2',
        'files': {
            'config.json': '7135149f7cffa1a573466c6e4d8423ed73b62fd2332c575bf738a0d033f70df7',
            'tokenizer.json': 'da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0',
            'tokenizer_config.json': '9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3',
            'special_tokens_map.json': 'b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3',
            'README.md': '730d4be64f0bbceee06e52d3ab49b7f76174c17644a56fea20708967aaa53750',
            'onnx/model_quantized.onnx': 'afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1',
        },
    },
    'bge': {
        'repository': 'Xenova/bge-small-en-v1.5',
        'revision': 'ea104dacec62c0de699686887e3f920caeb4f3e3',
        'pooling': 'cls', 'max_tokens': 512, 'dimension': 384,
        # Available for an explicitly reported retrieval experiment; off by default.
        'query_prefix': 'Represent this sentence for searching relevant passages: ',
        'license': 'MIT', 'upstream': 'https://huggingface.co/BAAI/bge-small-en-v1.5',
        'files': {
            'config.json': 'fa73f90bf92c8cace1fbcb709626306f2bdbc9ea3e5b5f94b440df9b6aa56350',
            'tokenizer.json': 'd241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66',
            'tokenizer_config.json': '9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3',
            'special_tokens_map.json': 'b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3',
            'README.md': 'ce711ead2cb11725c9c6de69779d918c500ab12c74c5c2437ff0c448ed1566a5',
            'onnx/model_quantized.onnx': '6c9c6101a956d62dfb5e7190c538226c0c5bb9cb27b651234b6df063ee7dbfe4',
        },
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_assets(model='minilm', root=None, verify_hashes=False):
    """Check local assets only. Hash verification runs once during runtime loading."""
    if model not in PROFILES:
        raise ValueError('Choose the minilm or bge model profile.')
    profile = PROFILES[model]
    directory = Path(root) / model if root is not None else DEFAULT_ROOT / model
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('model') != model or manifest.get('revision') != profile['revision']:
            raise ValueError('Asset manifest does not match the pinned model.')
        for name, expected in profile['files'].items():
            entry = manifest['files'][name]
            path = directory / name
            if entry['sha256'] != expected or path.stat().st_size != entry['bytes']:
                raise ValueError('A model asset is incomplete or changed.')
            if verify_hashes and sha256(path) != expected:
                raise ValueError('A model asset failed its pinned integrity check.')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f'Local {model} assets are missing or invalid; run python -m app.recommendations.assets prepare --model {model}.') from error
    return directory


def prepare(model='minilm', root=None):
    """Download public pinned files, verifying SHA-256 before atomic replacement."""
    if model not in PROFILES:
        raise ValueError('Choose the minilm or bge model profile.')
    profile = PROFILES[model]
    directory = Path(root) / model if root is not None else DEFAULT_ROOT / model
    directory.mkdir(parents=True, exist_ok=True)
    records = {}
    for name, expected in profile['files'].items():
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or sha256(destination) != expected:
            url = f"https://huggingface.co/{profile['repository']}/resolve/{profile['revision']}/{name}"
            request = urllib.request.Request(url, headers={'User-Agent': 'GroupPay-model-preparation/1'})
            temporary = None
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.partial', delete=False) as target:
                        temporary = Path(target.name)
                        total = 0
                        for chunk in iter(lambda: response.read(1024 * 1024), b''):
                            total += len(chunk)
                            if total > 64 * 1024 * 1024:
                                raise ValueError('Public model asset exceeds the download bound.')
                            target.write(chunk)
                if sha256(temporary) != expected:
                    raise ValueError(f'Integrity check failed for public model asset {name}.')
                os.replace(temporary, destination)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        records[name] = {'sha256': expected, 'bytes': destination.stat().st_size}
    manifest = {
        'format': 1, 'model': model, 'repository': profile['repository'],
        'revision': profile['revision'], 'pooling': profile['pooling'],
        'max_tokens': profile['max_tokens'], 'dimension': profile['dimension'],
        'license': profile['license'], 'upstream': profile['upstream'], 'files': records,
    }
    # No participant information, cookies, environment settings or database state.
    temporary = directory / 'manifest.json.partial'
    temporary.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, directory / 'manifest.json')
    validate_assets(model, root, verify_hashes=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare'])
    parser.add_argument('--model', choices=sorted(PROFILES), default='minilm')
    parser.add_argument('--root', type=Path, help='Optional local AI asset directory.')
    args = parser.parse_args()
    try:
        manifest = prepare(args.model, args.root)
    except Exception as error:
        parser.exit(1, f'Model preparation failed: {type(error).__name__}. No model is marked ready.\n')
    size = sum(entry['bytes'] for entry in manifest['files'].values())
    print(f"Prepared {args.model}: revision {manifest['revision']}, {size:,} verified asset bytes. No application data changed.")


if __name__ == '__main__':
    main()

