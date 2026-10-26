"""Application command line: serve, migrate, or recover."""
import argparse
import os

from . import create_app
from .config import database_url, load_env
from .shared.storage import Store


def main():
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', choices=['serve', 'migrate', 'recover'], default='serve')
    args = parser.parse_args()
    if args.command == 'migrate':
        store = Store(database_url())
        store.migrate(target=6)
        store.seed()
        print('Database revision 6 applied; catalog seeded if empty. No database URL displayed.')
    elif args.command == 'recover':
        application = create_app()
        result = application.extensions['booking'].payments.recover_pending()
        print('Recovery pass:', result)
    else:
        from waitress import serve
        application = create_app()
        print('Workshop Sandbox checkout at ' + application.config['APP_ORIGIN'], flush=True)
        serve(application, host='0.0.0.0' if application.config['APP_ENV'] == 'production' else '127.0.0.1',
              port=int(os.getenv('PORT', '8000')), threads=4)


if __name__ == '__main__':
    main()
