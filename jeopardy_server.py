import requests

from flask import Flask, jsonify, request

from flask_utils import error, get_client_id, no_content, to_json
from jeopardy_game import Game, get_random_question
from jeopardy_model import Answer, AnswerResponse, ClientIDResponse, RegisterRequest


app = Flask(__name__)
game = Game()


@app.route('/')
def root():
    return jsonify({
        'clients': {
            client_id: client.to_json() for client_id, client in game.clients.items()
        }
    })


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

    correct = game.check_guess(answer.text)
    return AnswerResponse(correct)
