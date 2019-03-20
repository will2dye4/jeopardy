#!/usr/bin/env python3.7

import json
import sys


def migrate_file(path):
    with open(path) as f:
        players = json.load(f)

    game = {
        'statistics': {
            'questions_asked': 0,
            'questions_answered': 0,
            'total_answers': 0,
            'total_correct_answers': 0,
        },
        'players': players,
    }

    with open(path, 'w') as f:
        json.dump(game, f)

    print('Done!')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} <path_to_game_file>')
        sys.exit(1)
    migrate_file(sys.argv[1])
