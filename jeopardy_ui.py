import os
import random
import subprocess
import tkinter as tk
import uuid

from collections import namedtuple
from tkinter import font
from multiprocessing import Process, Queue

from jeopardy_cli import ClientApp
from jeopardy_client import JeopardyClient
from jeopardy_model import PlayerInfo, Question


SUPPRESS_FLASK_LOGGING = True


TaggedText = namedtuple('TaggedText', ['text', 'tags'])


class JeopardyApp(tk.Frame):

    DEFAULT_TICK_DELAY_MILLIS = 100
    HOST = 'Host'
    JEOPARDY_BLUE = '#060CE9'
    JEOPARDY_LIGHT_BLUE = '#115FF4'
    JEOPARDY_VIOLET = '#8D2AB5'

    def __init__(self, master=None, server_address=None, nick=None):
        if master is None:
            master = tk.Tk()
            master.title('Jeopardy!')
        super().__init__(master)
        master.protocol('WM_DELETE_WINDOW', self.close)

        if nick is None:
            nick = os.getenv('JEOPARDY_CLIENT_NICKNAME')
        self.player_id = str(uuid.uuid4())
        self.players = {}
        self.nick = nick or self.player_id
        self.client = JeopardyClient(server_address, self.player_id)
        self.current_question_id = None
        self.port = random.randrange(65000, 65536)
        self.app_process = None
        self.event_queue = Queue(maxsize=100)
        self.stats_queue = Queue(maxsize=100)

        self.stats_pane = None
        self.event_pane = None
        self.pack()
        self.default_font = font.Font(self, 'Courier')
        self.main_pane = self.create_main_pane()
        self.input_text = tk.StringVar(value='')
        self.input_pane = self.create_input_pane()

    def create_main_pane(self):
        main_pane = tk.Frame(self, height=50, width=120)
        main_pane.pack(side='top')
        self.stats_pane = self.create_stats_pane(main_pane)
        self.update_stats()
        self.event_pane = self.create_event_pane(main_pane)
        return main_pane

    def create_stats_pane(self, parent):
        pane = tk.Text(parent, height=50, width=20, font=self.default_font, relief=tk.GROOVE, borderwidth=3, state=tk.DISABLED, takefocus=0, undo=False)
        pane.pack(side='left')
        return pane

    def create_event_pane(self, parent):
        pane = tk.Text(parent, height=50, width=80, font=self.default_font, wrap=tk.WORD, state=tk.DISABLED, takefocus=0, undo=False)
        bold_font = font.Font(pane, 'Courier')
        bold_font.configure(weight='bold')
        pane.tag_configure('bold', font=bold_font)
        small_font = font.Font(pane, 'Courier')
        small_font.configure(size=4)
        pane.tag_configure('small', font=small_font)
        pane.tag_configure('question_category', background=self.JEOPARDY_BLUE, foreground='white', justify=tk.CENTER, spacing1=3, spacing3=3)
        pane.tag_configure('question_value', background=self.JEOPARDY_LIGHT_BLUE, foreground='white', justify=tk.CENTER, spacing1=3, spacing3=3)
        pane.tag_configure('question_text', justify=tk.CENTER, spacing1=3, spacing3=3)
        tiny_font = font.Font(pane, 'Courier')
        tiny_font.configure(size=2)
        pane.tag_configure('line', background='black', font=tiny_font)
        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, borderwidth=1, command=pane.yview)
        scrollbar.pack(side='right', fill='y', expand=False)
        pane.configure(yscrollcommand=scrollbar.set)
        pane.pack(side='right')
        return pane

    def create_input_pane(self):
        pane = tk.Entry(self, width=80, textvariable=self.input_text)
        pane.bind('<KeyPress-Return>', self.handle_user_input)
        pane.pack(side='bottom')
        return pane

    def fetch_stats(self):
        resp = self.client.get('/')
        if resp.ok:
            resp_json = resp.json()
            if resp_json:
                self.players = {
                    player_id: PlayerInfo.from_json(player)
                    for player_id, player in resp_json['players'].items()
                }
            else:
                print('Invalid response from server')
        else:
            print('Failed to fetch stats')

    def update_stats(self):
        def format_nick(player):
            prefix = '*' if player.player_id == self.player_id else ' '
            return f'{prefix} {player.nick}'

        sorted_players = sorted(self.players.values(), key=lambda p: p.score, reverse=True)
        player_stats = [
            f'{format_nick(player)}\t{self.format_score(player.score)}'
            for player in sorted_players
        ]
        self.stats_pane.configure(state=tk.NORMAL)
        self.stats_pane.delete('1.0', tk.END)
        self.stats_pane.insert('1.0', '\n'.join(player_stats))
        self.stats_pane.configure(state=tk.DISABLED)

    def register(self):
        external_ip = subprocess.getoutput(r'ifconfig | grep -A3 en0 | grep -E "inet\b" | cut -d" " -f2')
        if not external_ip:
            raise RuntimeError('Failed to find external IP')
        self.client.register(f'{external_ip}:{self.port}', self.nick)

    def show_event(self, event_parts):
        self.event_queue.put_nowait(event_parts)

    def show_stats_update(self, event):
        self.stats_queue.put_nowait(event)

    def append_to_event_pane(self, event_parts):
        self.event_pane.configure(state=tk.NORMAL)
        for event_part in event_parts:
            if isinstance(event_part, TaggedText):
                text, tags = event_part
                if isinstance(tags, str):
                    tags = (tags,)
                self.event_pane.insert(tk.END, text, tags)
            else:
                self.event_pane.insert(tk.END, event_part)
        self.event_pane.insert(tk.END, '\n')
        self.event_pane.insert(tk.END, '\n', ('small',))
        self.event_pane.configure(state=tk.DISABLED)
        self.event_pane.see(tk.END)

    def player_says(self, player, message_parts):
        if isinstance(message_parts, str):
            message_parts = [message_parts]
        self.show_event([
            TaggedText(f'{player}: ', 'bold'),
            *message_parts
        ])

    def host_says(self, message):
        self.player_says(self.HOST, message)

    @staticmethod
    def format_score(score):
        return f'${score:,}'

    def show_question(self, question):
        self.show_event([
            '\n',
            TaggedText('\n', 'line'),
            TaggedText(question.category + '\n', 'question_category'),
            TaggedText(self.format_score(question.value) + '\n', 'question_value'),
            TaggedText(question.text + '\n', 'question_text'),
            TaggedText('\n', 'line'),
        ])

    def handle_user_input(self, event):
        user_input = self.input_text.get()
        if not user_input:
            return
        if user_input == '/h':
            self.append_to_event_pane('Type "/q" to get a new question. Enter your answer to check if it is correct.')
        elif user_input == '/q':
            question = self.client.get_question()
            if question.question_id != self.current_question_id:
                self.current_question_id = question.question_id
                self.show_question(question)
        elif user_input.startswith('/c '):
            message = user_input[3:]
            self.client.chat(message)
            self.player_says(self.nick, message)
        else:
            player = self.players[self.player_id]
            player.total_answers += 1
            self.player_says(self.nick, f'What is {user_input}?')
            resp = self.client.answer(user_input)
            if resp is not None and resp.is_correct:
                host_response = f'{self.nick}, that is correct.'
                player.correct_answers += 1
                player.score += resp.value
            else:
                host_response = f'No, sorry, {self.nick}.'
            self.host_says(host_response)
        self.input_text.set('')

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
            self.show_stats_update(event)
        elif event.event_type in {'NEW_PLAYER', 'PLAYER_LEFT'}:
            nick = event.player.nick
            verb = 'joined' if event.event_type == 'NEW_PLAYER' else 'left'
            self.host_says(f'{nick} has {verb} the game.')
            self.show_stats_update(event)
        elif event.event_type == 'QUESTION_TIMEOUT':
            self.host_says(f'The correct answer is: {event.payload["answer"]}')
        elif event.event_type == 'CHAT_MESSAGE':
            nick = event.player.nick
            self.player_says(nick, event.payload['message'])
        else:
            print(f'[!!] Received unexpected event: {event}')

    def tick(self):
        while not self.event_queue.empty():
            event = self.event_queue.get_nowait()
            self.append_to_event_pane(event)

        while not self.stats_queue.empty():
            event = self.stats_queue.get_nowait()
            if event.event_type in {'NEW_ANSWER', 'NEW_PLAYER'}:
                self.players[event.player.player_id] = event.player
            elif event.event_type == 'PLAYER_LEFT':
                del self.players[event.player.player_id]

        self.update_stats()
        self.update()
        self.after(self.DEFAULT_TICK_DELAY_MILLIS, self.tick)

    def run(self):
        self.app_process = self.start_app_process()
        self.register()
        self.client.start_game()
        self.fetch_stats()
        self.tick()
        super().mainloop()

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
            self.master.destroy()


if __name__ == '__main__':
    app = JeopardyApp()
    app.run()
