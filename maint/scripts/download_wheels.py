#!/usr/bin/env python3

import asyncio
import json
import pathlib
import sys
from tornado.httpclient import AsyncHTTPClient

BASE_URL = "https://ci.appveyor.com/api"


async def fetch_job(directory, job):
    http = AsyncHTTPClient()
    artifacts = await http.fetch(f"{BASE_URL}/buildjobs/{job}/artifacts")
    paths = [pathlib.PurePosixPath(a["fileName"]) for a in json.loads(artifacts.body)]

    for path in paths:
        artifact = await http.fetch(f"{BASE_URL}/buildjobs/{job}/artifacts/{path}")
        with open(directory.joinpath(path.name), "wb") as f:
            f.write(artifact.body)


async def main():
    http = AsyncHTTPClient()
    try:
        _, version = sys.argv
    except ValueError:
        print("usage: maint/scripts/download_wheels.py v6.0.1", file=sys.stderr)
        sys.exit(1)

    directory = pathlib.Path(f"downloads-{version}")
    directory.mkdir(exist_ok=True)

    build = await http.fetch(f"{BASE_URL}/projects/bdarnell/tornado/branch/{version}")
    jobs = [job["jobId"] for job in json.loads(build.body)["build"]["jobs"]]

    await asyncio.gather(*(fetch_job(directory, job) for job in jobs))


if __name__ == "__main__":
    asyncio.run(main())
