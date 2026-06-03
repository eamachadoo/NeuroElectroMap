.PHONY: install install-dev install-desktop test run run-ds004473 validate-ds004473 data data-ds004473 viewer desktop ports help

VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest

help:
	@echo "Available commands:"
	@echo "  make setup            Create venv + install all dependencies"
	@echo "  make install          Install runtime dependencies into existing venv"
	@echo "  make install-dev      Install runtime + dev/test dependencies"
	@echo "  make install-desktop  Install pywebview for the desktop launcher"
	@echo "  make data             Download MNE sample sEEG dataset (small, ~25 MB)"
	@echo "  make data-ds004473    Download ds004473 sub-12 from OpenNeuro (~75 MB, real patient)"
	@echo "  make test             Run the test suite"
	@echo "  make run              Run pipeline + export viewer data (set MRI=, CT=, SUBJECT_DIR=)"
	@echo "  make run-ds004473     Run pipeline on ds004473 sub-12 (one-line shortcut)"
	@echo "  make validate-ds004473 Run full CT pipeline + shaft-aware validation against ds004473 GT"
	@echo "  make viewer           Serve the viewer over loopback HTTP (open in browser)"
	@echo "  make desktop          Open the viewer in a native desktop window"
	@echo "  make ports            List all TCP ports currently in LISTEN state"

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

install-desktop: $(VENV)/bin/activate
	$(PIP) install -r requirements-desktop.txt

data: $(VENV)/bin/activate
	$(PYTHON) scripts/download_data.py

data-ds004473: $(VENV)/bin/activate
	$(PYTHON) scripts/download_ds004473.py

# Browser-based viewer — handy for development (auto-reload on edit).
# Server starts and the browser is opened on http://localhost:8765/ —
# the dev server redirects "/" to the viewer automatically.
# Cross-platform: open on macOS, xdg-open on Linux, start on Windows.
OPEN_CMD := $(shell command -v open 2>/dev/null \
                  || command -v xdg-open 2>/dev/null \
                  || command -v start 2>/dev/null \
                  || echo true)

viewer: $(VENV)/bin/activate
	@echo "─── Freeing port 8765 if held ───"
	-@lsof -t -iTCP:8765 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
	@$(MAKE) --no-print-directory ports
	@echo ""
	@( sleep 0.6 && $(OPEN_CMD) http://localhost:8765/ ) &
	$(PYTHON) scripts/dev_server.py 8765

# Useful diagnostic when the dev server complains about an address in use:
# `make ports` lists every TCP socket currently in LISTEN state on the box,
# one per line, sorted and de-duplicated.
ports:
	@echo "─── TCP ports in LISTEN state ───"
	@printf "  %-6s %-14s %-7s %s\n" PORT COMMAND PID HOST
	@lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null \
	  | awk 'NR>1 { \
	      n=split($$9, a, ":"); port=a[n]; host=$$9; \
	      sub(":"port"$$", "", host); \
	      printf "  %-6s %-14s %-7s %s\n", port, $$1, $$2, host \
	    }' \
	  | sort -u \
	  || echo "  (lsof unavailable or no listeners)"

# Native desktop window (pywebview). Requires `make install-desktop`.
desktop: $(VENV)/bin/activate
	$(PYTHON) scripts/launch_desktop.py

test: $(VENV)/bin/activate
	$(PYTEST) tests/ -v

# Pipeline runner. `--export-viewer` is on by default so `make desktop` /
# `make viewer` show real data right after.
# Example: make run MRI=data/raw/mne_seeg_sample/T1.nii.gz CT=data/raw/mne_seeg_sample/CT.nii.gz SUBJECT_DIR=data/raw/mne_seeg_sample/sample_seeg
SUBJECT_DIR ?= data/raw/mne_seeg_sample/sample_seeg
CERT_FILE   := $(shell $(PYTHON) -c "import certifi; print(certifi.where())" 2>/dev/null)

run: $(VENV)/bin/activate
	SSL_CERT_FILE=$(CERT_FILE) REQUESTS_CA_BUNDLE=$(CERT_FILE) \
	$(PYTHON) main.py --mri $(MRI) --ct $(CT) --subject-dir $(SUBJECT_DIR) \
		--plot --export-viewer --output-dir outputs/

# Shortcut for the dataset we built the viewer around (real sEEG patient).
# ds004473 ships verified ground-truth electrode positions — we use those
# directly via --use-ground-truth, so CT segmentation is skipped entirely.
# This gives 100% positional accuracy + clinical electrode names (LTP1, RAHIPP3, ...).
#
# We pass the *ACPC* file (BIDS: `iEEGCoordinateSystem: ACPC`,
# `IntendedFor: …/mri/T1.mgz`) rather than the ScanRAS one because the
# ACPC frame is already aligned with the pial surface (FreeSurfer tkRAS).
# Using ScanRAS would require a T1w→T1.mgz scanner-RAS bridge that is not
# guaranteed to exist for every dataset (it isn't for ds004473).
run-ds004473: $(VENV)/bin/activate
	SSL_CERT_FILE=$(CERT_FILE) REQUESTS_CA_BUNDLE=$(CERT_FILE) \
	$(PYTHON) main.py \
	  --mri data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz \
	  --subject-dir data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12 \
	  --use-ground-truth data/raw/ds004473/sub-12/ieeg/sub-12_space-ACPC_electrodes.tsv \
	  --plot --export-viewer --output-dir outputs/

# Validation run: detect electrodes from CT and score them against the
# clinically-verified ScanRAS positions using the shaft-aware matcher
# (PCA axis fit per shaft, Hungarian assignment within shaft, no predicted
# claimed twice). The GT here is the ScanRAS file because the predicted
# coordinate used for scoring (`centroid_scanner_mm`) lives in T1w ScanRAS.
validate-ds004473: $(VENV)/bin/activate
	SSL_CERT_FILE=$(CERT_FILE) REQUESTS_CA_BUNDLE=$(CERT_FILE) \
	$(PYTHON) main.py \
	  --mri data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz \
	  --ct  data/raw/ds004473/sub-12/anat/sub-12_ct.nii.gz \
	  --subject-dir data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12 \
	  --validate data/raw/ds004473/sub-12/ieeg/sub-12_space-ScanRAS_electrodes.tsv \
	  --output-dir outputs/sub-12-validated
