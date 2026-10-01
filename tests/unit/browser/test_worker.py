from threading import get_ident

from ai_workshop.browser.worker import BrowserWorker


class FakeEngine:
    def __init__(self): self.started=False; self.stopped=False; self.thread_ids=[]
    def start(self): self.started=True; self.thread_ids.append(get_ident())
    def stop(self): self.stopped=True; self.thread_ids.append(get_ident())
    def add(self,a,b): self.thread_ids.append(get_ident()); return a+b
    def fail(self): raise ValueError("boom")


def test_worker_runs_engine_calls_on_one_dedicated_thread():
    engine=FakeEngine(); worker=BrowserWorker(lambda:engine); worker.start()
    try: assert worker.call("add",2,3)==5; assert worker.call("add",4,5)==9
    finally: worker.stop()
    assert engine.started and engine.stopped and len(set(engine.thread_ids)) == 1


def test_worker_propagates_engine_error():
    engine=FakeEngine(); worker=BrowserWorker(lambda:engine); worker.start()
    try:
        try: worker.call("fail")
        except ValueError as exc: assert str(exc)=="boom"
        else: raise AssertionError("expected ValueError")
    finally: worker.stop()
