#!/usr/bin/env python3

import random
import subprocess
import time
import uuid

from multiprocessing import Process

import requests

from flask import Flask, request

from flask_utils import no_content, to_json
from jeopardy_model import Answer, AnswerResponse, ClientIDResponse, Event, Question, RegisterRequest


SUPPRESS_FLASK_LOGGING = True


class JeopardyClient:

    def __init__(self, server_address):
        self.client_id = str(uuid.uuid4())
        self.server_address = server_address
        self.server_session = requests.Session()
        self.server_session.headers.update({'X-Jeopardy-Client-ID': self.client_id})
        self.port = random.randrange(65000, 65536)
        self.app_process = self.start_app_process()
        self.register()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def server_url(self, path):
        return f'http://{self.server_address}{path}'

    def get(self, path, *args, **kwargs):
        return self.server_session.get(self.server_url(path), *args, **kwargs)

    def post(self, path, *args, **kwargs):
        return self.server_session.post(self.server_url(path), *args, **kwargs)

    def register(self):
        external_ip = subprocess.getoutput(r'ifconfig | grep -A3 en0 | grep -E "inet\b" | cut -d" " -f2')
        if not external_ip:
            raise RuntimeError('Failed to find external IP')
        register_req = RegisterRequest(address=f'{external_ip}:{self.port}', client_id=self.client_id)
        resp = self.post('/register', json=register_req.to_json())
        if resp.ok:
            print('Registered with server')
        else:
            raise RuntimeError(f'Failed to register with server: {resp.text}')

    def goodbye(self):
        self.post('/goodbye')

    def get_question(self):
        resp = self.get('/question')
        if resp.ok:
            question = Question.from_response(resp)
            print(f'Category: {question.category}')
            print(f'Value: ${question.value}')
            print(f'Question: {question.text}')
        else:
            print('Failed to get question from server')

    def answer_question(self, answer):
        answer_req = Answer(answer)
        resp = self.post('/answer', json=answer_req.to_json())
        if resp.ok:
            try:
                answer_resp = AnswerResponse.from_response(resp)
            except (TypeError, ValueError) as e:
                print(f'Failed to parse answer response: {e}')
            else:
                if answer_resp.is_correct:
                    print('Correct!')
                else:
                    print('Wrong.')
        else:
            print('Failed to submit answer to server')

    def handle(self, event):
        print(f'Server says: {event.event_type}')

    def start_app_process(self):
        app = ClientApp(self)

        def app_target():
            if SUPPRESS_FLASK_LOGGING:
                import click
                import logging
                log = logging.getLogger('werkzeug')
                log.disabled = True
                setattr(click, 'echo', lambda *a, **k: None)
                setattr(click, 'secho', lambda *a, **k: None)
            app.run(host='0.0.0.0', port=self.port)

        app_process = Process(target=app_target)
        app_process.start()
        print(f'Client app running on port {self.port}')
        return app_process

    def close(self):
        try:
            self.goodbye()  # tell the server we are going away
        finally:
            self.app_process.terminate()
            self.app_process.join()
            self.app_process.close()
            print('Client app stopped')


class ClientApp(Flask):

    def __init__(self, client, *args, **kwargs):
        super().__init__(f'jeopardy-client-{client.client_id}', *args, **kwargs)
        self.client = client
        self.route('/')(self.root)
        self.route('/id')(self.id)
        self.route('/notify', methods=['POST'])(self.notify)

    @to_json
    def id(self):
        return ClientIDResponse(self.client.client_id)

    def notify(self):
        try:
            event = Event.from_request(request)
        except (TypeError, ValueError):
            return error('Failed to parse event')
        self.client.handle(event)
        return no_content()

    @staticmethod
    def root():
        return no_content()
