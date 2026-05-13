.PHONY: install install-dev test run data help

VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest

help:
	@echo "Available commands:"
	@echo "  make setup        Create venv + install all dependencies"
	@echo "  make install      Install runtime dependencies into existing venv"
	@echo "  make install-dev  Install runtime + dev/test dependencies"
	@echo "  make data         Download MNE sample sEEG dataset (MRI + CT)"
	@echo "  make test         Run the test suite"
	@echo "  make run          Run pipeline (set MRI= and CT= variables)"

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

setup: $(VENV)/bin/activate
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "Done. Activate with: source $(VENV)/bin/activate"

install: $(VENV)/bin/activate
	$(PIP) install -r requirements.txt

install-dev: $(VENV)/bin/activate
	$(PIP) install -r requirements-dev.txt

data: $(VENV)/bin/activate
	$(PYTHON) scripts/download_data.py

test: $(VENV)/bin/activate
	$(PYTEST) tests/ -v

# Example: make run MRI=data/raw/mne_seeg_sample/T1.nii.gz CT=data/raw/mne_seeg_sample/CT.nii.gz SUBJECT_DIR=data/raw/mne_seeg_sample/sample_seeg
SUBJECT_DIR ?= data/raw/mne_seeg_sample/sample_seeg
CERT_FILE   := $(shell $(PYTHON) -c "import certifi; print(certifi.where())" 2>/dev/null)

run: $(VENV)/bin/activate
	SSL_CERT_FILE=$(CERT_FILE) REQUESTS_CA_BUNDLE=$(CERT_FILE) \
	$(PYTHON) main.py --mri $(MRI) --ct $(CT) --subject-dir $(SUBJECT_DIR) --plot --output-dir outputs/
