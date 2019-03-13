import datetime
import re
import string
import time
import uuid

from concurrent.futures import ThreadPoolExecutor as Pool
from difflib import SequenceMatcher
from threading import RLock

import requests

from nltk.corpus import stopwords
from nltk.stem.snowball import EnglishStemmer

from flask_utils import get_client_id
from jeopardy_model import ClientInfo, Event, Question


MATCH_RATIO_THRESHOLD = 0.75
REMOVE_PUNCTUATION_TRANSLATIONS = {ord(char): None for char in string.punctuation}


stemmer = EnglishStemmer()


class Game:

    def __init__(self):
        self.clients = {}
        self.current_question = None
        self.in_progress = False
        self.lock = RLock()
        self.pool = Pool(8)

    def register_client(self, register_req):
        if register_req.client_id not in self.clients:
            client = ClientInfo(
                client_id=register_req.client_id,
                client_address=register_req.address,
                nick=register_req.nick
            )
            self.clients[register_req.client_id] = client
            event = Event(
                event_type='NEW_PLAYER',
                payload=client.to_json()
            )
            self.notify(event)

    def remove_client(self, client_id):
        if client_id in self.clients:
            client = self.clients[client_id]
            del self.clients[client_id]
            event = Event(
                event_type='PLAYER_LEFT',
                payload=client.to_json()
            )
            self.notify(event)

    def get_client(self, client_id):
        return self.clients.get(client_id)

    def notify(self, event, exclude=None):
        self.pool.submit(self.notify_clients, event, exclude=exclude)

    def notify_clients(self, event, exclude=None):
        if exclude is None:
            exclude = set()
        event_json = event.to_json()
        for client_id, client_info in self.clients.items():
            if client_id not in exclude:
                resp = requests.post(f'http://{client_info.client_address}/notify', json=event_json)
                if not resp.ok:
                    print(f'Failed to notify client: {resp.text}')

    def start(self):
        with self.lock:
            if not self.in_progress:
                self.notify(Event(event_type='NEW_GAME', payload={}))
                question = get_random_question()
                if question is None:
                    raise RuntimeError('Failed to fetch starting question')
                self.in_progress = True
                self.update_current_question(question)

    def update_current_question(self, question, client_id=None):
        with self.lock:
            if self.current_question is None or question is None:
                self.current_question = question
                if question is not None:
                    event = Event(
                        event_type='NEW_QUESTION',
                        payload=question.to_json()
                    )
                    exclude = {client_id} if client_id is not None else None
                    self.notify(event, exclude=exclude)
                    self.pool.submit(self.question_timeout, question)

    def check_guess(self, guess):
        correct = check_guess(guess, self.current_question.answer)
        client = self.get_client(get_client_id())
        client.total_answers += 1
        if correct:
            client.correct_answers += 1
            client.score += self.current_question.value
            self.update_current_question(None)
        event = Event(
            event_type='NEW_ANSWER',
            payload={
                'answer': guess,
                'client': client.to_json(),
                'is_correct': correct
            }
        )
        self.notify(event)
        return correct

    def is_current_question(self, question_id):
        return self.current_question is not None and self.current_question.question_id == question_id

    def question_timeout(self, question):
        timeout = datetime.datetime.utcnow() + datetime.timedelta(seconds=30)
        while self.is_current_question(question.question_id) and datetime.datetime.utcnow() < timeout:
            time.sleep(0.1)
        with self.lock:
            if self.is_current_question(question.question_id):
                self.current_question = None
                event = Event(
                    event_type='QUESTION_TIMEOUT',
                    payload={'answer': question.answer}
                )
                self.notify(event)


def get_random_question():
    resp = requests.get('http://www.trivialbuzz.com/api/v1/questions/random.json')
    if not resp.ok:
        return None
    resp_json = resp.json()
    if not resp_json:
        return None
    question_data = resp_json['question']
    return Question(
        question_id=str(uuid.uuid4()),
        text=question_data['body'][1:-1],
        answer=question_data['response'],
        category=question_data['category']['name'],
        value=question_data['value']
    )


def check_guess(guess, correct_answer):
    potential_answers = re.findall(r'\([^()]*\)|[^()]+', correct_answer)
    if len(potential_answers) == 2:
        for potential_answer in potential_answers:
            potential_answer = potential_answer.replace('(', '').replace(')', '')
            if check_guess(guess, potential_answer):
                return True

    sequence_matcher = SequenceMatcher(None, guess, correct_answer)
    if sequence_matcher.ratio() >= MATCH_RATIO_THRESHOLD:
        return True

    guess_tokens = [process_token(token) for token in guess.split()]
    processed_answer_tokens = [process_token(token) for token in correct_answer.split()]
    answer_tokens = [tok for tok in processed_answer_tokens if tok not in stopwords.words('english')]
    matched = set(guess_tokens).intersection(set(answer_tokens))
    return len(matched) == len(answer_tokens)


def process_token(token):
    return stemmer.stem(token.lower().translate(REMOVE_PUNCTUATION_TRANSLATIONS))
