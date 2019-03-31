import argparse
import sys

from typing import Optional, Union

import requests

from flask import Flask, request

from jeopardy.game import Game, get_random_question
from jeopardy.model import AnswerResponse, GameState, Question, RegisterRequest
from jeopardy.utils.flask_utils import FlaskResponse, error, get_player_id, no_content, to_json


app = Flask(__name__)
game = Game()


@app.route('/')
@to_json
def root() -> GameState:
    return GameState(statistics=game.stats, players=game.players)


@app.route('/register', methods=['POST'])
def register() -> FlaskResponse:
    try:
        register_req = RegisterRequest.from_request(request)
    except (TypeError, ValueError) as e:
        return error(f'Failed to parse register request: {e}', status=400)

    if not register_req.address:
        return error('No client address provided', status=400)

    if is_invalid_nick(register_req.nick, register_req.player_id):
        return error(f'Nick {register_req.nick} is already in use', status=400)

    # ping the client to make sure it's up
    resp = requests.get(f'http://{register_req.address}/id')
    if resp.ok and resp.text == register_req.player_id:
        game.register_player(register_req)
        print(f'Added player {register_req.player_id} ({register_req.address})')
        return no_content()
    print(f'Failed to add player {register_req.player_id} ({register_req.address})')
    return error('Failed to connect to client')


@app.route('/goodbye', methods=['POST'])
def goodbye() -> FlaskResponse:
    player_id = get_player_id()
    game.remove_player(player_id)
    print(f'Removed player {player_id}')
    return no_content()


@app.route('/start', methods=['POST'])
def start_game() -> FlaskResponse:
    try:
        game.start()
    except RuntimeError as e:
        return error(str(e))
    return no_content()


@app.route('/question')
@to_json
def get_question() -> Union[Optional[Question], FlaskResponse]:
    with game.lock:
        if game.current_question is not None:
            return game.current_question
    question = get_random_question()
    if question is None:
        return error('Failed to fetch question from TrivialBuzz API')
    game.update_current_question(question)
    return game.current_question


@app.route('/answer', methods=['POST'])
@to_json
def submit_answer() -> Union[AnswerResponse, FlaskResponse]:
    if game.current_question is None:
        return error('There is no current question', status=400)

    correct, close, value = game.check_guess(request.get_data(as_text=True))
    return AnswerResponse(is_correct=correct, is_close=close, value=value)


@app.route('/chat', methods=['POST'])
def chat() -> FlaskResponse:
    game.post_chat_message(request.get_data(as_text=True))
    return no_content()


@app.route('/nick', methods=['POST'])
def change_nick() -> FlaskResponse:
    player_id = get_player_id()
    if player_id not in game.players or not game.players[player_id].is_active:
        return error('Cannot change nick for an inactive player', status=400)
    new_nick = request.get_data(as_text=True)
    if not new_nick:
        return error('No nickname provided', status=400)
    if is_invalid_nick(new_nick, player_id):
        return error(f'Nick {new_nick} is already in use', status=400)
    if new_nick != game.players[player_id].nick:
        game.change_nick(new_nick)
    return no_content()


def is_invalid_nick(nick, player_id) -> bool:
    return any(
        player.nick == nick and player.player_id != player_id
        for player in game.players.values()
    )


def parse_args(args) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run a "Jeopardy!" server for players to connect to')
    parser.add_argument('-s', '--server_address', default='0.0.0.0',
                        help='The IP address on which to run the server')
    parser.add_argument('-p', '--port', type=int, default=8008,
                        help='The port on which to run the server')
    return parser.parse_args(args)


def main(args=None) -> None:
    if args is None:
        args = sys.argv[1:]
    parsed_args = parse_args(args)
    try:
        app.run(host=parsed_args.server_address, port=parsed_args.port)
    finally:
        print('\nSaving game file')
        game.save_game_file()


if __name__ == '__main__':
    main()
