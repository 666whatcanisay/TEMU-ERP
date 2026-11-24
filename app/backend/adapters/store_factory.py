"""Select an explicitly configured store; a failed MySQL never falls back."""
from .. import config

def create_store():
    if config.DB_DRIVER == 'mysql':
        from .storage_mysql import MySQLStore
        return MySQLStore(**config.mysql_settings())
    from .storage_sqlite import SQLiteStore
    return SQLiteStore(config.DB_PATH)
