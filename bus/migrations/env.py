from alembic import context
from sqlalchemy import create_engine
from bus.models import metadata, EXCLUDE_FROM_AUTOGENERATE

config = context.config

def include_object(object, name, type_, reflected, compare_to):
    """Exclude WITHOUT ROWID and FTS5 tables from autogenerate."""
    if type_ == "table" and name in EXCLUDE_FROM_AUTOGENERATE:
        return False
    return True

def run_migrations():
    # If connection passed via config.attributes (daemon startup path), use it.
    # Otherwise fall back to sqlalchemy.url from alembic.ini (CLI usage).
    connection = config.attributes.get("connection", None)

    if connection is not None:
        # Daemon startup path: reuse existing connection
        context.configure(
            connection=connection,
            target_metadata=metadata,
            render_as_batch=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        # CLI path: create engine from alembic.ini URL
        url = config.get_main_option("sqlalchemy.url")
        engine = create_engine(url, connect_args={"timeout": 5})
        with engine.connect() as conn:
            context.configure(
                connection=conn,
                target_metadata=metadata,
                render_as_batch=True,
                include_object=include_object,
            )
            with context.begin_transaction():
                context.run_migrations()

run_migrations()
