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

from flask_utils import get_player_id
from jeopardy_model import Event, PlayerInfo, Question


MATCH_RATIO_THRESHOLD = 0.75
REMOVE_PUNCTUATION_TRANSLATIONS = {ord(char): None for char in string.punctuation}


stemmer = EnglishStemmer()


class Game:

    def __init__(self):
        self.players = {}
        self.current_question = None
        self.in_progress = False
        self.lock = RLock()
        self.pool = Pool(8)

    def register_player(self, register_req):
        if register_req.player_id not in self.players:
            player = PlayerInfo(
                player_id=register_req.player_id,
                client_address=register_req.address,
                nick=register_req.nick
            )
            self.players[register_req.player_id] = player
            event = self.make_event('NEW_PLAYER')
            self.notify(event)

    def remove_player(self, player_id):
        if player_id in self.players:
            event = self.make_event('PLAYER_LEFT')
            del self.players[player_id]
            self.notify(event)

    def get_player(self, player_id):
        return self.players.get(player_id)

    def make_event(self, event_type, payload=None):
        if payload is None:
            payload = {}
        try:
            player_id = get_player_id()
        except RuntimeError:
            player = None
        else:
            player = self.get_player(player_id)
        return Event(event_type=event_type, payload=payload, player=player)

    def notify(self, event):
        self.pool.submit(self.notify_players, event)

    def notify_players(self, event):
        event_json = event.to_json()
        for player_id, player_info in self.players.items():
            resp = requests.post(f'http://{player_info.client_address}/notify', json=event_json)
            if not resp.ok:
                print(f'Failed to notify player: {resp.text}')

    def start(self):
        with self.lock:
            if not self.in_progress:
                self.notify(self.make_event('NEW_GAME'))
                question = get_random_question()
                if question is None:
                    raise RuntimeError('Failed to fetch starting question')
                self.in_progress = True
                self.update_current_question(question)

    def update_current_question(self, question):
        with self.lock:
            if self.current_question is None or question is None:
                self.current_question = question
                if question is not None:
                    event = self.make_event(
                        event_type='NEW_QUESTION',
                        payload=question.to_json()
                    )
                    self.notify(event)
                    self.pool.submit(self.question_timeout, question)

    def check_guess(self, guess):
        with self.lock:
            if self.current_question is None:
                return False
            question = self.current_question
        correct = check_guess(guess, question.answer)
        player = self.get_player(get_player_id())
        player.total_answers += 1
        if correct:
            player.correct_answers += 1
            player.score += question.value
            self.update_current_question(None)
        event = self.make_event(
            event_type='NEW_ANSWER',
            payload={
                'answer': guess,
                'is_correct': correct,
                'value': question.value if correct else 0,
            }
        )
        self.notify(event)
        return correct, question.value

    def post_chat_message(self, message):
        event = self.make_event(
            event_type='CHAT_MESSAGE',
            payload={'message': message}
        )
        self.notify(event)

    def is_current_question(self, question_id):
        return self.current_question is not None and self.current_question.question_id == question_id

    def question_timeout(self, question):
        timeout = datetime.datetime.utcnow() + datetime.timedelta(seconds=30)
        while self.is_current_question(question.question_id) and datetime.datetime.utcnow() < timeout:
            time.sleep(0.1)
        with self.lock:
            if self.is_current_question(question.question_id):
                self.current_question = None
                event = self.make_event(
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
        text=question_data['body'][1:-1].replace('<br />', '\n'),  # TODO more sanitization
        answer=question_data['response'],
        category=question_data['category']['name'].title(),
        value=question_data['value']
    )


# TODO return another variable indicating if the guess is close
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
