import json
import os
import uuid

from jeopardy_model import ClientConfig
from jeopardy_ui import JeopardyApp


class JeopardyMain:

    DEFAULT_CONFIG_FILEPATH = os.path.expanduser('~/.jeopardy/config.json')

    def __init__(self, player_id=None, nick=None, server_address=None):
        self._player_id = player_id
        self._nick = nick
        self._server_address = server_address

        if os.path.exists(self.DEFAULT_CONFIG_FILEPATH):
            with open(self.DEFAULT_CONFIG_FILEPATH) as config_file:
                self._client_config = ClientConfig.from_json(json.load(config_file))
        else:
            self._client_config = None

    @property
    def player_id(self):
        if self._player_id is None:
            self._player_id = self.get_config_value('JEOPARDY_CLIENT_PLAYER_ID', 'player_id')
            if self._player_id is None:
                self._player_id = str(uuid.uuid4())
        return self._player_id

    @property
    def server_address(self):
        if self._server_address is None:
            self._server_address = self.get_config_value('JEOPARDY_SERVER_ADDRESS', 'server_address')
            if self._server_address is None:
                raise RuntimeError('You must configure a server address!')
        return self._server_address

    @property
    def nick(self):
        if self._nick is None:
            self._nick = self.get_config_value('JEOPARDY_CLIENT_NICKNAME', 'nick')
            if self._nick is None:
                self._nick = self.player_id
        return self._nick

    @property
    def client_config(self):
        if self._client_config is not None:
            return self._client_config
        return ClientConfig(
            server_address=self.server_address,
            player_id=self.player_id,
            nick=self.nick
        )

    def get_config_value(self, env_key, config_key):
        env_value = os.getenv(env_key)
        if env_value is not None:
            return env_value
        if self._client_config is not None:
            return getattr(self._client_config, config_key)
        return None

    def run(self):
        app = JeopardyApp(
            server_address=self.server_address,
            player_id=self.player_id,
            nick=self.nick
        )
        try:
            app.run()
        finally:
            if not os.path.exists(self.DEFAULT_CONFIG_FILEPATH):
                print('Saving config file')
                dirname = os.path.dirname(self.DEFAULT_CONFIG_FILEPATH)
                if not os.path.exists(dirname):
                    os.mkdir(dirname)
                with open(self.DEFAULT_CONFIG_FILEPATH, 'w') as config_file:
                    json.dump(self.client_config.to_json(), config_file)


def main():
    JeopardyMain().run()


if __name__ == '__main__':
    main()
