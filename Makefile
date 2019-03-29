clean:
	pip3 uninstall -y jeopardy

install:
	pip3 install --ignore-installed . || pip3 install --ignore-installed --user .
