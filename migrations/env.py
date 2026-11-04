import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("DQA_DATABASE_URL") or context.config.get_main_option("sqlalchemy.url")
if not url:
    raise SystemExit("set DQA_DATABASE_URL (run as dqa_admin_migrator; pods never run DDL)")

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as conn:
        context.configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()
