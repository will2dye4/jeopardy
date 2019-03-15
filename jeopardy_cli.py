import os
import random
import subprocess
import traceback
import uuid

from multiprocessing import Process

from flask import Flask, request

from colorize import bold, green
from flask_utils import error, no_content
from jeopardy_client import JeopardyClient
from jeopardy_model import Event, PlayerInfo, Question


SUPPRESS_FLASK_LOGGING = True


class JeopardyCLI:

    HOST = 'Host'

    def __init__(self, server_address=None, nick=None):
        if nick is None:
            nick = os.getenv('JEOPARDY_CLIENT_NICKNAME')
        self.player_id = str(uuid.uuid4())
        self.nick = nick or self.player_id
        self.client = JeopardyClient(server_address, self.player_id)
        self.current_question_id = None
        self.port = random.randrange(65000, 65536)
        self.app_process = self.start_app_process()
        self.register()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def player_says(player, message):
        print(f'{bold(player + ":")} {message}')

    @classmethod
    def host_says(cls, message):
        cls.player_says(cls.HOST, message)

    @classmethod
    def show_question(cls, question):
        cls.host_says(f'In {bold(question.category)} for {green("$" + str(question.value))}:\n      {question.text}')

    def show_stats(self):
        resp = self.client.get('/')
        if resp.ok:
            resp_json = resp.json()
            if not resp_json:
                print('Invalid response from server')
            for player_info in resp_json['players'].values():
                player = PlayerInfo.from_json(player_info)
                print(f'{player.nick}\t${player.score}\t({player.correct_answers}/{player.total_answers})')
        else:
            print('Failed to fetch stats')

    def register(self):
        external_ip = subprocess.getoutput(r'ifconfig | grep -A3 en0 | grep -E "inet\b" | cut -d" " -f2')
        if not external_ip:
            raise RuntimeError('Failed to find external IP')
        self.client.register(f'{external_ip}:{self.port}', self.nick)

    def play(self):
        self.client.start_game()
        try:
            while True:
                user_input = input().strip()
                if user_input == '/h':
                    print('Type "/q" to get a new question. Enter your answer to check if it is correct.')
                elif user_input == '/q':
                    question = self.client.get_question()
                    if question.question_id != self.current_question_id:
                        self.current_question_id = question.question_id
                        self.show_question(question)
                elif user_input == '/s':
                    self.show_stats()
                elif user_input.startswith('/c '):
                    self.client.chat(user_input[3:])
                else:
                    resp = self.client.answer(user_input)
                    self.host_says('Correct!' if resp.is_correct else 'Wrong.')
        except EOFError:
            print()
            self.host_says('Goodbye!')

    def handle(self, event):
        if event.player is not None and event.player.player_id == self.player_id:
            return  # don't respond to our own events
        if event.event_type == 'NEW_GAME':
            self.host_says('A new game is starting!')
        elif event.event_type == 'NEW_QUESTION':
            question = Question.from_json(event.payload)
            if question.question_id != self.current_question_id:
                self.current_question_id = question.question_id
                self.show_question(question)
        elif event.event_type == 'NEW_ANSWER':
            nick = event.player.nick
            answer = event.payload['answer']
            correct = event.payload['is_correct']
            self.player_says(nick, f'What is {answer}?')
            host_response = f'{nick}, that is correct.' if correct else f'No, sorry, {nick}.'
            self.host_says(host_response)
        elif event.event_type in {'NEW_PLAYER', 'PLAYER_LEFT'}:
            nick = event.player.nick
            verb = 'joined' if event.event_type == 'NEW_PLAYER' else 'left'
            self.host_says(f'{nick} has {verb} the game.')
        elif event.event_type == 'QUESTION_TIMEOUT':
            self.host_says(f'The correct answer is: {event.payload["answer"]}')
        elif event.event_type == 'CHAT_MESSAGE':
            nick = event.player.nick
            self.player_says(nick, event.payload['message'])
        else:
            print(f'[!!] Received unexpected event: {event}')

    def start_app_process(self):
        app = ClientApp(self.player_id, self)

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
            self.client.close()
        finally:
            if self.app_process is not None:
                self.app_process.terminate()
                self.app_process.join()
                self.app_process.close()
                print('Client app stopped')


class ClientApp(Flask):

    def __init__(self, player_id, event_handler, *args, **kwargs):
        super().__init__(f'jeopardy-client-{player_id}', *args, **kwargs)
        self.player_id = player_id
        self.event_handler = event_handler
        self.route('/')(self.root)
        self.route('/id')(self.id)
        self.route('/notify', methods=['POST'])(self.notify)

    def id(self):
        return self.player_id

    def notify(self):
        try:
            event = Event.from_request(request)
        except (TypeError, ValueError) as e:
            return error(f'Failed to parse event: {e}')
        try:
            self.event_handler.handle(event)
        except Exception:
            print('Caught exception handling event')
            print('Event:', str(event))
            traceback.print_exc()
        return no_content()

    @staticmethod
    def root():
        return no_content()


if __name__ == '__main__':
    with JeopardyCLI() as cli:
        cli.play()
