import datetime

from dataclasses import dataclass
from typing import Any, Dict


class Model:

    @classmethod
    def from_request(cls, request):
        request_json = request.get_json()
        if not request_json:
            raise ValueError('No request JSON')
        return cls.from_json(request_json)

    @classmethod
    def from_response(cls, response):
        response_json = response.json()
        if not response_json:
            raise ValueError('No response JSON')
        return cls.from_json(response_json)

    @classmethod
    def from_json(cls, json):
        if json is None:
            return json
        fields = {}
        for key, value in json.items():
            field_type = cls.__dataclass_fields__[key].type
            if field_type == datetime.datetime and isinstance(value, str):
                value = datetime.datetime.fromisoformat(value)
            elif isinstance(field_type, type) and issubclass(field_type, Model):
                value = field_type.from_json(value)
            fields[key] = value
        return cls(**fields)

    def to_json(self):
        json = {}
        for key in self.__dataclass_fields__.keys():
            value = getattr(self, key)
            if isinstance(value, datetime.datetime):
                value = value.isoformat()
            elif isinstance(value, Model):
                value = value.to_json()
            json[key] = value
        return json


@dataclass
class PlayerInfo(Model):
    player_id: str
    client_address: str
    nick: str
    correct_answers: int = 0
    total_answers: int = 0
    score: int = 0
    is_active: bool = False
    last_active_time: datetime.datetime = None


@dataclass
class GameInfo(Model):
    questions_asked: int = 0
    questions_answered: int = 0
    total_answers: int = 0
    total_correct_answers: int = 0


@dataclass
class GameState(Model):
    statistics: GameInfo
    players: Dict[str, PlayerInfo]

    @classmethod
    def from_json(cls, json):
        for player_id, player in json['players'].items():
            if 'client_address' not in player:
                player['client_address'] = None
            json['players'][player_id] = PlayerInfo.from_json(player)
        return super().from_json(json)

    def to_json(self):
        self.players = {
            player_id: player.to_json()
            for player_id, player in self.players.items()
        }
        return super().to_json()


@dataclass
class RegisterRequest(Model):
    address: str
    player_id: str
    nick: str


@dataclass
class Question(Model):
    question_id: str
    text: str
    answer: str
    category: str
    value: int

    def to_json(self):
        json = super().to_json()
        json['answer'] = ''
        return json


@dataclass
class AnswerResponse(Model):
    is_correct: bool
    is_close: bool
    value: int


@dataclass
class NickUpdate(Model):
    old_nick: str
    new_nick: str


@dataclass
class Event(Model):
    event_type: str
    player: PlayerInfo
    payload: Dict[str, Any]


@dataclass
class ClientConfig(Model):
    player_id: str
    server_address: str
    nick: str
    dark_mode: bool = False
    client_port: int = None
