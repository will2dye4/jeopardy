from jeopardy_client import JeopardyClient
from jeopardy_model import ClientInfo, Question


class JeopardyCLI:

    def __init__(self, server_address=None, nick=None):
        self.client = JeopardyClient(server_address, nick)
        self.current_question_id = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def show_question(question):
        print(f'Category: {question.category}')
        print(f'Value: ${question.value}')
        print(f'Question: {question.text}')

    def show_stats(self):
        resp = self.client.get('/')
        if resp.ok:
            resp_json = resp.json()
            if not resp_json:
                print('Invalid response from server')
            for client_info in resp_json['clients'].values():
                client = ClientInfo(**client_info)
                print(f'{client.nick}\t${client.score}\t({client.correct_answers}/{client.total_answers})')
        else:
            print('Failed to fetch stats')

    def play(self):
        self.client.start_app_process(self)
        self.client.register()
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
                else:
                    is_correct = self.client.answer(user_input)
                    if is_correct:
                        print('Correct!')
                    else:
                        print('Wrong.')
        except EOFError:
            print()

    def handle(self, event):
        if event.event_type == 'NEW_GAME':
            print('A new game is starting!')
        elif event.event_type == 'NEW_QUESTION':
            question = Question(**event.payload)
            if question.question_id != self.current_question_id:
                self.current_question_id = question.question_id
                self.show_question(question)
        elif event.event_type == 'NEW_ANSWER':
            client_id = event.payload['client']['client_id']
            if client_id != self.client.client_id:
                nick = event.payload['client']['nick']
                answer = event.payload['answer']
                correct = event.payload['is_correct']
                adverb = 'correctly' if correct else 'incorrectly'
                print(f'{nick} {adverb} guessed: {answer}')
        elif event.event_type in {'NEW_PLAYER', 'PLAYER_LEFT'}:
            client_id = event.payload['client_id']
            if client_id != self.client.client_id:
                nick = event.payload['nick']
                verb = 'joined' if event.event_type == 'NEW_PLAYER' else 'left'
                print(f'{nick} has {verb} the game')
        elif event.event_type == 'QUESTION_TIMEOUT':
            print(f'The correct answer is: {event.payload["answer"]}')
        else:
            print(f'Server says: {event.event_type}')

    def close(self):
        self.client.close()


if __name__ == '__main__':
    with JeopardyCLI() as cli:
        cli.play()
