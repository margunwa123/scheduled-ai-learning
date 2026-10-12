.PHONY: setup

setup:
	sudo apt update
	sudo apt install -y python3-venv python3-pip
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install google-genai python-dotenv
