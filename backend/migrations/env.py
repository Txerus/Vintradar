from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.models import Base
from app.config import settings
config=context.config;config.set_main_option("sqlalchemy.url",settings.database_url);target_metadata=Base.metadata
def offline():
    context.configure(url=settings.database_url,target_metadata=target_metadata,literal_binds=True);context.run_migrations()
async def online():
    engine=async_engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    async with engine.connect() as c:
        def migrate(conn):
            context.configure(connection=conn,target_metadata=target_metadata);context.run_migrations()
        await c.run_sync(migrate)
    await engine.dispose()
if context.is_offline_mode():offline()
else:
    import asyncio;asyncio.run(online())
