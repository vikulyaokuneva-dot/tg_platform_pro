class JobContext:
    def __init__(self, job_name, storage_path, dry_run=False):
        self.job_name = job_name
        self.storage_path = storage_path
        self.dry_run = dry_run

    def log(self, message):
        prefix = "DRY-RUN" if self.dry_run else "RUN"
        print(f"[{prefix}][{self.job_name}] {message}")
