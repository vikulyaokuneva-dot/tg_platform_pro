import os, time, importlib, json
from datetime import datetime
from core.context import JobContext

JOB_DELAY_SECONDS = int(os.getenv("JOB_DELAY_SECONDS", "30"))
DRY_RUN = os.getenv("DRY_RUN") == "1"
JOBS_DIR = "jobs"

def load_stats(path):
    if not os.path.exists(path):
        return {"runs":0,"success":0,"errors":0,"total_duration":0}
    with open(path, "r") as f:
        return json.load(f)

def save_stats(path, stats):
    with open(path, "w") as f:
        json.dump(stats, f, indent=2)

def discover_jobs():
    for name in sorted(os.listdir(JOBS_DIR)):
        if os.path.isdir(f"{JOBS_DIR}/{name}") and os.path.exists(f"{JOBS_DIR}/{name}/job.py"):
            yield name

def run_jobs():
    for job_name in discover_jobs():
        if job_name.startswith("generate_") and os.getenv("REPORT_ONLY") != "1":
            continue

        ctx = JobContext(job_name, f"{JOBS_DIR}/{job_name}/storage.json", DRY_RUN)
        stats_path = f"{JOBS_DIR}/{job_name}/stats.json"
        stats = load_stats(stats_path)

        start = time.time()
        error = False

        try:
            module = importlib.import_module(f"jobs.{job_name}.job")
            module.run(ctx)
        except Exception as e:
            error = True
            ctx.log(f"ERROR: {e}")
        finally:
            duration = time.time() - start
            stats["runs"] += 1
            stats["total_duration"] += duration
            stats["errors"] += 1 if error else 0
            stats["success"] += 0 if error else 1
            stats["last_run"] = datetime.utcnow().isoformat()
            save_stats(stats_path, stats)

        time.sleep(JOB_DELAY_SECONDS)

if __name__ == "__main__":
    run_jobs()
