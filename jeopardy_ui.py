import os
import random
import subprocess
import tkinter as tk
import uuid

from collections import namedtuple
from tkinter import font
from tkinter import ttk
from multiprocessing import Process, Queue
from threading import RLock

from jeopardy_cli import ClientApp
from jeopardy_client import JeopardyClient
from jeopardy_model import PlayerInfo, Question


SUPPRESS_FLASK_LOGGING = True


TaggedText = namedtuple('TaggedText', ['text', 'tags'])


class JeopardyApp(ttk.Frame):

    DEFAULT_TICK_DELAY_MILLIS = 100
    FONT_FAMILY = 'Consolas'  # was Courier
    HOST = 'Host'

    DARK_GRAY = '#333333'
    LIGHT_GRAY = '#CCCCCC'
    JEOPARDY_BLUE = '#060CE9'
    JEOPARDY_GOLD = '#CC8E3C'
    JEOPARDY_LIGHT_BLUE = '#115FF4'
    JEOPARDY_VIOLET = '#8D2AB5'

    WELCOME_TEXT = (
        'Use the text box at the bottom to enter commands and answers. '
        'To fetch a new question, enter "/q" (or just press Enter). '
        'To send a chat message, enter "/c" followed by your message. '
        'To answer a question, simply enter your answer in the text box.\n'
    )

    def __init__(self, master=None, server_address=None, nick=None, dark_mode=False):
        if master is None:
            master = tk.Tk()
            master.minsize(width=400, height=300)
            master.title('Jeopardy!')
        super().__init__(master)
        master.protocol('WM_DELETE_WINDOW', self.close)

        if nick is None:
            nick = os.getenv('JEOPARDY_CLIENT_NICKNAME')
        self.player_id = str(uuid.uuid4())
        self.nick = nick or self.player_id
        self.players = {}
        self.client = JeopardyClient(server_address, self.player_id)
        self.current_question_id = None
        self.lock = RLock()
        self.port = random.randrange(65000, 65536)
        self.app_process = None
        self.event_queue = Queue(maxsize=100)
        self.stats_queue = Queue(maxsize=100)
        self.question_timeout_queue = Queue(maxsize=1)

        # enable resizing
        top = self.winfo_toplevel()
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.stats_pane = None
        self.event_pane = None
        self.grid(sticky=tk.N + tk.S + tk.E + tk.W)
        self.dark_mode = dark_mode
        self.configure_style()
        self.default_font = font.Font(self, family=self.FONT_FAMILY, size=14)
        self.bold_font = font.Font(self, family=self.FONT_FAMILY, size=14, weight='bold')
        self.main_pane = self.create_main_pane()
        self.input_text = tk.StringVar(value='')
        self.input_pane = self.create_input_pane()

    def configure_style(self):
        style = ttk.Style()
        style.configure('TEntry', borderwidth=0, highlightthickness=0)
        style.configure('TScrollbar', borderwidth=0)
        style.configure('Line.TFrame', background='black', foreground='black')
        if self.dark_mode:
            style.configure('Main.TFrame', background=self.DARK_GRAY, borderwidth=0, highlightthickness=0)
        else:
            style.configure('Main.TFrame', borderwidth=0, highlightthickness=0)

    def create_main_pane(self):
        main_pane = ttk.Frame(self, height=600, width=600, style='Main.TFrame')
        main_pane.grid(row=0, column=0, sticky=tk.N + tk.S + tk.E + tk.W)
        self.stats_pane = self.create_stats_pane(main_pane)
        self.update_stats()
        vertical_line = ttk.Frame(main_pane, height=600, width=5, style='Line.TFrame')
        vertical_line.grid(row=0, column=1)
        self.event_pane = self.create_event_pane(main_pane)
        main_pane.rowconfigure(0, weight=1)
        main_pane.columnconfigure(2, weight=1)
        return main_pane

    def create_stats_pane(self, parent):
        pane = tk.Text(parent, height=50, width=20, font=self.default_font, background=self.LIGHT_GRAY, borderwidth=0, highlightthickness=0, state=tk.DISABLED, takefocus=0, undo=False)
        pane.tag_configure('heading', font=(self.FONT_FAMILY, 16, 'bold'), background=self.JEOPARDY_BLUE, foreground='white', justify=tk.CENTER, spacing1=6, spacing3=6)
        pane.tag_configure('bold', font=self.bold_font, justify=tk.CENTER)
        pane.tag_configure('centered', justify=tk.CENTER)
        pane.grid(row=0, column=0, sticky=tk.N + tk.S)
        return pane

    def create_event_pane(self, parent):
        if self.dark_mode:
            background = self.DARK_GRAY
            foreground = 'white'
        else:
            background = 'white'
            foreground = 'black'
        pane = tk.Text(parent, height=50, width=80, font=self.default_font, background=background, foreground=foreground, borderwidth=0, highlightthickness=0, wrap=tk.WORD, state=tk.DISABLED, takefocus=0, undo=False)
        pane.tag_configure('bold', font=self.bold_font)
        small_font = font.Font(pane, self.FONT_FAMILY)
        small_font.configure(size=4)
        pane.tag_configure('small', font=small_font)
        pane.tag_configure('welcome_title', background=self.JEOPARDY_VIOLET, foreground='white', font=(self.FONT_FAMILY, 24, 'bold'), justify=tk.CENTER, lmargin1=10, rmargin=10, spacing1=10, spacing3=5)
        pane.tag_configure('welcome_text', background=self.JEOPARDY_VIOLET, foreground='white', justify=tk.CENTER, lmargin1=10, lmargin2=10, rmargin=10, spacing1=5, spacing3=10)
        pane.tag_configure('question_category', background=self.JEOPARDY_BLUE, font=(self.FONT_FAMILY, 16, 'bold'), foreground='white', justify=tk.CENTER, spacing1=3, spacing3=3)
        pane.tag_configure('question_value', background=self.JEOPARDY_LIGHT_BLUE, foreground='white', font=(self.FONT_FAMILY, 16), justify=tk.CENTER, spacing1=3, spacing3=3)
        pane.tag_configure('question_text', background='white', foreground='black', justify=tk.CENTER, lmargin1=5, lmargin2=5, rmargin=5, spacing1=3, spacing3=3)
        tiny_font = font.Font(pane, self.FONT_FAMILY)
        tiny_font.configure(size=2)
        pane.tag_configure('line', background='black', font=tiny_font)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=pane.yview)
        pane.configure(yscrollcommand=scrollbar.set)
        pane.grid(row=0, column=2, sticky=tk.N + tk.S + tk.E + tk.W)
        scrollbar.grid(row=0, column=3, sticky=tk.N + tk.S)
        return pane

    def create_input_pane(self):
        pane = ttk.Entry(self, width=80, style='TEntry', textvariable=self.input_text)
        pane.bind('<KeyPress-Return>', self.handle_user_input)
        pane.grid(row=1, column=0, sticky=tk.E + tk.W)
        return pane

    def is_current_question(self, question_id):
        return self.current_question_id is not None and self.current_question_id == question_id

    def update_current_question(self, question_id):
        with self.lock:
            self.current_question_id = question_id

    def maybe_update_and_show_question(self, question):
        with self.lock:
            if not self.is_current_question(question.question_id):
                self.update_current_question(question.question_id)
                self.show_question(question)

    @property
    def longest_player_nick(self):
        if not self.players:
            return 0
        longest_nick_player = max(self.players.values(), key=lambda p: len(p.nick))
        return len(longest_nick_player.nick)

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
        sorted_players = sorted(self.players.values(), key=lambda p: p.score, reverse=True)
        align = self.longest_player_nick + 2
        self.stats_pane.configure(state=tk.NORMAL)
        self.stats_pane.delete('1.0', tk.END)
        self.stats_pane.insert('1.0', 'Players\n', ('heading',))
        self.stats_pane.insert(tk.END, '\n')
        for player in sorted_players:
            player_stats = f'{player.nick:{align}}{self.format_score(player.score)}\n'
            if player.player_id == self.player_id:
                self.stats_pane.insert(tk.END, player_stats, ('bold',))
            else:
                self.stats_pane.insert(tk.END, player_stats, ('centered',))
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
            TaggedText(question.category.upper() + '\n', 'question_category'),
            TaggedText(self.format_score(question.value) + '\n', 'question_value'),
            TaggedText(question.text + '\n', 'question_text'),
            TaggedText('\n', 'line'),
        ])

    def handle_user_input(self, event):
        user_input = self.input_text.get()
        if not user_input:
            user_input = '/q'
        if user_input == '/h':
            self.append_to_event_pane('Type "/q" to get a new question. Enter your answer to check if it is correct.')
        elif user_input == '/q':
            question = self.client.get_question()
            self.maybe_update_and_show_question(question)
        elif user_input.startswith('/c '):
            message = user_input[3:]
            self.client.chat(message)
            self.player_says(self.nick, message)
        else:
            if self.current_question_id is None:
                self.host_says(f'{self.nick}, there is currently no active question.')
            else:
                player = self.players[self.player_id]
                player.total_answers += 1
                self.player_says(self.nick, f'What is {user_input}?')
                resp = self.client.answer(user_input)
                if resp is not None and resp.is_correct:
                    host_response = f'{self.nick}, that is correct.'
                    player.correct_answers += 1
                    player.score += resp.value
                    self.update_current_question(None)
                elif resp is not None and resp.is_close:
                    host_response = f'{self.nick}, can you be more specific?'
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
            self.maybe_update_and_show_question(question)
        elif event.event_type == 'NEW_ANSWER':
            nick = event.player.nick
            answer = event.payload['answer']
            if event.payload['is_correct']:
                host_response = f'{nick}, that is correct.'
                self.question_timeout_queue.put(None)
            elif event.payload['is_close']:
                host_response = f'{nick}, can you be more specific?'
            else:
                host_response = f'No, sorry, {nick}.'
            self.player_says(nick, f'What is {answer}?')
            self.host_says(host_response)
            self.show_stats_update(event)
        elif event.event_type in {'NEW_PLAYER', 'PLAYER_LEFT'}:
            nick = event.player.nick
            verb = 'joined' if event.event_type == 'NEW_PLAYER' else 'left'
            self.host_says(f'{nick} has {verb} the game.')
            self.show_stats_update(event)
        elif event.event_type == 'QUESTION_TIMEOUT':
            self.question_timeout_queue.put(None)
            self.host_says(f'The correct answer is: {event.payload["answer"]}')
        elif event.event_type == 'CHAT_MESSAGE':
            nick = event.player.nick
            self.player_says(nick, event.payload['message'])
        else:
            print(f'[!!] Received unexpected event: {event}')

    def tick(self):
        if not self.question_timeout_queue.empty():
            _ = self.question_timeout_queue.get_nowait()
            self.update_current_question(None)

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
        self.show_event([
            TaggedText('Welcome to Jeopardy!\n', 'welcome_title'),
            TaggedText(self.WELCOME_TEXT, 'welcome_text'),
        ])
        self.tick()
        self.input_pane.focus_set()

        with self.lock:
            if self.current_question_id is None:
                question = self.client.get_question()
                self.maybe_update_and_show_question(question)

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
