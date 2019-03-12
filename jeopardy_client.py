#!/usr/bin/env python3

import random
import subprocess
import uuid

from multiprocessing import Process
from threading import Thread

import requests

from flask import Flask, request


class JeopardyClient:

    def __init__(self, server_address):
        def root():
            print('Received request to /')
            return 'Client OK'

        self.server_address = server_address
        self.client_id = str(uuid.uuid4())
        app = Flask(f'jeopardy-client-{self.client_id}')
        app.logger.setLevel('ERROR')
        app.route('/')(root)
        port = random.randrange(65000, 65536)
        self.app_process = Process(target=app.run, kwargs={'host': '0.0.0.0', 'port': port})
        self.app_process.start()
        print(f'Client app running on port {port}')
        external_ip = subprocess.getoutput(r'ifconfig | grep -A3 en0 | grep -E "inet\b" | cut -d" " -f2')
        if not external_ip:
            raise RuntimeError('failed to find external IP')
        payload = {
            'address': f'{external_ip}:{port}',
            'client_id': self.client_id,
        }
        resp = requests.post(f'http://{self.server_address}/register', json=payload)
        if not resp.ok:
            print(f'Failed to register with server: {resp.text}')
        print('Registered with server')

    def close(self):
        print('Stopping client app')
        self.app_process.terminate()
        self.app_process.join()
        print('Client app stopped')
