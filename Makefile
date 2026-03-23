.PHONY: install install-dev test run help

help:
	@echo "Available commands:"
	@echo "  make install      Install runtime dependencies"
	@echo "  make install-dev  Install runtime + dev/test dependencies"
	@echo "  make test         Run the test suite"
	@echo "  make run          Run pipeline (set MRI= and CT= variables)"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v

# Example: make run MRI=data/mri.nii.gz CT=data/ct.nii.gz
run:
	python main.py --mri $(MRI) --ct $(CT) --plot --output-dir outputs/
