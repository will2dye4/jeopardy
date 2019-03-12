#!/usr/bin/env python3

import os
import random
import subprocess
import sys
import uuid

from multiprocessing import Process

import requests

from flask import Flask, request


def app_target(app, port, outfile):
    # redirect output from the flask server
    sys.stderr = outfile
    sys.stdout = outfile
    app.run(host='0.0.0.0', port=port)


class JeopardyClient:

    def __init__(self, server_address):
        self.server_address = server_address
        self.client_id = str(uuid.uuid4())
        self.devnull = open(os.devnull, 'w')
        app = Flask(f'jeopardy-client-{self.client_id}')
        app.logger.setLevel('ERROR')
        app.route('/')(self.root)
        port = random.randrange(65000, 65536)
        self.app_process = Process(target=app_target, args=(app, port, self.devnull))
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def root():
        print('Received request to /')
        return 'Client OK'

    def close(self):
        print('Stopping client app')
        self.app_process.terminate()
        self.app_process.join()
        self.app_process.close()
        print('Client app stopped')
        self.devnull.close()
