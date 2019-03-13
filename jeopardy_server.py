#!/usr/bin/env python3

import datetime
import re
import string
import time
import uuid

from concurrent.futures import ThreadPoolExecutor as Pool
from difflib import SequenceMatcher
from threading import Lock

import requests

from flask import Flask, jsonify, request
from nltk.corpus import stopwords
from nltk.stem.snowball import EnglishStemmer

from flask_utils import error, get_client_id, no_content, to_json
from jeopardy_model import Answer, AnswerResponse, ClientIDResponse, Event, Question, RegisterRequest


MATCH_RATIO_THRESHOLD = 0.75
REMOVE_PUNCTUATION_TRANSLATIONS = {ord(char): None for char in string.punctuation}


app = Flask(__name__)
pool = Pool(4)
stemmer = EnglishStemmer()


class Game:

    def __init__(self):
        self.clients = {}
        self.current_question = None
        self.in_progress = False
        self.lock = Lock()

    def register_client(self, register_req):
        if register_req.client_id not in self.clients:
            self.clients[register_req.client_id] = register_req.address

    def remove_client(self, client_id):
        if client_id in self.clients:
            del self.clients[client_id]

    def notify_clients(self, event):
        event_json = event.to_json()
        for client_address in self.clients.values():
            resp = requests.post(f'http://{client_address}/notify', json=event_json)
            if not resp.ok:
                print(f'Failed to notify client: {resp.text}')

    def update_current_question(self, question):
        with self.lock:
            self.current_question = question
        if question is not None:
            pool.submit(self.question_timeout, question.question_id)

    def is_current_question(self, question_id):
        return self.current_question is not None and self.current_question.question_id == question_id

    def question_timeout(self, question_id):
        timeout = datetime.datetime.utcnow() + datetime.timedelta(seconds=30)
        while self.is_current_question(question_id) and datetime.datetime.utcnow() < timeout:
            time.sleep(0.1)
        with self.lock:
            if self.is_current_question(question_id):
                self.current_question = None
                pool.submit(game.notify_clients, Event('QUESTION_TIMEOUT'))


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


@app.route('/question')
@to_json
def get_question():
    if game.current_question is not None:
        return game.current_question
    resp = requests.get('http://www.trivialbuzz.com/api/v1/questions/random.json')
    if not resp.ok:
        return error('Failed to fetch question from TrivialBuzz API')
    resp_json = resp.json()
    if not resp_json:
        return error('Received invalid response from TrivialBuzz API')
    question_data = resp_json['question']
    question = Question(
        question_id=str(uuid.uuid4()),
        text=question_data['body'][1:-1],
        answer=question_data['response'],
        category=question_data['category']['name'],
        value=question_data['value']
    )
    game.update_current_question(question)
    return question


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
    return AnswerResponse(correct)


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
