# jeopardy

## Dedication

This project is dedicated to Mr. William D. Dye, my father and one of the best
armchair *Jeopardy!* players I have ever known.

## Installing

```
$ make install
```

## Running the server

```
$ jeopardyd [-s <server_ip>] [-p <server_port>]
```

or:

```
$ python3.7 jeopardy/server.py [-s <server_ip>] [-p <server_port>]
```

### Options

* **-s, --server-address** - the IP address on which to run the server
* **-p, --port** - the port on which to run the server

## Running the client

```
$ jeopardy -n <nick> -s <server_address> [-c <client_ip>] [-p <client_port>] [-d]
```

or:

```
$ python3.7 -m jeopardy -n <nick> -s <server_address> [-c <client_ip>] [-p <client_port>] [-d]
```

or:

```
$ python3.7 jeopardy/main.py -n <nick> -s <server_address> [-c <client_ip>] [-p <client_port>] [-d]
```

### Options

* **-n, --nickname** - the nickname to use (must be unique)
* **-s, --server-address** - the address and port of the remote server to connect to
* **-c, --client-address** - the IP address for the server to connect to in order to send events
  (defaults to the external IP address of the host running the client)
* **-p, --client-port** - the port for the server to connect to in order to send events
* **-d, --dark-mode** - use the dark theme in the GUI

You only need to specify **-n**, **-s**, and **-p** once, or if you want to change them. Otherwise,
the previously-used value will be used on the next invocation of the program.
