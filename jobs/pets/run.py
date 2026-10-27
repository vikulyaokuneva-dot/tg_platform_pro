# -*- coding: utf-8 -*-
"""Manual PETS entry point; it never invokes the platform-wide runner."""
import os

from core.context import JobContext
from jobs.pets.job import run


def resolve_dry_run(env=None):
    """Keep manual runs safe and re-check the scheduled publication gates.

    GitHub Actions expressions choose the normal value of ``DRY_RUN``.  This
    small second gate protects against a future workflow regression: schedule
    runs are real only when *both* owner variables are explicitly ``1``.
    The job itself separately requires a healthy GitHub durable backend and a
    successful Telegram preflight before it can send a message.
    """
    env = os.environ if env is None else env
    if env.get("PETS_SCHEDULED_RUN", "0") == "1":
        return not (
            env.get("PETS_AUTONOMOUS_SCHEDULE_ENABLED", "0") == "1"
            and env.get("PETS_PUBLISH", "0") == "1"
        )
    return env.get("DRY_RUN", "1") == "1"


if __name__ == "__main__":
    run(JobContext("pets", "jobs/pets/storage.json", resolve_dry_run()))
