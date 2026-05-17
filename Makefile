.PHONY: run test lint install

run:
	streamlit run app.py

test:
	pytest tests/ -m "not slow" -q

test-all:
	pytest tests/ -q

lint:
	ruff check . --select E,W,F --ignore E501

install:
	pip install -r requirements.txt
