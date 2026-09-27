.PHONY: all bridge comtrade census portwatch routing schema load export \
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
# -> routing -> schema -> load -> dbt. Targets do not depend on each other;
# `all` runs them in order. dbt build seeds, runs and tests, so `all` skips
# dbt-seed.
all: bridge comtrade census portwatch routing schema load dbt-build

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

# Applies the raw landing DDL to the icr_postgres container. Idempotent
# (CREATE ... IF NOT EXISTS and COMMENT ON only, no DROP), so `all` runs it on
# every pass. psql takes credentials from the container's environment, not
# from .env.
schema:
	docker exec -i icr_postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < db/schema.sql

load:
	$(PY) -m ingest.load $(ARGS)

# Dumps the fct_ marts to exports/*.csv for Tableau. Run after dbt-build.
export:
	$(PY) -m ingest.export $(ARGS)

dbt-seed:
	$(DBT) seed --project-dir dbt $(ARGS)

# Rebuilds every seed table from scratch. Needed when a seed's columns or
# column types change; a plain seed only truncates and reinserts.
dbt-seed-full:
	$(DBT) seed --full-refresh --project-dir dbt $(ARGS)

dbt-build:
	$(DBT) build --project-dir dbt $(ARGS)

# Compiles models and dbt/analyses/ (dbt build does not compile analyses).
dbt-compile:
	$(DBT) compile --project-dir dbt $(ARGS)

dbt-debug:
	$(DBT) debug --project-dir dbt

dbt-run:
	$(DBT) run --project-dir dbt $(ARGS)

dbt-test:
	$(DBT) test --project-dir dbt $(ARGS)

dbt-docs:
	$(DBT) docs generate --project-dir dbt
