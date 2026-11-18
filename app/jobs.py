"""Minimal in-process background job queue.

Long tasks (plate solving, frame analysis) run in a worker thread; the browser
polls /api/jobs/<id> for state, progress and the result.
"""
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=2)
_sync_slots = threading.BoundedSemaphore(2)
_jobs = {}
_lock = threading.Lock()
_MAX_AGE_S = 3600


class Job:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.state = 'queued'        # queued -> running -> done | failed
        self.progress = 0.0          # 0..1
        self.message = 'Queued'
        self.result = None
        self.error = None
        self.created = time.time()
        self.files = {}              # name -> (bytes, mimetype), e.g. a preview image

    def update(self, progress=None, message=None):
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if message is not None:
            self.message = message

    def to_dict(self):
        return {'id': self.id, 'state': self.state, 'progress': self.progress,
                'message': self.message, 'result': self.result, 'error': self.error}


def submit(fn, *args, sync=False, **kwargs):
    """Run fn(job, *args, **kwargs) in the background, or right now if sync=True. Returns the Job.

    sync=True is for hosts that only give the process CPU while a request is open (Cloud Run):
    the job finishes before the response is sent, and the browser's first poll sees the result.
    sync='thread' starts it at once on its own thread, for a request that streams its progress.
    At most two run at once any way, to bound memory use.
    """
    job = Job()
    with _lock:
        _prune()
        _jobs[job.id] = job

    def run():
        job.state = 'running'
        try:
            job.result = fn(job, *args, **kwargs)
            job.state, job.progress, job.message = 'done', 1.0, 'Done'
        except Exception as exc:
            # Expected failures (bad file, no solution) carry a user-facing message; log the rest.
            if not isinstance(exc, (ValueError, LookupError)) and type(exc).__name__ != 'SolveError':
                traceback.print_exc()
            job.state, job.error, job.message = 'failed', str(exc) or type(exc).__name__, 'Failed'

    if sync == 'thread':
        # Runs now, inside the current request, but on its own thread so the request can stream
        # progress while it works (the host still gives CPU, as the request is open).
        def guarded():
            with _sync_slots:
                run()
        threading.Thread(target=guarded, daemon=True).start()
    elif sync:
        with _sync_slots:
            run()
    else:
        _executor.submit(run)
    return job


def get(job_id):
    with _lock:
        return _jobs.get(job_id)


def discard(job_id):
    """Forget a job and everything it holds (result, preview image)."""
    with _lock:
        _jobs.pop(job_id, None)


def _prune():
    cutoff = time.time() - _MAX_AGE_S
    for jid in [j for j, job in _jobs.items() if job.created < cutoff and job.state in ('done', 'failed')]:
        del _jobs[jid]
