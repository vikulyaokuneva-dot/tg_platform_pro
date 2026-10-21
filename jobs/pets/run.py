# -*- coding: utf-8 -*-
"""Manual PETS entry point; it never invokes the platform-wide runner."""
import os

from core.context import JobContext
from jobs.pets.job import run


if __name__ == "__main__":
    run(JobContext("pets", "jobs/pets/storage.json", os.getenv("DRY_RUN", "1") == "1"))
