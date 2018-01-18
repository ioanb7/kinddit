#adds an archive field

import asyncio
import peewee
import peewee_async
from playhouse.signals import pre_save
from datetime import datetime, timedelta

from playhouse.migrate import *

import sys
sys.path.append("..")

from utils import get_config  # noqa


database_conn = get_config()["database"]

database = peewee_async.MySQLDatabase(database=database_conn['name'],host=database_conn['host'],user=database_conn['user'],password=database_conn['password'])

migrator = MySQLMigrator(database)

archive = peewee.TextField(default="")
migrate(
    migrator.add_column('user', 'archive', archive),
)
