import asyncio
import peewee
import peewee_async
from playhouse.signals import pre_save
from datetime import datetime, timedelta
from utils import get_config



database_conn = get_config()["database"]

database = peewee_async.MySQLDatabase(database=database_conn['name'],host=database_conn['host'],user=database_conn['user'],password=database_conn['password'])


class UserModel(peewee.Model):
    username = peewee.CharField(unique=True)
    password = peewee.CharField()
    kindle_email = peewee.CharField()
    email = peewee.CharField()
    activation_key = peewee.CharField()
    activated = peewee.BooleanField()
    created_date = peewee.DateTimeField(default=datetime.now)
    last_hi = peewee.DateTimeField(default=datetime.now) # last sent hi
    last_sent = peewee.DateTimeField()
    is_recurrent = peewee.BooleanField(default=True)
    has_requested = peewee.BooleanField(default=False)
    archive = peewee.TextField(default="")

    class Meta:
        database = database
        db_table = 'user'

class SubscribtionModel(peewee.Model):
    user = peewee.ForeignKeyField(UserModel, related_name='subscribtions', db_column='user_id')
    subreddit = peewee.CharField()
    created_date = peewee.DateTimeField(default=datetime.now)
    per_email = peewee.IntegerField(default=10)

    class Meta:
        database = database
        db_table = 'subscription'

class ReportModel(peewee.Model):
    user = peewee.ForeignKeyField(UserModel, related_name='reports', db_column='user_id')
    created_date = peewee.DateTimeField(default=datetime.now)
    subs = peewee.TextField()
    article_shortlinks = peewee.TextField()
    was_successful = peewee.BooleanField(default=False)
    was_requested = peewee.BooleanField()
    to_email = peewee.CharField()
    attachment_size = peewee.IntegerField(default=0)
    attachment_title = peewee.CharField()
    processing_time = peewee.IntegerField(default=0)
    processing_stage = peewee.IntegerField(default=0)
    is_recurrent = peewee.BooleanField()

    class Meta:
        database = database
        db_table = 'report'


class ContactModel(peewee.Model):
    name = peewee.CharField()
    website = peewee.CharField()
    email = peewee.CharField()
    content = peewee.TextField()
    created_date = peewee.DateTimeField(default=datetime.now)

    class Meta:
        database = database
        db_table = 'contact'

class KeyValueModel(peewee.Model):
    key = peewee.CharField()
    value = peewee.TextField(default='')
    ip = peewee.CharField(default='')
    created_date = peewee.DateTimeField(default=datetime.now)

    class Meta:
        database = database
        db_table = 'keyvalue'
        
def get_db():
    global database
    if database == None or database.is_closed():
        try:
            database = peewee_async.MySQLDatabase(database=database_conn['name'],host=database_conn['host'],user=database_conn['user'],password=database_conn['password'])
            UserModel.create_table(True)
            SubscribtionModel.create_table(True)
            ReportModel.create_table(True)
            ContactModel.create_table(True)
            KeyValueModel.create_table(True)
        except peewee.OperationalError:
            #couldn't connect
            raise
    return database
