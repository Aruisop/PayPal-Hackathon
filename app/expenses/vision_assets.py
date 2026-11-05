"""Explicit preparation of pinned receipt vision weights; never called by a request."""
import argparse
import json
from pathlib import Path

from app.config import ROOT

MODEL_ID = 'Qwen/Qwen3-VL-2B-Instruct'
REVISION = '89644892e4d85e24eaac8bacfd4f463576704203'
DEFAULT_ROOT = ROOT / 'instance' / 'receipt-vision'
REQUIRED_FILES = ('config.json', 'model.safetensors', 'preprocessor_config.json',
                  'tokenizer.json', 'tokenizer_config.json', 'chat_template.json')


def validate_assets(root=None):
    directory = Path(root) if root is not None else DEFAULT_ROOT
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if manifest != {'model': MODEL_ID, 'revision': REVISION}:
            raise ValueError('Unexpected receipt model revision')
        if any(not (directory / name).is_file() or (directory / name).stat().st_size == 0
               for name in REQUIRED_FILES):
            raise ValueError('Incomplete receipt model')
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        raise ValueError('Receipt model is not prepared; run python -m app.expenses.vision_assets prepare.') from error
    return directory


def prepare(root=None):
    from huggingface_hub import snapshot_download
    directory = Path(root) if root is not None else DEFAULT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=MODEL_ID, revision=REVISION, local_dir=directory,
                      ignore_patterns=('*.md', '*.png', '*.jpg', '*.jpeg', '.gitattributes'))
    if any(not (directory / name).is_file() or (directory / name).stat().st_size == 0
           for name in REQUIRED_FILES):
        raise ValueError('Downloaded receipt model is incomplete.')
    (directory / 'manifest.json').write_text(
        json.dumps({'model': MODEL_ID, 'revision': REVISION}), encoding='utf-8')
    return validate_assets(directory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare local Hugging Face receipt vision weights')
    parser.add_argument('command', choices=('prepare', 'status'))
    args = parser.parse_args()
    if args.command == 'prepare':
        print(prepare())
    else:
        try:
            print(validate_assets())
        except ValueError as error:
            parser.exit(1, f'{error}\n')
