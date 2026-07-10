.PHONY: all install install-release install-dev install-opencad build core doctor doctor-full spec-validate spec-summary reconcile manifest drawings qcad-pdfs openscad freecad ifc cadquery opencad-pilot provenance test lint validate preflight clean-pycache

PYTHON := .venv/bin/python
VENV_PYTHON ?= python3.11

all: build

install:
	$(VENV_PYTHON) -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

install-release:
	$(VENV_PYTHON) -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -c constraints-release.txt

install-dev: install
	$(PYTHON) -m pip install -r requirements-dev.txt

install-opencad: install
	$(PYTHON) -m pip install -r requirements-opencad.txt

build: spec-validate
	$(PYTHON) tools/build_all.py

core: spec-validate
	$(PYTHON) tools/build_all.py --profile core

doctor:
	$(PYTHON) tools/doctor.py --profile core

doctor-full:
	$(PYTHON) tools/doctor.py --profile full

spec-validate:
	$(PYTHON) tools/project_spec.py validate

spec-summary:
	$(PYTHON) tools/project_spec.py summary

reconcile: spec-validate
	$(PYTHON) tools/reconcile_parameters.py

manifest:
	$(PYTHON) tools/build_manifest.py

drawings:
	$(PYTHON) tools/generate_drawings.py

qcad-pdfs:
	$(PYTHON) tools/export_qcad_pdfs.py

openscad:
	$(PYTHON) tools/generate_openscad_exports.py

freecad:
	$(PYTHON) tools/generate_freecad_assets.py

ifc:
	$(PYTHON) tools/generate_ifc.py

cadquery:
	$(PYTHON) cadquery/generate_all.py

opencad-pilot:
	$(PYTHON) integrations/opencad/pilot.py

provenance:
	$(PYTHON) tools/build_provenance.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

validate: spec-validate
	$(PYTHON) validation/run_all.py

preflight: spec-validate
	$(PYTHON) tools/preflight_public_package.py

clean-pycache:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
