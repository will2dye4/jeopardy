#!/usr/bin/env python3

import datetime
import re
import string
import time
import uuid

from concurrent.futures import ThreadPoolExecutor as Pool
from difflib import SequenceMatcher
from threading import RLock

import requests

from flask import Flask, jsonify, request
from nltk.corpus import stopwords
from nltk.stem.snowball import EnglishStemmer

from flask_utils import error, get_client_id, no_content, to_json
from jeopardy_model import Answer, AnswerResponse, ClientIDResponse, Event, Question, RegisterRequest


MATCH_RATIO_THRESHOLD = 0.75
REMOVE_PUNCTUATION_TRANSLATIONS = {ord(char): None for char in string.punctuation}


app = Flask(__name__)
pool = Pool(8)
stemmer = EnglishStemmer()


class Game:

    def __init__(self):
        self.clients = {}
        self.current_question = None
        self.in_progress = False
        self.lock = RLock()

    def register_client(self, register_req):
        if register_req.client_id not in self.clients:
            self.clients[register_req.client_id] = register_req.address
            event = Event(
                event_type='NEW_PLAYER',
                payload={'client_id': register_req.client_id}
            )
            pool.submit(self.notify_clients, event)

    def remove_client(self, client_id):
        if client_id in self.clients:
            del self.clients[client_id]
            event = Event(
                event_type='PLAYER_LEFT',
                payload={'client_id': client_id}
            )
            pool.submit(self.notify_clients, event)

    def notify_clients(self, event, exclude=None):
        if exclude is None:
            exclude = set()
        event_json = event.to_json()
        for client_id, client_address in self.clients.items():
            if client_id not in exclude:
                resp = requests.post(f'http://{client_address}/notify', json=event_json)
                if not resp.ok:
                    print(f'Failed to notify client: {resp.text}')

    def start(self):
        with self.lock:
            if not self.in_progress:
                pool.submit(self.notify_clients, Event(event_type='NEW_GAME', payload={}))
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
                    pool.submit(self.notify_clients, event, exclude=exclude)
                    pool.submit(self.question_timeout, question)

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
                pool.submit(game.notify_clients, event)


game = Game()


@app.route('/')
def root():
    return jsonify({'clients': game.clients})


@app.route('/register', methods=['POST'])
def register():
    try:
        register_req = RegisterRequest.from_request(request)
    except (TypeError, ValueError) as e:
        return error(f'Failed to parse register request: {e}', status=400)
    # ping the client to make sure it's up
    resp = requests.get(f'http://{register_req.address}/id')
    if resp.ok:
        try:
            client_id_resp = ClientIDResponse.from_response(resp)
        except (TypeError, ValueError) as e:
            return error(f'Failed to parse response from client: {e}')
        if client_id_resp.client_id == register_req.client_id:
            game.register_client(register_req)
            print(f'Added client {register_req.client_id} ({register_req.address})')
            return no_content()
    print(f'Failed to add client {register_req.client_id} ({register_req.address})')
    return error('Failed to connect to client')


@app.route('/goodbye', methods=['POST'])
def goodbye():
    client_id = get_client_id()
    game.remove_client(client_id)
    print(f'Removed client {client_id}')
    return no_content()


@app.route('/start', methods=['POST'])
def start_game():
    try:
        game.start()
    except RuntimeError as e:
        return error(str(e))
    return no_content()


@app.route('/question')
@to_json
def get_question():
    with game.lock:
        if game.current_question is not None:
            return game.current_question
    question = get_random_question()
    if question is None:
        return error('Failed to fetch question from TrivialBuzz API')
    game.update_current_question(question, get_client_id())
    return game.current_question


@app.route('/answer', methods=['POST'])
@to_json
def submit_answer():
    if game.current_question is None:
        return error('There is no current question', status=400)
    try:
        answer = Answer.from_request(request)
    except (TypeError, ValueError) as e:
        return error(f'Failed to parse answer: {e}', status=400)

    correct = check_guess(answer.text, game.current_question.answer)
    if correct:
        # TODO update scores
        game.update_current_question(None)

    event = Event(
        event_type='NEW_ANSWER',
        payload={
            'answer': answer.text,
            'client_id': get_client_id(),
            'is_correct': correct
        }
    )
    pool.submit(game.notify_clients, event)

    return AnswerResponse(correct)


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
    if len(matched) == len(answer_tokens):
        return True
    return False


def process_token(token):
    return stemmer.stem(token.lower().translate(REMOVE_PUNCTUATION_TRANSLATIONS))
