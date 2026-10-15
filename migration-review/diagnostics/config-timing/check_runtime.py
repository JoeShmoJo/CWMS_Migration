import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_read_timing_diagnostic as diagnostic
from cwms.diagnostics import ConfigReadTimings
from java.lang import Thread
from java.util.concurrent import Executors, Callable, TimeUnit
from java.nio.file import Files
root = str(Files.createTempDirectory('config-timing-check-'))
diagnostic.REPORT_ROOT = root
sentinel = ['unchanged']
def read_file(path):
    Thread.sleep(1)
    return sentinel
namespace = {'fileOpenReadClose': read_file}
diagnostic.instrument_module(namespace, 'NWDJyLib.cFile', ['fileOpenReadClose'], 'read')
wrapped = namespace['fileOpenReadClose']
diagnostic.instrument_module(namespace, 'NWDJyLib.cFile', ['fileOpenReadClose'], 'read')
assert namespace['fileOpenReadClose'] is wrapped
def load_config(path):
    if path == 'fail': raise ValueError('original failure')
    return namespace['fileOpenReadClose'](path)
loaders = {'loadConfig': load_config}
diagnostic.instrument_module(loaders, 'test', ['loadConfig'], 'loader')
class Work(Callable):
    def call(self):
        for i in range(10): assert loaders['loadConfig']('config.csv') is sentinel
        return True
pool = Executors.newFixedThreadPool(4)
try:
    futures = [pool.submit(Work()) for i in range(4)]
    for future in futures: assert future.get(10, TimeUnit.SECONDS)
finally:
    pool.shutdown()
    assert pool.awaitTermination(10,TimeUnit.SECONDS)
try: loaders['loadConfig']('fail')
except ValueError as error: assert str(error) == 'original failure'
else: raise AssertionError('Exception swallowed')
report = str(ConfigReadTimings.writeReport()).split('CONFIG TIMING REPORT: ')[1]
rows = list(csv.DictReader(open(os.path.join(report,'timings.csv'))))
assert sum(int(row['calls']) for row in rows if row['category']=='read') == 40
assert sum(int(row['calls']) for row in rows if row['category']=='loader') == 41
assert sum(int(row['failures']) for row in rows) == 1
assert all(float(row['exclusive_ms']) <= float(row['inclusive_ms']) for row in rows)
assert 'snapshot: 0' in open(os.path.join(report,'summary.txt')).read()
print('PASS: concurrent counts, nested timings, return identity, exceptions, idempotent wrapping, reports')
