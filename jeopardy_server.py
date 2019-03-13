#!/usr/bin/env python3

import requests

from flask import Flask, jsonify, request

from flask_utils import error, get_client_id, no_content
from jeopardy_model import ClientIDResponse, RegisterRequest


app = Flask(__name__)


class Game:

    def __init__(self):
        self.clients = {}
        self.in_progress = False

    def register_client(self, register_req):
        if register_req.client_id not in self.clients:
            self.clients[register_req.client_id] = register_req.address

    def remove_client(self, client_id):
        if client_id in self.clients:
            del self.clients[client_id]


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
