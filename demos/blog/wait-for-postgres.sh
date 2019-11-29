#!/bin/bash
# from https://docs.docker.com/compose/startup-order/
# wait-for-postgres.sh

set -e

host="$1"
shift
cmd="$@"

until python -c 'import os;import psycopg2;psycopg2.connect("dbname=" + os.environ["POSTGRES_DB"] + " user=" + os.environ["POSTGRES_USER"] + " host=postgres password=" + os.environ["POSTGRES_PASSWORD"])'; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - executing command"
exec $cmd
