import asyncio
import peewee
import peewee_async
from datetime import datetime, timedelta
import os
import time 
from models import SubscribtionModel, UserModel, ReportModel, get_db
from utils import encode_articles_for, generate_html, send_kindler, GracefulKiller, get_datetime_today_4_00, is_debug, serialise_article_for_archive
import filelock
import sys

################################### LOGS
LOG_DEBUG = 'logs/debug_cron.log'
import logging
logger = logging.getLogger('')
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

import logging.handlers
file_debug_handler = logging.handlers.RotatingFileHandler(
              LOG_DEBUG, maxBytes=1024*1024*50, backupCount=5)
file_debug_handler.setLevel(logging.DEBUG)

file_debug_handler.setFormatter(formatter)

logger.addHandler(file_debug_handler)

def log_error(error):
    logger.error(error)
def log_info(info):
    logger.info(info)
##################################

killer = GracefulKiller()

def delay_between_users():
    global killer
    if killer.kill_now:
        return
    log_info(".")
    time.sleep(1)
    if killer.kill_now:
        return
    log_info(".")
    time.sleep(1)

def delay_between_runs():
    global killer
    
    sleepint = 60 # usual
    if is_debug():
        sleepint = 5
        log_info("Till next time.. DEBUG MODE 5 second delay only")
    
    log_info("Till next time..")
    for i in range(sleepint):# 1 minute
        if killer.kill_now:
            return
        time.sleep(1)

        
def get_title():
    date = str(time.strftime("%d-%m-%Y"))
    return "Kiddler - " + date

def get_milliseconds_from(start_time):
    b = datetime.now()
    c = b - start_time
    return int(c.total_seconds() * 1000)

def process(select):
    database = get_db()
    now = datetime.now()
    todo = {}

    for subscribtion in select:
        if subscribtion.user.username not in todo:
            obj = { 'subs': [], 'archive': subscribtion.user.archive, 'user': subscribtion.user }
            todo[subscribtion.user.username] = obj
        todo[subscribtion.user.username]['subs'] += [subscribtion]
        

    for username, value in todo.items():
        start_time = datetime.now()
        log_info(username)
        log_info(value)
        
        till_tries_again = now - timedelta(hours=2)
        user = value['user']
        #update before it can go to shit
        q = user.update(last_sent = till_tries_again).where(UserModel.id == user.id)
        q.execute()
        
        subs_encoded = ""
        for sub in value['subs']:
            subs_encoded += sub.subreddit + " ; "
            
        
        report = ReportModel(
            user=user,
            processing_stage=0,
            processing_time=get_milliseconds_from(start_time),
            to_email = user.kindle_email,
            was_requested = user.has_requested,
            was_successful=False,
            attachment_size = 0,
            attachment_title = get_title(),
            article_shortlinks='',
            subs=subs_encoded,
            is_recurrent=user.is_recurrent
            )
        report.save()
        
        try:
            thisdir = os.path.dirname(os.path.realpath(__file__))
            title=get_title()
            output_path = os.path.join(thisdir, 'kinddit_output/' + title + '.html')
            
            articles = encode_articles_for(value['subs'], value['archive'])

            prepend_archives = ""
            for article in articles:
                if not article['archived']:
                    prepend_archives = serialise_article_for_archive(article) + prepend_archives
            
            archive = prepend_archives + value['archive']

            q = user.update(archive = archive).where(UserModel.id == user.id)
            q.execute()

            
            articles_encoded = ""
            for article in articles:
                articles_encoded += article['link'] + " ; "
            
            #make a list of subs, articles
            #update report.stage
            q = report.update(processing_stage=5, processing_time=get_milliseconds_from(start_time), article_shortlinks=articles_encoded )\
                        .where(ReportModel.id == report.id)
            q.execute()
            
            #generate book.html
            size = generate_html(username, articles, output_path, title)
            
            
            q = report.update(processing_stage=10, processing_time=get_milliseconds_from(start_time),attachment_size=size )\
                        .where(ReportModel.id == report.id)
            q.execute()
            
            
            #update before it can go to shit
            hasrequested = user.is_recurrent == False and user.has_requested == True
            if hasrequested:
                hasrequested = False
            q = user.update(has_requested=hasrequested).where(UserModel.id == user.id)
            q.execute()


            if not is_debug():
                send_kindler(value['user'].kindle_email, output_path)
            else:
                log_info("Didnt send kindler through e-mail. it's waiting in the folter.")
            #send email
            #update success=True, processing_time
            q = report.update(processing_stage=15, processing_time=get_milliseconds_from(start_time), was_successful=True, was_requested=False )\
                        .where(ReportModel.id == report.id)
            q.execute()
            
            if not is_debug():
                os.remove(output_path)
            
            log_info("Sent for: " + username)
        except Exception as e:
            log_error("Unexpected error while sending.")
            import traceback
            log_error(traceback.format_exception(None, # <- type(e) by docs, but ignored 
                             e, e.__traceback__),)
        
        delay_between_users()
    
        
        
    
    
def process_nonpremiums():
    log_info("Process non-premiums")
    database = get_db()
    now = datetime.now()
    #last_valid_date = datetime.now() - timedelta(hours = 24)    
    #select = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.activated == True).where(UserModel.last_sent < last_valid_date).where(UserModel.last_hi + timedelta(days=14) < now)
    
    today_4_00 = get_datetime_today_4_00()
    if now < today_4_00:
        return # not 4 yet ..
    
    compare_against = today_4_00 - timedelta(hours = 22) # so if user received a kindler at 3.59am? dont send another one 2 hours later..
    last_hi_verif = now - timedelta(days=14)
    select = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.is_recurrent == True).where(UserModel.activated == True).where(UserModel.last_sent < compare_against).where(UserModel.last_hi > last_hi_verif).select()
    
    #print(select)
    #print(list(select))
    
    
    process(select)
    
    
def process_manuals():
    log_info("Process manuals")
    database = get_db()
    now = datetime.now()
    
    compare_against = now - timedelta(hours = 23, minutes=59)
    last_hi_verif = now - timedelta(days=14)
    select = SubscribtionModel.select().join(UserModel).where(UserModel.id == SubscribtionModel.user_id).where(UserModel.is_recurrent == False).where(UserModel.has_requested == True).where(UserModel.activated == True).where(UserModel.last_sent < compare_against).where(UserModel.last_hi > last_hi_verif).select()
    
    #print(select)
    #print(list(select))
    
    process(select)
    
    # query all that match
    
    
    
def go():
    now = datetime.now()
    log_info("Running at: " + str(now))
    process_manuals()
    process_nonpremiums()

def loop():
    try:
        go()
    except peewee.OperationalError as e:
        log_error("peewee.OperationalError happened")
        import traceback
        log_error(traceback.format_exception(None, # <- type(e) by docs, but ignored 
                         e, e.__traceback__))
        exit(1)
    except peewee.InterfaceError as e:
        log_error("peewee.InterfaceError happened")
        import traceback
        log_error(traceback.format_exception(None, # <- type(e) by docs, but ignored 
                         e, e.__traceback__))
        exit(1)
    delay_between_runs()

if __name__ == '__main__':
    lock = filelock.FileLock("LOCKFILE")
    
    try:
        with lock.acquire(timeout = 3):
            while True:
                loop()
                if killer.kill_now:
                    break
                    database = get_db()
                    if database != None:
                        database.close()
    except filelock.Timeout:
        log_error("File lock timeout")
    
        
log_info("End of the program. I was killed gracefully :)")
