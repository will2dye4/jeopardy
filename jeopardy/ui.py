import random
import tkinter as tk
import uuid

from collections import namedtuple
from tkinter import font
from tkinter import ttk
from multiprocessing import Process, Queue
from threading import RLock

import requests

from jeopardy.cli import ClientApp
from jeopardy.client import JeopardyClient
from jeopardy.model import NickUpdate, PlayerInfo, Question


SUPPRESS_FLASK_LOGGING = True


TaggedText = namedtuple('TaggedText', ['text', 'tags'])


class JeopardyApp(ttk.Frame):

    DEFAULT_TICK_DELAY_MILLIS = 100
    FONT_FAMILY = 'Consolas'  # was Courier
    HOST = 'Host'

    DARK_GRAY = '#333333'
    LIGHT_GRAY = '#CCCCCC'
    MEDIUM_GRAY = '#888888'
    MEDIUM_DARK_GRAY = '#555555'
    MEDIUM_LIGHT_GRAY = '#AAAAAA'
    JEOPARDY_BLUE = '#060CE9'
    JEOPARDY_GOLD = '#CC8E3C'
    JEOPARDY_LIGHT_BLUE = '#115FF4'
    JEOPARDY_VIOLET = '#8D2AB5'

    WELCOME_TEXT = (
        'Use the text box at the bottom to enter commands and answers. '
        'To fetch a new question, enter "/q" (or just press Enter). '
        'To send a chat message, enter "/c" followed by your message. '
        'To change your nickname, enter "/n " followed by the new nickname. '
        'To answer a question, simply enter your answer in the text box.\n'
    )

    def __init__(self, master=None, server_address=None, client_port=None, player_id=None, nick=None, dark_mode=False):
        if master is None:
            master = tk.Tk()
            master.minsize(width=400, height=300)
            master.title('Jeopardy!')
        super().__init__(master)
        master.protocol('WM_DELETE_WINDOW', self.close)

        self.player_id = player_id or str(uuid.uuid4())
        self.nick = nick or self.player_id
        self.server_address = server_address
        self.client_port = client_port or random.randrange(65000, 65536)
        self.client = JeopardyClient(self.server_address, self.player_id)
        self.players = {}
        self.current_question_id = None
        self.lock = RLock()

        self.app_process = None
        self.event_queue = Queue(maxsize=100)
        self.stats_queue = Queue(maxsize=100)
        self.question_queue = Queue(maxsize=1)

        # enable resizing
        top = self.winfo_toplevel()
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dark_mode = dark_mode
        if self.dark_mode:
            self.default_background = self.DARK_GRAY
            self.default_foreground = 'white'
        else:
            self.default_background = 'white'
            self.default_foreground = 'black'

        self.stats_pane = None
        self.event_pane = None
        self.grid(sticky=tk.N + tk.S + tk.E + tk.W)
        self.configure_style()
        self.default_font = font.Font(self, family=self.FONT_FAMILY, size=14)
        self.bold_font = font.Font(self, family=self.FONT_FAMILY, size=14, weight='bold')
        self.italic_font = font.Font(self, family=self.FONT_FAMILY, size=14, slant='italic')
        self.main_pane = self.create_main_pane()
        self.configure_tags()
        self.input_text = tk.StringVar(value='')
        self.input_pane = self.create_input_pane()

    def configure_style(self):
        style = ttk.Style()
        style.configure('TScrollbar', borderwidth=0)
        style.configure('Line.TFrame', background='black', foreground='black')

        if self.dark_mode:
            input_background = self.MEDIUM_DARK_GRAY
        else:
            input_background = self.default_background

        style.configure('TEntry', background=input_background, foreground=self.default_foreground,
                        borderwidth=0, highlightthickness=0)

    def configure_tags(self):
        if self.dark_mode:
            inactive_player_foreground = self.LIGHT_GRAY
        else:
            inactive_player_foreground = self.MEDIUM_GRAY

        for pane in (self.stats_pane, self.event_pane):
            # general tags
            pane.tag_configure('bold', font=self.bold_font)
            pane.tag_configure('centered', justify=tk.CENTER)
            pane.tag_configure('small', font=(self.FONT_FAMILY, 4))
            pane.tag_configure('line', background=self.default_foreground, font=(self.FONT_FAMILY, 2))

            # tags for specific panes
            pane.tag_configure('players_heading', font=(self.FONT_FAMILY, 16, 'bold'), background=self.JEOPARDY_BLUE,
                               foreground='white', justify=tk.CENTER, spacing1=6, spacing3=6)
            pane.tag_configure('players_inactive', font=self.italic_font, foreground=inactive_player_foreground)
            pane.tag_configure('welcome_title', background=self.JEOPARDY_VIOLET, foreground='white',
                               font=(self.FONT_FAMILY, 24, 'bold'), justify=tk.CENTER, lmargin1=10, rmargin=10,
                               spacing1=10, spacing3=5)
            pane.tag_configure('welcome_text', background=self.JEOPARDY_VIOLET, foreground='white', justify=tk.CENTER,
                               lmargin1=10, lmargin2=10, rmargin=10, spacing1=5, spacing3=10)
            pane.tag_configure('question_category', background=self.JEOPARDY_BLUE, font=(self.FONT_FAMILY, 16, 'bold'),
                               foreground='white', justify=tk.CENTER, spacing1=3, spacing3=3)
            pane.tag_configure('question_value', background=self.JEOPARDY_LIGHT_BLUE, foreground='white',
                               font=(self.FONT_FAMILY, 16), justify=tk.CENTER, spacing1=3, spacing3=3)
            pane.tag_configure('question_text', background=self.default_background, foreground=self.default_foreground,
                               justify=tk.CENTER, lmargin1=5, lmargin2=5, rmargin=5, spacing1=3, spacing3=3)

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
        background = self.MEDIUM_GRAY if self.dark_mode else self.LIGHT_GRAY
        pane = tk.Text(parent, height=50, width=20, font=self.default_font, background=background,
                       foreground=self.default_foreground, borderwidth=0, highlightthickness=0, state=tk.DISABLED,
                       takefocus=0, undo=False)
        pane.grid(row=0, column=0, sticky=tk.N + tk.S)
        return pane

    def create_event_pane(self, parent):
        pane = tk.Text(parent, height=50, width=80, font=self.default_font, background=self.default_background,
                       foreground=self.default_foreground, borderwidth=0, highlightthickness=0, wrap=tk.WORD,
                       state=tk.DISABLED, takefocus=0, undo=False)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=pane.yview)
        pane.configure(yscrollcommand=scrollbar.set)
        pane.grid(row=0, column=2, sticky=tk.N + tk.S + tk.E + tk.W)
        scrollbar.grid(row=0, column=3, sticky=tk.N + tk.S)
        return pane

    def create_input_pane(self):
        pane = ttk.Entry(self, width=80, font=self.default_font, style='TEntry', textvariable=self.input_text)
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
        def get_stats(player, alignment):
            return f'{player.nick:{len(player.nick) + alignment}}{self.format_score(player.score)}\n'

        if not self.players:
            return

        stats = {
            player_id: f'{player.nick}{self.format_score(player.score)}'
            for player_id, player in self.players.items()
        }
        longest_stats_len = max(len(s) for s in stats.values())

        active_players = [player for player in self.players.values() if player.is_active]
        inactive_players = [player for player in self.players.values() if not player.is_active]
        sorted_active_players = sorted(active_players, key=lambda p: p.score, reverse=True)
        sorted_inactive_players = sorted(inactive_players, key=lambda p: p.score, reverse=True)
        self.stats_pane.configure(state=tk.NORMAL)
        self.stats_pane.delete('1.0', tk.END)
        self.stats_pane.insert('1.0', 'Players\n', ('players_heading',))
        self.stats_pane.insert(tk.END, '\n')

        for player in sorted_active_players:
            align = (longest_stats_len - len(stats[player.player_id])) + 2
            player_stats = get_stats(player, align)
            if player.player_id == self.player_id:
                self.stats_pane.insert(tk.END, player_stats, ('bold', 'centered'))
            else:
                self.stats_pane.insert(tk.END, player_stats, ('centered',))

        for player in sorted_inactive_players:
            align = (longest_stats_len - len(stats[player.player_id])) + 2
            self.stats_pane.insert(tk.END, get_stats(player, align), ('players_inactive', 'centered'))

        self.stats_pane.configure(state=tk.DISABLED)

    def register(self):
        if 'localhost' in self.server_address or '127.0.0.1' in self.server_address:
            client_address = 'localhost'  # shortcut for running locally
        else:
            resp = requests.get('https://api.ipify.org')
            if not resp.ok:
                raise RuntimeError(f'Failed to find external IP: {resp.text}')
            client_address = resp.text
        self.client.register(f'{client_address}:{self.client_port}', self.nick)

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
        elif user_input.startswith('/n '):
            new_nick = user_input[3:]
            if new_nick != self.nick:
                if self.client.change_nick(new_nick):
                    self.nick = new_nick
                    self.players[self.player_id].nick = new_nick
                    self.host_says(f'You are now known as {new_nick}.')
                else:
                    self.host_says(f"Sorry, {self.nick}, I wasn't able to do that.")
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
            self.question_queue.put_nowait(question)
        elif event.event_type == 'NEW_ANSWER':
            nick = event.player.nick
            answer = event.payload['answer']
            if event.payload['is_correct']:
                host_response = f'{nick}, that is correct.'
                self.question_queue.put_nowait(None)
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
            self.question_queue.put_nowait(None)
            self.host_says(f'The correct answer is: {event.payload["answer"]}')
        elif event.event_type == 'CHAT_MESSAGE':
            nick = event.player.nick
            self.player_says(nick, event.payload['message'])
        elif event.event_type == 'NICK_CHANGED':
            update = NickUpdate.from_json(event.payload)
            self.host_says(f'{update.old_nick} is now known as {update.new_nick}')
            self.show_stats_update(event)
        else:
            print(f'[!!] Received unexpected event: {event}')

    def tick(self):
        if not self.question_queue.empty():
            question = self.question_queue.get_nowait()
            if question is None:
                self.update_current_question(None)
            else:
                self.maybe_update_and_show_question(question)

        while not self.event_queue.empty():
            event = self.event_queue.get_nowait()
            self.append_to_event_pane(event)

        while not self.stats_queue.empty():
            event = self.stats_queue.get_nowait()
            self.players[event.player.player_id] = event.player

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
            app.run(host='0.0.0.0', port=self.client_port)

        app_process = Process(target=app_target)
        app_process.start()
        print(f'Client app running on port {self.client_port}')
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
