"""Experimental Jython state isolation for a private native compute JVM."""
from java.lang import Class
from java.util.concurrent import Executors, ThreadFactory, ThreadPoolExecutor
from java.lang import Runnable
from org.python.core import Py, PySystemState


class StateIsolatedWorker(Runnable):
    def __init__(self, task):
        self.task = task

    def run(self):
        # The Java executor runs all of this worker's tasks inside this state.
        # A temporary script compiler must not close another worker's files
        # or run another worker's threading exit handlers.
        Py.setSystemState(PySystemState())
        self.task.run()


class StateIsolatedFactory(ThreadFactory):
    def __init__(self):
        self.default = Executors.defaultThreadFactory()

    def newThread(self, task):
        return self.default.newThread(StateIsolatedWorker(task))


def install_on_pool(pool):
    if pool.getPoolSize() != 0:
        raise RuntimeError('Worker isolation must be installed before workers start')
    pool.setThreadFactory(StateIsolatedFactory())


def isolate_native_workers():
    factory = Class.forName('hec.rss.compute.c')
    getter = factory.getDeclaredMethod('a', [])
    getter.setAccessible(True)
    delegate = getter.invoke(None, [])
    pool = None
    for field in delegate.getClass().getDeclaredFields():
        field.setAccessible(True)
        candidate = field.get(delegate)
        if isinstance(candidate, ThreadPoolExecutor):
            pool = candidate
            break
    if pool is None:
        raise RuntimeError('Native executor pool not found; isolation not installed')
    if delegate.getPoolCount() != 2:
        raise RuntimeError('Trial requires exactly two workers')
    install_on_pool(pool)
    print('EXPERIMENTAL WORKER ISOLATION: two independent Jython runtime states')
