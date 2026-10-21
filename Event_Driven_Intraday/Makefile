# Event-Driven Intraday module — one-command workflows
#
#   make test        run the 23-test suite
#   make data        regenerate the committed sample CSVs (fixed seeds)
#   make notebooks   rebuild + execute every lesson notebook
#   make all         data, test, notebooks

PY ?= python

.PHONY: all test data notebooks clean

all: data test notebooks

test:
	$(PY) -m pytest -q

data:
	$(PY) tools/make_sample_data.py

notebooks:
	$(PY) tools/build_notebooks.py

# Remove build noise only; never touches data/ or notebooks/.
clean:
	rm -rf .pytest_cache tools/lessons/__pycache__ intraday_engine/__pycache__ tests/__pycache__
