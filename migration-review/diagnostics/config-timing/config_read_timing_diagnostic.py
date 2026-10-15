"""Jython timing wrappers. No cache, logging per call, or result transformation."""
from java.io import File
from cwms.diagnostics import ConfigReadTimings

# Replaced with the copied watershed's report directory by the installer.
REPORT_ROOT = None


def _wrap(function, category, label):
    def timed(*args, **kwargs):
        filename = args[0] if args else kwargs.get('configCSV', '<unspecified>')
        try:
            filename = File(unicode(filename)).getAbsolutePath()
        except Exception:
            filename = '<unavailable>'
        token = ConfigReadTimings.begin(category, label, unicode(filename))
        failed = True
        try:
            result = function(*args, **kwargs)
            failed = False
            return result
        finally:
            ConfigReadTimings.finish(token, failed)
    timed._config_timing_wrapped = True
    timed.__name__ = function.__name__
    timed.__doc__ = function.__doc__
    return timed


def instrument_module(namespace, module_name, names, category):
    if REPORT_ROOT is None:
        raise RuntimeError('Diagnostic REPORT_ROOT not configured')
    ConfigReadTimings.configure(REPORT_ROOT)
    for name in names:
        function = namespace.get(name)
        if callable(function) and not getattr(function, '_config_timing_wrapped', False):
            namespace[name] = _wrap(function, category, module_name+'.'+name)
