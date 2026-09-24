.PHONY: all bridge comtrade census portwatch routing load \
	dbt-seed dbt-seed-full dbt-build dbt-compile dbt-debug dbt-run dbt-test dbt-docs

# Ingest scripts read secrets through ingest/config.py (python-dotenv), so
# they need no sourcing. Every ingest target is cache-first: a rerun with the
# cache on disk costs zero API calls. Pass flags through ARGS, e.g.
#   make comtrade ARGS="--refresh 2025"
#   make routing ARGS="--sample 20 --seed 1"
PY = .venv/bin/python

# dbt does not read .env itself; these targets source it and point dbt at
# dbt/profiles.yml (DBT_PROFILES_DIR) instead of ~/.dbt/profiles.yml.
DBT = set -a && . ./.env && set +a && DBT_PROFILES_DIR=dbt .venv/bin/dbt

# Run order: basket_codes (manual) -> bridge -> comtrade, census, portwatch
# -> routing -> load -> dbt. Targets do not depend on each other; `all` runs
# them in order. dbt build seeds, runs and tests, so `all` skips dbt-seed.
all: bridge comtrade census portwatch routing load dbt-build

bridge:
	$(PY) -m ingest.hs_bridge $(ARGS)

comtrade:
	$(PY) -m ingest.comtrade $(ARGS)

census:
	$(PY) -m ingest.census $(ARGS)

portwatch:
	$(PY) -m ingest.portwatch $(ARGS)

routing:
	$(PY) -m ingest.routing $(ARGS)

load:
	$(PY) -m ingest.load $(ARGS)

dbt-seed:
	$(DBT) seed --project-dir dbt

# Rebuilds every seed table from scratch. Needed when a seed's columns or
# column types change; a plain seed only truncates and reinserts.
dbt-seed-full:
	$(DBT) seed --full-refresh --project-dir dbt

dbt-build:
	$(DBT) build --project-dir dbt

# Compiles models and dbt/analyses/ (dbt build does not compile analyses).
dbt-compile:
	$(DBT) compile --project-dir dbt

dbt-debug:
	$(DBT) debug --project-dir dbt

dbt-run:
	$(DBT) run --project-dir dbt

dbt-test:
	$(DBT) test --project-dir dbt

dbt-docs:
	$(DBT) docs generate --project-dir dbt
