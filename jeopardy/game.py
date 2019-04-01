import datetime
import json
import os
import re
import string
import time
import uuid

from concurrent.futures import ThreadPoolExecutor as Pool
from difflib import SequenceMatcher
from threading import Lock, RLock
from typing import Any, Dict, Optional, Tuple

import requests

from nltk.corpus import stopwords
from nltk.stem.snowball import EnglishStemmer

from jeopardy.model import Event, GameInfo, GameState, NickUpdate, PlayerInfo, Question, RegisterRequest
from jeopardy.utils.flask_utils import get_player_id


MATCH_RATIO_THRESHOLD = 0.75
QUESTION_TIMEOUT_SECONDS = 30
REMOVE_PUNCTUATION_TRANSLATIONS = {ord(char): None for char in string.punctuation}

ANSWER_RE = re.compile(r'\([^()]*\)|[^()]+')
URL_RE = re.compile(r'<a[^>]+>(?P<text>[^<]+)</a>')


stemmer = EnglishStemmer()


class Game:

    DEFAULT_FILEPATH = 'jeopardy_game.json'

    def __init__(self, load_from_file: bool = True) -> None:
        self.players = {}
        self.stats = GameInfo()
        self.current_question = None
        self.in_progress = False
        self.lock = RLock()
        self.pool = Pool(8)
        self.file_lock = Lock()
        if load_from_file:
            self.load_game_file()

    def load_game_file(self) -> None:
        with self.file_lock:
            if os.path.exists(self.DEFAULT_FILEPATH):
                with open(self.DEFAULT_FILEPATH) as game_file:
                    game = GameState.from_json(json.load(game_file))
                self.stats = game.statistics
                self.players = game.players

    def save_game_file(self) -> None:
        with self.file_lock:
            game_state = GameState(statistics=self.stats, players=self.players)
            game = game_state.to_json()
            for player in game['players'].values():
                del player['client_address']
                del player['is_active']
            with open(self.DEFAULT_FILEPATH, 'w') as game_file:
                json.dump(game, game_file, sort_keys=True, indent=4)

    def register_player(self, register_req: RegisterRequest) -> None:
        player_id = register_req.player_id
        if player_id in self.players and self.players[player_id].is_active:
            # if they're already active, just update address/nick and return
            player = self.players[player_id]
            print(f'Player {player_id} has moved from {player.client_address} to {register_req.address}')
            player.client_address = register_req.address
            player.last_active_time = datetime.datetime.utcnow()
            if register_req.nick and register_req.nick != player.nick:
                print(f'Player {player_id} (a/k/a {player.nick}) is now known as {register_req.nick}')
                self.change_nick(register_req.nick)
            return
        if player_id in self.players:
            player = self.players[player_id]
            player.client_address = register_req.address
            if register_req.nick:
                player.nick = register_req.nick
            player.is_active = True
        else:
            player = PlayerInfo(
                player_id=player_id,
                client_address=register_req.address,
                nick=register_req.nick,
                is_active=True
            )
            self.players[player_id] = player
        event = self.make_event('NEW_PLAYER')
        self.notify(event)

    def remove_player(self, player_id: str) -> None:
        if player_id in self.players:
            self.players[player_id].client_address = None
            self.players[player_id].is_active = False
            event = self.make_event('PLAYER_LEFT')
            self.notify(event)

    def get_player(self, player_id: str) -> Optional[PlayerInfo]:
        return self.players.get(player_id)

    def make_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Event:
        if payload is None:
            payload = {}
        try:
            player_id = get_player_id()
        except RuntimeError:
            player = None
        else:
            player = self.get_player(player_id)
            player.last_active_time = datetime.datetime.utcnow()
        return Event(event_type=event_type, payload=payload, player=player)

    def notify(self, event: Event) -> None:
        self.pool.submit(self.notify_players, event)

    def notify_players(self, event: Event) -> None:
        event_json = event.to_json()
        for player_id, player in self.players.items():
            if player.is_active:
                resp = requests.post(f'http://{player.client_address}/notify', json=event_json)
                if not resp.ok:
                    print(f'Failed to notify player: {resp.text}')

    def start(self) -> None:
        with self.lock:
            if not self.in_progress:
                self.notify(self.make_event('NEW_GAME'))
                question = get_random_question()
                if question is None:
                    raise RuntimeError('Failed to fetch starting question')
                self.in_progress = True
                self.update_current_question(question)

    def update_current_question(self, question: Optional[Question]) -> None:
        with self.lock:
            if self.current_question is None or question is None:
                self.current_question = question
                if question is not None:
                    self.stats.questions_asked += 1
                    event = self.make_event(
                        event_type='NEW_QUESTION',
                        payload=question.to_json()
                    )
                    self.notify(event)
                    self.pool.submit(self.question_timeout, question)

    def check_guess(self, guess: str) -> Tuple[bool, bool, int]:
        with self.lock:
            if self.current_question is None:
                return False, False, 0
            question = self.current_question
        correct, close = check_guess(guess, question.answer)
        player = self.get_player(get_player_id())
        player.total_answers += 1
        self.stats.total_answers += 1
        if correct:
            player.correct_answers += 1
            player.score += question.value
            self.stats.total_correct_answers += 1
            self.stats.questions_answered += 1
            self.update_current_question(None)
        event = self.make_event(
            event_type='NEW_ANSWER',
            payload={
                'answer': guess,
                'is_close': close,
                'is_correct': correct,
                'value': question.value if correct else 0,
            }
        )
        self.notify(event)
        return correct, close, question.value

    def post_chat_message(self, message: str) -> None:
        event = self.make_event(
            event_type='CHAT_MESSAGE',
            payload={'message': message}
        )
        self.notify(event)

    def change_nick(self, new_nick: str) -> None:
        player = self.get_player(get_player_id())
        if not player.is_active:
            return
        old_nick = player.nick
        player.nick = new_nick
        nick_update = NickUpdate(old_nick, new_nick)
        event = self.make_event(
            event_type='NICK_CHANGED',
            payload=nick_update.to_json()
        )
        self.notify(event)

    def is_current_question(self, question_id: str) -> bool:
        return self.current_question is not None and self.current_question.question_id == question_id

    def question_timeout(self, question: Question) -> None:
        timeout = datetime.datetime.utcnow() + datetime.timedelta(seconds=QUESTION_TIMEOUT_SECONDS)
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


def get_random_question() -> Optional[Question]:
    resp = requests.get('http://www.trivialbuzz.com/api/v1/questions/random.json')
    if not resp.ok:
        return None
    resp_json = resp.json()
    if not resp_json:
        return None
    question_data = resp_json['question']
    return Question(
        question_id=str(uuid.uuid4()),
        text=sanitize_question(question_data['body'][1:-1]),
        answer=sanitize_answer(question_data['response']),
        category=question_data['category']['name'],
        value=question_data['value']
    )


def sanitize_question(question: str) -> str:
    # replace '<a href="...">text</a>' with 'text'
    question = URL_RE.sub(lambda match: match.group('text'), question)
    # replace HTML line breaks with newlines
    question = question.replace('<br />', '\n')
    # strip out backslashes
    question = question.replace('\\', '')
    # strip leading/trailing whitespace
    return question.strip()


def sanitize_answer(answer: str) -> str:
    # strip out backslashes and leading/trailing whitespace
    return answer.replace('\\', '').strip()


def check_guess(guess: str, correct_answer: str) -> Tuple[bool, bool]:
    potential_answers = ANSWER_RE.findall(correct_answer)
    if len(potential_answers) == 2:
        for potential_answer in potential_answers:
            potential_answer = potential_answer.replace('(', '').replace(')', '')
            correct, close = check_guess(guess, potential_answer)
            if correct:
                return correct, close

    sequence_matcher = SequenceMatcher(None, guess, correct_answer)
    if sequence_matcher.ratio() >= MATCH_RATIO_THRESHOLD:
        return True, False

    guess_tokens = [process_token(token) for token in guess.split()]
    processed_answer_tokens = [process_token(token) for token in correct_answer.split()]
    answer_tokens = [tok for tok in processed_answer_tokens if tok not in stopwords.words('english')]
    matched = set(guess_tokens).intersection(set(answer_tokens))
    return len(matched) == len(answer_tokens), len(matched) > 0


def process_token(token: str) -> str:
    return stemmer.stem(token.lower().translate(REMOVE_PUNCTUATION_TRANSLATIONS))
