.PHONY: all install build manifest drawings qcad-pdfs openscad freecad ifc cadquery validate preflight clean-pycache

PYTHON := .venv/bin/python

all: build

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

build:
	$(PYTHON) tools/build_all.py

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

validate:
	$(PYTHON) validation/run_all.py

preflight:
	$(PYTHON) tools/preflight_public_package.py

clean-pycache:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
