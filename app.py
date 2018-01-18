
from utils import file_get_contents, file_get_contents_b, send_mmail, send_email_activation, json_converter, get_datetime_today_3_30, is_debug
import os

import tornado.ioloop
import tornado.web
import tornado.websocket

from tornado.options import parse_command_line
from tornado import gen

import json
from math import floor
import time
import sys
import threading
import validators

import praw

from urllib.parse import urlparse, parse_qs
from tornado.websocket import WebSocketClosedError

sleep_between_updates = 5

import asyncio
import functools
import signal

#logging = logging.getLogger('base.tornado')

########################## logging

# LOG_INFO = 'info.log'
LOG_DEBUG = 'logs/debug.log'
LOG_MESSAGES = 'logs/messages.log'
import logging
logger = logging.getLogger('')
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# add formatter to ch
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

#logging.basicConfig(filename=LOG_INFO,level=logging.INFO)
#logging.basicConfig(filename=LOG_DEBUG,level=logging.DEBUG)

import logging.handlers

# # Add the log message handler to the logger
# file_info_handler = logging.handlers.RotatingFileHandler(
#               LOG_INFO, maxBytes=1024*1024*50, backupCount=5)
# file_info_handler.setLevel(logging.INFO)
# file_info_handler.setFormatter(formatter)

# logger.addHandler(file_info_handler)

# Add the log message handler to the logger
file_debug_handler = logging.handlers.RotatingFileHandler(
              LOG_DEBUG, maxBytes=1024*1024*50, backupCount=5)
file_debug_handler.setLevel(logging.DEBUG)

file_debug_handler.setFormatter(formatter)

logger.addHandler(file_debug_handler)


message_logger = logger.getChild('message')
message_logger.propagate = False
# Add the log message handler to the logger
file_messages_handler = logging.handlers.RotatingFileHandler(
              LOG_MESSAGES, maxBytes=1024*1024*50, backupCount=5)
file_messages_handler.setLevel(logging.DEBUG)

file_messages_handler.setFormatter(formatter)

message_logger.addHandler(file_messages_handler)
message_logger.addHandler(ch)

def log_error(error):
    logger.error(error)
def log_info(info):
    logger.info(info)
def log_message(message):
    message_logger.info(message)
########################## logging











# store clients in dictionary..
clients = dict()
sessions = dict()

import asyncio
import peewee
import peewee_async
from models import SubscribtionModel, UserModel,  get_db, ContactModel, KeyValueModel
from utils import hash_password, id_generator, check_password, reddit_exists

database = get_db()
#database.close()
objects = peewee_async.Manager(database)
#database.set_allow_sync(False)


from tornado.platform.asyncio import AsyncIOMainLoop
AsyncIOMainLoop().install()

from datetime import datetime, timedelta


antispam_dict = dict() # {ip => { key => counter }} 
antispam_lock = threading.Lock()
antispam_last_hour = datetime.now().hour

r = praw.Reddit("bot", user_agent="bot2")
class AntispamException(Exception):
    def __init__(self, message, ip):

        # Call the base class constructor with the parameters it needs
        super(AntispamException, self).__init__(message)

        self.ip = ip

def record_entry(ip, key, limit=10):
    global antispam_dict
    
    log_info("Recording entry for key: " + str(key))
    
    antispam_lock.acquire()
    if ip not in antispam_dict:
        antispam_dict[ip] = dict()
    
    if key not in antispam_dict[ip]:
        antispam_dict[ip][key] = 0
    antispam_dict[ip][key] = antispam_dict[ip][key] + 1
    
    result = antispam_dict[ip][key] > limit
    antispam_lock.release()
    if result:
        return False
    return True

def antispam(ip, key, limit=10):
    if not record_entry(ip, key, limit):
        raise AntispamException("You've exceeded the limit of " + str(limit) + " requests for this action.", ip)
    
def antispam_clear():
    global antispam
    log_info("Antispam clear was called")
    antispam_lock.acquire()
    antispam_last_hour = datetime.now().hour
    antispam_dict = dict()
    antispam_lock.release()

@gen.coroutine
def antispam_caller():
    global antispam_last_hour
    while True:
        last_hour = datetime.now().hour
        if antispam_last_hour != last_hour:
            antispam_clear()
        yield gen.sleep(60) # seconds

        

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    _client_id_counter = 0
    def __init__(self, *args, **kwargs):
        super(WebSocketHandler, self).__init__(*args, **kwargs)
        
        self.client_id = WebSocketHandler._client_id_counter
        WebSocketHandler._client_id_counter = WebSocketHandler._client_id_counter + 1
        
        clients[self.client_id] = self
        
        tornado.ioloop.IOLoop.current().spawn_callback(self.update_ui)
        
        self.listeningTo = []
        self.my_user_id = "" # none
        self.session = None
    
    def open(self, *args):
        log_info("open(): hi, new connection with IP: " + str(self.request.remote_ip))
        
        try:
            antispam(self.getip(), "connect", 200)
        except AntispamException:
            log_error("SPAM: Too many connects. Closing on open()")
            self.close()
        
        self.send_data({})
        self.update_ui()
        self.stream.set_nodelay(True)

        uri = self.request.uri
        
        '''
        query_components = parse_qs(urlparse(uri).query)
        if "listen" in query_components:
            if len(query_components) > 0:
                self.listeningTo = query_components["listen"][0].split(',')
        '''

    def on_close(self):
        log_info("on_close(): bye user")
        """
        When client will disconnect (close web browser) then shut down connection for selected client
        """
        if self.client_id in clients:
            del clients[self.client_id]
        self.client_id = None
    
    def send_no_players_online(self):
        data = {'key': 'newPlayersOnlineCounter', 'players_online': len(clients)}
        self.send_data(data)
    def send_ping(self):
        data = {'key': 'PING'}
        self.send_data(data)
        
    def broadcast(self, data): #{ "id": "broadcast", "r": r, "g": g, "b": b })
        for key, value in clients.items():
            self.send_data_to(value, data)
    
    #data has to be object
    def send_data(self, data):
        self.send_data_to(self, data)
    
    #data has to be object
    def send_data_to(self, whom, data):
        try:
            whom.write_message(json.dumps(data, separators=(',',':'), default = json_converter))
        except WebSocketClosedError:
            whom.force_close()
    
    #string raw
    def send_raw(self, raw):
        try:
            self.write_message(raw)
        except WebSocketClosedError:
            self.force_close()#
    
    def count_users(self):
        return UserModel.select().count()
    
    def create_session(self, user, username, ip):
        global sessions
        session_id = id_generator(20)
        # TODO: datetime ..

        obj = {}
        #obj['client_id'] = self.client_id #no need for this
        obj['username'] = username
        obj['ip'] = ip
        obj['session_id'] = session_id # useful for the return
        obj['user'] = user # might be old
        obj['user_id'] = user.id
        log_info("Created session for user_id: " + str(obj['user_id']))
        obj['activated'] = user.activated
        
        sessions[session_id] = obj
        
        return obj
    def get_session(self, session_id, ip):
        global sessions
        if session_id in sessions:
            obj = sessions[session_id]
            if obj['ip'] == ip:
                return obj
        return None
    
    def close_session(self):
        global sessions
        if self.session != None:
            if self.session['session_id'] in sessions:
                del sessions[self.session['session_id']]
                self.session = None
                return True
        return False
    
    ###########################
    def getip(self):
        x_real_ip = self.request.headers.get("X-Real-IP")
        return x_real_ip or self.request.remote_ip
        
    def send_session_info(self):
        self.send_data({"key": "LOGGEDIN", "did": True, "session": self.session['session_id'], "activated": self.session['activated'], "kindle_email":self.session['user'].kindle_email})
        
    async def send_subs(self): # this is quite common.. goes for each update when changing the list. so i am gonna increase it from 30 to 100
        antispam(self.getip(), "send_subs", 100)
        if not self.logged_in():
            return
        subs = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.username == self.session['username'])
        all_subs = []
        for subscribtion in subs.select():
            all_subs += [subscribtion.subreddit]
        self.send_data({"key": "subs_list", "subs": all_subs})
    
    async def count_subs(self):
        subs = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.username == self.session['username'])

        return len(subs.select())
    
    async def send_antispamex(self, antispamex):
        self.send_data({"key": "antispam", "message": str(antispamex)})
    
    async def create_key_value(self, key, value=''):
        key = str(key)
        value = str(value)
        
        await objects.create(KeyValueModel,
            key=key,
            value=value,
            ip=self.getip())
        
    ###########################################################################
    async def m_contact(self, data):
        global objects
        
        antispam(self.getip(), "contact", 20)
        
        errors = []
        if not validators.email(data['email']):
            errors += ['Email invalid']
        if len(errors) > 0:
            self.send_data({"key": "form_contact", "success": False, "errors": errors})
            return None
        
        antispam(self.getip(), "contact", 5)
        
        contact = await objects.create(ContactModel,
            name=data['name'],
            website=data['website'],
            email=data['email'],
            content=data['content'])
        
        self.send_data({"key": "form_contact", "success": True})
        
        
        
    async def m_register(self, data):
        global objects
        
        antispam(self.getip(), "register_before_valid", 50)
        
        users_c = self.count_users()
        
        errors = []
        if not validators.email(data['email']):
            errors += ['Email invalid']
        if not validators.email(data['kindle_email']) or '@kindle.com' not in data['kindle_email']:
            errors += ['Kindle email invalid']
        if not validators.slug(data['username']):
            errors += ['Username invalid']
        if len(data['username']) < 6:
            errors += ['Username has to be at least 6 characters long']
        if len(data['password']) < 6:
            errors += ['Password has to be at least 6 characters long']
        if users_c >= 50:
            errors += ["The user limit has already reached 50. Please try again and consider letting us know if you'd prefer premium ($1 a month)."]
        if len(errors) > 0:
            self.send_data({"key": "form_register", "success": False, "errors": errors})
            return None
        
        #check if it exists already
        try:
            user = await objects.get(UserModel, username=data['username'])
            self.send_data({"key": "form_register", "success": False, "errors": ["Username already exists"]})
            return None
        except UserModel.DoesNotExist:
            pass
        
        try:
            user = await objects.get(UserModel, email=data['email'])
            self.send_data({"key": "form_register", "success": False, "errors": ["Email already exists"]})
            return None
        except UserModel.DoesNotExist:
            pass
            
        antispam(self.getip(), "register", 10)
        
        last_sent = get_datetime_today_3_30()
        activation_key=id_generator(6)
        user = await objects.create(UserModel,
            username=data['username'],
            password=hash_password(data['password']),
            kindle_email=data['kindle_email'],
            email=data['email'], 
            activation_key=activation_key,
            activated=False,
            last_sent=last_sent)
            
        send_email_activation(data['email'], activation_key)
        self.send_data({"key": "form_register", "success": True})
        return user
    
    
    async def m_login(self, data):
        global objects
        
        antispam(self.getip(), "login", 40)
        
        try:
            obj = await objects.get(UserModel, username=data['username'])
            if check_password(obj.password, data['password']):
                self.session = self.create_session(obj, data['username'], self.request.remote_ip)
                self.send_data({"key": "form_login", "success": True})
                self.send_session_info()
            else:
                self.send_data({"key": "form_login", "errors": ["Incorrect password!"]})
        except UserModel.DoesNotExist:
            self.send_data({"key": "form_login", "errors": ["Incorrect username!"]})
    
    
    async def m_relogin(self, data):
        antispam(self.getip(), "relogin", 200)
        
        self.session = self.get_session(data['session'], self.request.remote_ip)
        if self.session:
            self.send_data({"key": "form_relogin", "success": True})
            self.send_session_info()
        else:
            self.send_data({"key": "form_relogin", "success": False, "errors": ["Couldnt find the session"]})
            self.send_data({"key": "LOGGEDIN", "did": False})
        
    
    async def m_logout(self, data):
        antispam(self.getip(), "logout", 50)
        
        if not self.logged_in():
            return
        
        self.close_session()
        self.send_data({"key": "LOGGEDIN", "did": False})
    
    
    async def m_activate(self, data):
        antispam(self.getip(), "activate", 50)
        
        if not self.logged_in():
            self.send_data({"key": "form_activate", "success": False, "errors": ["not logged in"]})
            return
        
        activation_key = data['activation_key']
        if len(activation_key) != 6:
            self.send_data({"key": "form_activate", "success": False, "errors": ["Activation key is the wrong size"]})
            return
        
        if await self.activated():
            self.send_data({"key": "form_activate", "success": False, "errors": ["Activation has already been done."]})
        
        user = await self.get_user()
        if user.activation_key == activation_key:
            q = user.update(activated = True).where(UserModel.username == self.session['username'])
            q.execute()
            self.send_data({"key": "form_activate", "success": True})
            self.session['activated'] = True
        else:
            self.send_data({"key": "form_activate", "success": False, "errors": ["Activation key wrong"]})
    
    async def m_add_sub(self, data):
        global r
        
        antispam(self.getip(), "add_subs", 50)
        
        if not self.logged_in():
            self.send_data({"key": "form_add_sub", "success": False, "errors": ["not logged in"]})
            return
        if not await self.enabled():
            self.send_data({"key": "form_add_sub", "success": False, "errors": ["Account not enabled. Go to settings"]})
            return
        if not await self.activated():
            self.send_data({"key": "form_add_sub", "success": False, "errors": ["Account not activated. Go to your email"]})
            return
        
        sub = data['sub']
        
        if not reddit_exists(r, sub):
            self.send_data({"key": "form_add_sub", "success": False, "errors": ["Couldnt find subreddit, or it's marked as nsfw"]})
        
        count = await self.count_subs()
        if count > 1:
            self.send_data({"key": "form_add_sub", "success": False, "errors": ["Exceeded your limit of 2 subreddits."]})
            return
        
        results = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.username == self.session['username']).where(SubscribtionModel.subreddit == sub).select()
        
        if len(results) == 0: # doesnt already exist.
            await objects.create(SubscribtionModel, user=self.session['user'], subreddit=sub, per_email=10)
            await self.send_subs() # update
            self.send_data({"key": "form_add_sub", "success": True})
        else:
            self.send_data({"key": "form_add_sub", "success": False, "errors": ["You've already got this sub added"]})
        
    async def m_remove_sub(self, data):
        antispam(self.getip(), "remove_sub", 50)
        
        if not self.logged_in():
            self.send_data({"key": "form_remove_sub", "success": False, "errors": ["not logged in"]})
            return
            
        sub = data['sub']
        
        results = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.username == self.session['username']).where(SubscribtionModel.subreddit == sub).select()
        
        if len(results) > 0:
            result = results[0]
            SubscribtionModel.delete().where(SubscribtionModel.id == result.id).execute()
            self.send_data({"key": "form_remove_sub", "success": True})
        else:
            self.send_data({"key": "form_remove_sub", "success": False, "errors": ["You've already got this one added"]})
        
        await self.send_subs() # update
        
    async def m_get_subs(self, data):
        await self.send_subs()
   
    async def m_update_settings(self, data):
        antispam(self.getip(), "update_settings", 30)
        
        if not self.logged_in():
            self.send_data({"key": "form_settings", "success": False, "errors": ["not logged in"]})
            return
        kindle_email = data['kindle_email']
        
        user = await self.get_user()
        if user != None:
            q = user.update(kindle_email = kindle_email).where(UserModel.username == self.session['username'])
            q.execute()
        else:
            self.send_data({"key": "form_settings", "success": False, "errors": ["Couldnt find your user"]})
            
        self.send_data({"key": "form_settings", "success": True})
    
    async def m_account_reenable(self, data):
        antispam(self.getip(), "reenable", 20)
            
        if not self.logged_in():
            self.send_data({"key": "form_reenable", "success": False, "errors": ["not logged in"]})
            
        user = await self.get_user()
        if user != None:
            user = await objects.get(UserModel, username=self.session['username'])
            q = user.update(last_hi = datetime.now()).where(UserModel.username == self.session['username'])
            q.execute()
        else:
            self.send_data({"key": "form_reenable", "success": False, "errors": ["Couldnt find your user"]})
            
        self.send_data({"key": "form_reenable", "success": True})
        
    async def m_unsubscribe(self, data):
        antispam(self.getip(), "unsubscribe", 20)
        
        if not self.logged_in():
            self.send_data({"key": "form_unsubscribe", "success": False, "errors": ["not logged in"]})
            return
        
        kindle_email = data['kindle_email']
        
        user = UserModel.select().where(UserModel.kindle_email == kindle_email)
        SubscribtionModel.delete().where(SubscribtionModel.user == user).execute()
        
        self.send_data({"key": "form_unsubscribe", "success": True})
        
        
    async def m_get_settings(self, data):
        antispam(self.getip(), "get_settings", 100)
        
        if not self.logged_in():
            self.send_data({"key": "form_get_settings", "success": False, "errors": ["not logged in"]})
            return
            
        user = await self.get_user()
        if user != None:
            user = await self.get_user()
            self.send_data({"key": "settings_list", "settings": {'kindle_email':user.kindle_email, 'last_hi':user.last_hi}})
        else:
            self.send_data({"key": "form_get_settings", "success": False})
            
    async def m_delivery_request(self, data):
        antispam(self.getip(), "delivery_request", 100)
        
        if not self.logged_in():
            self.send_data({"key": "form_get_settings", "success": False, "errors": ["not logged in"]})
            return
        # ... others 
        
        
        user = await self.get_user()
        if user != None:
            q = user.update(has_requested = True).where(UserModel.username == self.session['username'])
            q.execute()
            
            now = datetime.now()
            if user.last_sent + timedelta(hours = 22) < now:
                self.send_data({"key": "form_delivery_request", "success": True, "message": "Ok, soon you'll have it."})
            else:
                self.send_data({"key": "form_delivery_request", "success": False, "errors": ["You will get one, in a day or so."]})
        else:
            self.send_data({"key": "form_delivery_request", "success": False, "errors": ["Not logged in"]})
        
    async def m_get_reccurency(self, data):
        antispam(self.getip(), "get_reccurency", 100)
        
        if not self.logged_in():
            self.send_data({"key": "form_recurrency", "success": False, "errors": ["not logged in"]})
            return
        #.. others
        
        user = await self.get_user()
        if user != None:
            self.send_data({"key": "form_recurrency", "success":True, "recurrent": user.is_recurrent})
        else:
            self.send_data({"key": "form_recurrency", "success": False, "errors":["Unexcepted"]})
            
            
            
    async def m_set_reccurency(self, data):
        antispam(self.getip(), "set_reccurency", 100)
        
        if not self.logged_in():
            self.send_data({"key": "form_recurrency", "success": False, "errors": ["not logged in"]})
            return
        #others.. ?
        
        recurrent = data['recurrent'] == True
        
        user = await self.get_user()
        q = user.update(is_recurrent = recurrent).where(UserModel.username == self.session['username'])
        q.execute()
        
        user = await self.get_user()
        self.send_data({"key": "form_recurrency", "success":True, "recurrent": user.is_recurrent})
        
    async def m_interested(self, data):
        await self.create_key_value("interested", "yes")
    
    #############################################################################################
   
    async def on_message(self, message):
        get_db()
        
        try:
            antispam(self.getip(), "on_message", 1500) # 1 500 messages an hour...
        except AntispamException:
            log_error("SPAM: Too many messages. closing.")
            self.close()
        
        if isinstance(message, (bytes, bytearray)):
            log_message("on_message(): BYTES")
            try:
                antispam(self.getip(), "on_message bytes", 40)
            except AntispamException:
                log_error("SPAM: Too many on message bytes. closing.")
                self.close()
        else:
            log_message("on_message(): message:" + message)
            data = None
            try:
                data = json.loads(message)
            except ValueError:
                log_message("INVALID JSON RECEIVED")
            
            if data != None and "key" in data: # message key
                try:
                    if data["key"] == "register":
                        await self.m_register(data)
                    elif data["key"] == "login":
                        await self.m_login(data)
                    elif data["key"] == "relogin":
                        await self.m_relogin(data)
                    elif data["key"] == "logout":
                        await self.m_logout(data)
                    elif data["key"] == "activate":
                        await self.m_activate(data)
                    elif data["key"] == "add_sub":
                        await self.m_add_sub(data)
                    elif data["key"] == "remove_sub":
                        await self.m_remove_sub(data)
                    elif data["key"] == "get_subs":
                        await self.m_get_subs(data)
                    elif data["key"] == "update_settings":
                        await self.m_update_settings(data)
                    elif data["key"] == "unsubscribe":
                        await self.m_unsubscribe(data)
                    elif data["key"] == "get_settings":
                        await self.m_get_settings(data)
                    elif data["key"] == "account_reenable":
                        await self.m_account_reenable(data)
                    elif data["key"] == "set_reccurency":
                        await self.m_set_reccurency(data)
                    elif data["key"] == "delivery_request":
                        await self.m_delivery_request(data)
                    elif data["key"] == "get_reccurency":
                        await self.m_get_reccurency(data)
                    elif data["key"] == "contact":
                        await self.m_contact(data)
                    elif data["key"] == "interested":
                        await self.m_interested(data)
                    elif data["key"] == "PING":
                        pass
                    else:
                        try:
                            antispam(self.getip(), "on_message else", 40) # 3 000 messages an hour...
                        except AntispamException:
                            log_error("SPAM: Too many on message elses. closing.")
                            self.close()
                    
                    pass
                    
                except peewee.OperationalError as e:
                    log_error("peewee.OperationalError happened")
                    import traceback
                    log_error(traceback.format_exception(None, # <- type(e) by docs, but ignored 
                                     e, e.__traceback__))
                    loop = asyncio.get_event_loop()
                    loop.stop()
                    #exit(1)
                except peewee.InterfaceError as e:
                    log_error("peewee.InterfaceError happened")
                    import traceback
                    log_error(traceback.format_exception(None, # <- type(e) by docs, but ignored 
                                     e, e.__traceback__))
                    loop = asyncio.get_event_loop()
                    loop.stop()
                    #exit(1)
                except AntispamException as antispamex:
                    log_error(str(antispamex) + " coming from: " + antispamex.ip)
                    self.send_antispamex(antispamex)

    @gen.coroutine
    def update_ui(self):
        global sleep_between_updates
        while self.client_id != None:
            self.send_ping()
            yield gen.sleep(sleep_between_updates) # seconds
            
        #removed sessions that haven't been updated .. + UPDATE in another function if they send pings lol.
        
    def force_close(self):
        log_info("force_close(): bye user. probably message wasn't able to send.")
        if self.client_id in clients:
            del clients[self.client_id]
        self.client_id = None

    def check_origin(self, origin):
        log_info("check_origin(): check origin, origin:" + origin)
        """
        Check if incoming connection is in supported domain
        :param origin (str): Origin/Domain of connection
        """
        if not is_debug():
            return 'ioanb7.com' in origin
        return True

    def logged_in(self):
        return self.session != None
    
    async def enabled(self):
        user = await self.get_user()
        now = datetime.now()
        
        last_hi = user.last_hi
        testing = last_hi + timedelta(days=14)
        return testing > now
    
    async def activated(self):
        user = await self.get_user()
        return user.activated
        
    async def get_user(self):
        if not self.logged_in():
            return None
        
        user = None
        try:
            user = await objects.get(UserModel, username=self.session['username'])
        except UserModel.DoesNotExist:
            log_error("ERROR activate usermodel")
        
        return user
def get_path_intern(path):
    thisdir = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(thisdir, path)
    
class MainHandler(tornado.web.RequestHandler):
    def get(self, second_param):
        self.write(file_get_contents(get_path_intern('assets/index.html')))

class ScriptHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(file_get_contents(get_path_intern('assets/bundle.js')))

class LogoHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(file_get_contents_b(get_path_intern('assets/logo.png')))

class FaviconHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(file_get_contents_b(get_path_intern('assets/favicon.ico')))

        
def ask_exit(signame):
    log_info("got signal %s: exit" % signame)
    loop = asyncio.get_event_loop()
    if loop != None:
        loop.stop()


        
def main():
    port = 8200
    
    print(1)
    import sys
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except:
            pass
    print(2)
    tornado.options.parse_command_line()
    print(3)

    '''
    global debug
    debug = False
    debug=True
    if 'debug' in sys.argv or '-debug' in sys.argv or '--debug' in sys.argv:
        debug=True
    '''

    print(4)
    
    paths = [
        (r'/socket_kinddit', WebSocketHandler),
    ]
    if is_debug():
        paths += [
            (r'/script.js', ScriptHandler),
            (r'/favicon.ico', FaviconHandler),
            (r'/kinddit/logo.png', LogoHandler),
            (r'/(.*)', MainHandler),
        ]
    app = tornado.web.Application(paths, debug=is_debug())

    print(5)
    log_info("Websocket service on %d" % port)
    if is_debug():
        log_info("Debug mode.")
    app.listen(port)    
    
    tornado.ioloop.IOLoop.current().spawn_callback(antispam_caller)
    loop = asyncio.get_event_loop()
    
    # run.
    if sys.platform == 'win32':
        try:
            log_info("Running. Press Ctrl+C to interrupt.")
            loop.run_forever()
        except KeyboardInterrupt:
            log_info("CTRL+C pressed")
    else:
        for signame in ('SIGINT', 'SIGTERM'):
            try:
                loop.add_signal_handler(getattr(signal, signame),
                                    functools.partial(ask_exit, signame))
            except NotImplementedError:
                log_error("NOTIMPLEMENTEDERROR SIGINT, SIGTERM")
        try:
            log_info("Running. Press Ctrl+C to interrupt.")
            loop.run_forever()
        finally:
            loop.close()
    log_info("Shutdown with grace!")


if __name__ == "__main__":
    main()