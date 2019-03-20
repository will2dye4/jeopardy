import argparse
import json
import os
import sys
import uuid

from typing import Any, List

from jeopardy.model import ClientConfig
from jeopardy.ui import JeopardyApp


class JeopardyMain:

    DEFAULT_CONFIG_FILEPATH = os.path.expanduser('~/.jeopardy/config.json')

    def __init__(self, args: List[str] = None) -> None:
        if args is None:
            args = sys.argv[1:]
        parsed_args = self.parse_args(args)
        self._nick = parsed_args.nick
        self._server_address = parsed_args.server_address
        self._dark_mode = parsed_args.dark_mode or None
        self._player_id = None
        self.app = None

        if os.path.exists(self.DEFAULT_CONFIG_FILEPATH):
            with open(self.DEFAULT_CONFIG_FILEPATH) as config_file:
                self._client_config = ClientConfig.from_json(json.load(config_file))
        else:
            self._client_config = None

    @classmethod
    def parse_args(cls, args: List[str]) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description='Play a game of "Jeopardy!" with your friends')
        parser.add_argument('-n', '--nick', '--nickname', '--name',
                            help='The nickname you want to use (must be unique)')
        parser.add_argument('-s', '--server', '--server-address', dest='server_address',
                            help='The IP and port of the server to connect to (e.g., "192.168.0.151:5000")')
        parser.add_argument('-d', '--dark', '--dark-mode', action='store_true', dest='dark_mode',
                            help='Use the dark theme for the GUI')
        return parser.parse_args(args)

    @property
    def player_id(self) -> str:
        if self._player_id is None:
            self._player_id = self.get_config_value('JEOPARDY_PLAYER_ID', 'player_id')
            if self._player_id is None:
                self._player_id = str(uuid.uuid4())
        return self._player_id

    @property
    def server_address(self) -> str:
        if self._server_address is None:
            self._server_address = self.get_config_value('JEOPARDY_SERVER_ADDRESS', 'server_address')
            if not self._server_address:
                raise RuntimeError('You must configure a server address!')
        return self._server_address

    @property
    def nick(self) -> str:
        if self._nick is None:
            self._nick = self.get_config_value('JEOPARDY_NICKNAME', 'nick')
            if self._nick is None:
                self._nick = self.player_id
        return self._nick

    @property
    def dark_mode(self) -> bool:
        if self._dark_mode is None:
            dark_mode = self.get_config_value('JEOPARDY_DARK_MODE', 'dark_mode')
            if isinstance(dark_mode, str):
                self._dark_mode = str_to_bool(dark_mode)
            else:
                self._dark_mode = bool(dark_mode)
        return self._dark_mode

    @property
    def client_config(self) -> ClientConfig:
        return ClientConfig(
            server_address=self.server_address,
            player_id=self.player_id,
            nick=self.app.nick,
            dark_mode=self.app.dark_mode
        )

    def get_config_value(self, env_key, config_key) -> Any:
        env_value = os.getenv(env_key)
        if env_value is not None:
            return env_value
        if self._client_config is not None:
            return getattr(self._client_config, config_key)
        return None

    def run(self) -> None:
        self.app = JeopardyApp(
            server_address=self.server_address,
            player_id=self.player_id,
            nick=self.nick,
            dark_mode=self.dark_mode
        )
        try:
            self.app.run()
        finally:
            save = False
            if os.path.exists(self.DEFAULT_CONFIG_FILEPATH):
                try:
                    with open(self.DEFAULT_CONFIG_FILEPATH) as config_file:
                        existing_config = ClientConfig.from_json(json.load(config_file))
                        if existing_config.player_id == self.player_id:
                            save = True
                        else:
                            print(f'Not overwriting existing config for new player {self.player_id}')
                except Exception:
                    save = True
            else:
                save = True

            if save:
                print('Saving config file')
                dirname = os.path.dirname(self.DEFAULT_CONFIG_FILEPATH)
                if not os.path.exists(dirname):
                    os.mkdir(dirname)
                with open(self.DEFAULT_CONFIG_FILEPATH, 'w') as config_file:
                    json.dump(self.client_config.to_json(), config_file, sort_keys=True, indent=4)


def str_to_bool(string: str) -> bool:
    return string is not None and string.lower() in {'true', '1', 'yes'}


def main() -> None:
    JeopardyMain().run()


if __name__ == '__main__':
    main()
