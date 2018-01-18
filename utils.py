import uuid
import hashlib
import string
import random
import sys

import unidecode
 
from jinja2 import Template
from jinja2 import Environment, BaseLoader, FileSystemLoader
from jinja2 import Markup
import markdown

import sys
import praw
import unicodedata

from mail_lib import SendMessage

from datetime import datetime
import os

import signal

def is_debug():
    import os
    return 'KINDDIT_DEBUG' in os.environ

config_archive = None

def get_config():
    global config_archive

    if config_archive is not None:
        return config_archive
    
    from YamJam import yamjam
    if is_debug():
        debug_path = os.path.dirname(os.path.realpath(__file__)) + '/internal/debug_config.yaml'
        print("Loading internal debug file:" + debug_path)
        config_archive = yamjam(debug_path)
    else:
        config_archive = yamjam('/home/configs/config.yaml')
    return config_archive
    
sender = get_config()['sender']

from prawcore import NotFound
def reddit_exists(r, name):
    try:
        x = r.subreddits.search_by_name(query=name, include_nsfw=False, exact=True)
        return True
    except NotFound:
        return False
 
def file_get_contents(filename):
    with open(filename) as f:
        return f.read()

def file_get_contents_b(filename):
    with open(filename, 'rb') as f:
        return f.read()
 
def hash_password(password):
    # uuid is used to generate a random number
    salt = uuid.uuid4().hex
    return hashlib.sha256(salt.encode() + password.encode()).hexdigest() + ':' + salt
    
def check_password(hashed_password, user_password):
    password, salt = hashed_password.split(':')
    return password == hashlib.sha256(salt.encode() + user_password.encode()).hexdigest()

def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def get_date_from_submission(submission):
    time = submission.created
    return datetime.fromtimestamp(time)
"""
''' was thinking of: reddit.{id, creation_date} => (id, creation-date)
''' but creation_date is the same as the reddit .. so it's not worth having it.
"""
#def serialise_article_for_archive(submission):
    #return "(" + submission.id + "," + submission.created + "),"

def serialise_article_for_archive(submission):
    separator_between_other_serialised = ","
    return submission['id'] + separator_between_other_serialised


def encode_articles_for(subs, archive):
    r = praw.Reddit("bot", user_agent="bot2")
    
    customid = 1
    
    articles = []
    for sub in subs:
        try:
            submissions = r.subreddit(sub.subreddit).hot(limit=sub.per_email)
            submissions_serialised = []
            for x in submissions:
                submissions_serialised += [{
                    'id':x.id,
                    'fullname':x.fullname,
                    'score': x.score,
                    'title': x.title,
                    'content': x.selftext.strip(),
                    'link': x.shortlink,
                    'author': x.author.name,
                    'sub': sub.subreddit,
                    'customid': customid,
                    'isfirstarchived': False,
                    'archived': x.id in archive
                }]
                customid = customid + 1
            print("Got " + str(len(submissions_serialised)) + " articles from " + str(sub.subreddit) + ".")


            #articles += submissions_serialised
            #order by NOT archived first (two fors)
            for submission_ser in submissions_serialised:
                if not submission_ser['archived']:
                    articles += [submission_ser]
            isfirstarchived = True
            for submission_ser in submissions_serialised:
                if submission_ser['archived']:
                    if isfirstarchived:
                        submission_ser['isfirstarchived'] = True
                        isfirstarchived = False
                    
                    articles += [submission_ser]
        except NotFound:
            print("NOT FOUND: " + sub.subreddit)
        except Exception as e: #prawcore.exceptions.NotFound 404
            print("Unexpected error in get submissions")# except all
            import traceback
            print(traceback.format_exception(None, # <- type(e) by docs, but ignored 
                             e, e.__traceback__),
                            file=sys.stderr, flush=True)
                             
            print(traceback.format_exc())
    
    return articles
    
 
def generate_html(username, articles, output_file, title):
    template_str = file_get_contents("templates/book.html")
    env = Environment(loader=FileSystemLoader("templates"))

    md = markdown.Markdown(extensions=['meta'])

    env.filters['markdown'] = lambda text: Markup(md.convert(text))

    t = env.from_string(template_str)
    output_size = 0
    with open(output_file, "w", encoding="utf-8") as text_file:
        output = t.render(title=title, username=username, articles=articles)  # try catch ..
        #print("size before unidecode:" + str(len(output)))
        output = unidecode.unidecode(output)
        #print("size after unidecode:" + str(len(output)))
        output_size = len(output)
        text_file.write(output)
    return output_size

def send_kindler(to, file):
    global sender
    #to = "catalin_web@yahoo.com"
    subject = "Yet another book"
    html = "Hi<br/>Kindler."
    plain = "Hi\nKindler."
    SendMessage(sender, to, subject, html, plain, file)

def send_mmail(to, subject, html, plain):
    global sender
    SendMessage(sender, to, subject, html, plain)
def send_email_activation(to, activation_key):
    subject = "Kinddit - Account Activation"
    html = "Hi, Kinddit here.<br/>Your activation key is: <b>" + str(activation_key) + "</b>"
    plain = "Hi, Kinddit here.\nYour activation key is: " + str(activation_key)
    SendMessage(sender, to, subject, html, plain)


def json_converter(o):
    if isinstance(o, datetime):
        return o.__str__()


def get_datetime_today_3_30():
    now = datetime.now()
    return now.replace(hour=3, minute=30, second=0)
def get_datetime_today_4_00():
    now = datetime.now()
    return now.replace(hour=4, minute=0, second=0)

#def diff14days(testing):
#    now = datetime.now()
#    return testing + timedelta(days=14) < now

class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True
    print("SIGINT or SIGTERM triggered")






