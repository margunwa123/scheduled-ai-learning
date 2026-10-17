.PHONY: setup

setup:
	sudo apt update && sudo apt install -y python3-venv python3-pip
	curl -LsSf https://astral.sh/uv/install.sh | sh
	uv sync
