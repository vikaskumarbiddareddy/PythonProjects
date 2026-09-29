# Goggin Project

Python project scaffold for the Goggin project.

## Layout

```
Goggin project/
├── goggin/          # package source
│   ├── __init__.py
│   └── main.py      # entry point
├── tests/           # unit tests
│   └── test_main.py
└── requirements.txt
```

## Getting started

```bash
cd "Goggin project"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m goggin.main
python -m unittest discover tests
```
