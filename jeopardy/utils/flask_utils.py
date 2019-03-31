from functools import wraps
from typing import Callable, Tuple

from flask import jsonify, request

from jeopardy.model import Model


FlaskResponse = Tuple[str, int]


def to_json(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        result = view(*args, **kwargs)
        if isinstance(result, tuple):
            return result
        if isinstance(result, Model):
            result = result.to_json()
        return jsonify(result)
    return wrapper


def error(message: str, status: int = 500) -> FlaskResponse:
    return jsonify({'error': message, 'status': status}), status


def no_content() -> FlaskResponse:
    return '', 204


def get_player_id() -> str:
    return request.headers['X-Jeopardy-Player-ID']
