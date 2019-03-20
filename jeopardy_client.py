import os
import uuid

import requests

from jeopardy_model import AnswerResponse, Question, RegisterRequest


class JeopardyClient:

    def __init__(self, server_address=None, player_id=None):
        if server_address is None:
            server_address = os.getenv('JEOPARDY_SERVER_ADDRESS')
            if server_address is None:
                raise ValueError('Must provide server_address or set JEOPARDY_SERVER_ADDRESS environment variable')
        self.player_id = player_id or str(uuid.uuid4())
        self.server_address = server_address
        self.server_session = requests.Session()
        self.server_session.headers.update({'X-Jeopardy-Player-ID': self.player_id})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def server_url(self, path):
        return f'http://{self.server_address}{path}'

    def get(self, path, *args, **kwargs):
        return self.server_session.get(self.server_url(path), *args, **kwargs)

    def post(self, path, *args, **kwargs):
        return self.server_session.post(self.server_url(path), *args, **kwargs)

    def register(self, address, nick):
        register_req = RegisterRequest(
            address=address,
            player_id=self.player_id,
            nick=nick
        )
        resp = self.post('/register', json=register_req.to_json())
        if resp.ok:
            print('Registered with server')
        else:
            raise RuntimeError(f'Failed to register with server: {resp.text}')

    def goodbye(self):
        self.post('/goodbye')

    def start_game(self):
        resp = self.post('/start')
        if not resp.ok:
            raise RuntimeError(f'Failed to start game: {resp.text}')

    def get_question(self):
        resp = self.get('/question')
        if resp.ok:
            return Question.from_response(resp)
        else:
            print('Failed to get question from server')
            return None

    def answer(self, guess):
        resp = self.post('/answer', data=guess)
        if resp.ok:
            try:
                answer_resp = AnswerResponse.from_response(resp)
            except (TypeError, ValueError) as e:
                print(f'Failed to parse answer response: {e}')
                return None
            return answer_resp
        else:
            print('Failed to submit answer to server')
            return None

    def chat(self, message):
        resp = self.post('/chat', data=message)
        if not resp.ok:
            print(f'Failed to post chat message: {resp.text}')

    def change_nick(self, new_nick):
        resp = self.post('/nick', data=new_nick)
        if not resp.ok:
            print(f'Failed to change nick: {resp.text}')
        return resp.ok

    def close(self):
        self.goodbye()  # tell the server we are going away
