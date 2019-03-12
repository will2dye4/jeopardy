#!/usr/bin/env python3

import requests

from flask import Flask, request


app = Flask(__name__)
clients = {}


class Game:
    pass


@app.route('/')
def root():
    return 'Server OK'


@app.route('/register', methods=['POST'])
def register():
    request_json = request.get_json()
    if not request_json:
        return 'Failed to parse JSON', 400
    client_address = request_json.get('address')
    if not client_address:
        return 'Missing client address', 400
    client_id = request_json.get('client_id')
    if not client_id:
        return 'Missing client ID', 400
    # ping the client to make sure it's up
    resp = requests.get(f'http://{client_address}')
    if resp.ok and resp.text == 'Client OK':
        print(f'Added client ID {client_id} ({client_address})')
        clients[client_id] = client_address
        return 'Register OK'
    print(f'Failed to add client ID {client_id} ({client_address})')
    return 'Register fail', 500
