# jeopardy

## Installing

```
$ make install
```

## Running the server

```
$ jeopardyd
```

or:

```
$ python3.7 jeopardy/server.py
```

## Running the client

```
$ jeopardy -n <nick> -s <server_address> [-d]
```

or:

```
$ python3.7 -m jeopardy -n <nick> -s <server_address> [-d]
```

or:

```
$ python3.7 jeopardy/main.py -n <nick> -s <server_address> [-d]
```

### Options

* **-n, --nickname** - the nickname to use (must be unique)
* **-s, --server-address** - the address and port of the remote server to connect to
* **-d, --dark-mode** - use the dark theme in the GUI

You only need to specify **-n** and **-s** once, or if you want to change them. Otherwise,
the previously-used value will be used on the next invocation of the program.
