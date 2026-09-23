.PHONY: dbt-debug dbt-run dbt-test dbt-build dbt-seed dbt-docs

# dbt does not read .env itself; these targets source it and point dbt at
# dbt/profiles.yml (DBT_PROFILES_DIR) instead of ~/.dbt/profiles.yml.
DBT = set -a && . ./.env && set +a && DBT_PROFILES_DIR=dbt .venv/bin/dbt

dbt-debug:
	$(DBT) debug --project-dir dbt

dbt-run:
	$(DBT) run --project-dir dbt

dbt-test:
	$(DBT) test --project-dir dbt

dbt-build:
	$(DBT) build --project-dir dbt

dbt-seed:
	$(DBT) seed --project-dir dbt

dbt-docs:
	$(DBT) docs generate --project-dir dbt
