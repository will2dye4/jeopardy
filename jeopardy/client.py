import os
import uuid

from typing import Any, Optional

import requests

from jeopardy.model import AnswerResponse, GameState, Question, RegisterRequest


class JeopardyClient:

    def __init__(self, server_address: Optional[str] = None, player_id: Optional[str] = None) -> None:
        if server_address is None:
            server_address = os.getenv('JEOPARDY_SERVER_ADDRESS')
            if server_address is None:
                raise ValueError('Must provide server_address or set JEOPARDY_SERVER_ADDRESS environment variable')
        self.player_id = player_id or str(uuid.uuid4())
        self.server_address = server_address
        self.server_session = requests.Session()
        self.server_session.headers.update({'X-Jeopardy-Player-ID': self.player_id})

    def __enter__(self) -> 'JeopardyClient':
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def server_url(self, path: str) -> str:
        return f'http://{self.server_address}{path}'

    def get(self, path: str, *args, **kwargs) -> requests.Response:
        return self.server_session.get(self.server_url(path), *args, **kwargs)

    def post(self, path: str, *args, **kwargs) -> requests.Response:
        return self.server_session.post(self.server_url(path), *args, **kwargs)

    def get_game_state(self) -> Optional[GameState]:
        resp = self.get('/')
        if resp.ok:
            try:
                return GameState.from_response(resp)
            except (TypeError, ValueError) as e:
                print(f'Failed to parse game state response: {e}')
                return None
        else:
            print(f'Failed to fetch state from server: {resp.text}')
            return None

    def register(self, address: str, nick: str) -> None:
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

    def goodbye(self) -> None:
        self.post('/goodbye')

    def start_game(self) -> None:
        resp = self.post('/start')
        if not resp.ok:
            raise RuntimeError(f'Failed to start game: {resp.text}')

    def get_question(self) -> Optional[Question]:
        resp = self.get('/question')
        if resp.ok:
            return Question.from_response(resp)
        else:
            print('Failed to get question from server')
            return None

    def answer(self, guess: str) -> Optional[AnswerResponse]:
        resp = self.post('/answer', data=guess)
        if resp.ok:
            try:
                return AnswerResponse.from_response(resp)
            except (TypeError, ValueError) as e:
                print(f'Failed to parse answer response: {e}')
                return None
        else:
            print(f'Failed to submit answer to server: {resp.text}')
            return None

    def chat(self, message: str) -> None:
        resp = self.post('/chat', data=message)
        if not resp.ok:
            print(f'Failed to post chat message: {resp.text}')

    def change_nick(self, new_nick: str) -> bool:
        resp = self.post('/nick', data=new_nick)
        if not resp.ok:
            print(f'Failed to change nick: {resp.text}')
        return resp.ok

    def close(self) -> None:
        self.goodbye()  # tell the server we are going away
