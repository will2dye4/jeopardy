from functools import wraps

from flask import jsonify, request

from jeopardy_model import Model


def to_json(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        result = view(*args, **kwargs)
        if isinstance(result, tuple):
            return result
        if isinstance(result, Model):
            result = result.to_json()
        return jsonify(result)
    return wrapper


def error(message, status=500):
    return jsonify({'error': message, 'status': status}), status


def no_content():
    return '', 204


def get_player_id():
    return request.headers['X-Jeopardy-Player-ID']
