"""Configuration helpers shared by the app factory and CLI."""
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def database_url():
    value = os.getenv('DATABASE_URL', 'sqlite:///instance/workshops.db')
    if value.startswith('sqlite:///'):
        path = value[len('sqlite:///'):]
        if path != ':memory:' and not Path(path).is_absolute():
            return 'sqlite:///' + (ROOT / path).as_posix()
    return value


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
