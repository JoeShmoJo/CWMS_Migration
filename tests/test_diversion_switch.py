import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT/'migration-review/diagnostics/diversion-switch'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

installer = load(TOOLS/'prepare_diversion_switch.py', 'diversion_installer')
config = load(TOOLS/'diversion_demand_config.py', 'diversion_config')

class Rule:
    def __init__(self): self.values = {}
    def varPut(self, key, value): self.values[key] = value
    def varGet(self, key): return self.values[key]
    def varExists(self, key): return key in self.values

class OpValue:
    def init(self, kind, value): self.kind, self.value = kind, value

class Types:
    RULETYPE_SPEC = 'SPEC'
    RULETYPE_MIN = 'MIN'

class SwitchTests(unittest.TestCase):
    def namespace(self, name):
        text = installer.patch(name, (ROOT/'standalone-review/scripts/externalRules'/ (name+'.py')).read_text())
        tree = ast.parse(text)
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        ns = {'OpValue': OpValue, 'OpRule': Types, '_demands_enabled': lambda network: network.enabled}
        exec(compile(tree, name, 'exec'), ns)
        return ns

    def test_diversions_returns_and_reinitialization(self):
        ns = self.namespace('DiversionFromCSV')
        class Network:
            enabled = True
            def printMessage(self, message): pass
        network, rule = Network(), Rule()
        ns.update(_getElementName=lambda r: 'Return', _resolveConfigPath=lambda *a: 'csv',
                  loadDailyConfig=lambda p: {'Return': [None]+[-30.0]*365},
                  _dayOneOf=lambda month: month,
                  getDiversionFlow=lambda table, time: table[1],
                  getHecTimeFromRuntimestep=lambda time: time)
        ns['initRuleScript'](rule, network)
        self.assertEqual(ns['runRuleScript'](rule, network, None).value, -30)
        network.enabled = False
        ns['loadDailyConfig'] = lambda p: self.fail('Disabled rule read a CSV')
        ns['initRuleScript'](rule, network)
        value = ns['runRuleScript'](rule, network, None)
        self.assertEqual((value.kind, value.value), ('SPEC', 0))
        self.assertTrue(all(x is None for x in rule.varGet('dayTable')))
        network.enabled = True
        ns['loadDailyConfig'] = lambda p: {'Return': [None]+[40.0]*365}
        ns['initRuleScript'](rule, network)
        self.assertEqual(ns['runRuleScript'](rule, network, None).value, 40)

    def test_minimum_preserved_withdrawal_skipped_and_restored(self):
        ns = self.namespace('MinFlowPlusWithdrawal')
        class Network:
            enabled = True
            def printMessage(self, message): pass
        network, rule, calls = Network(), Rule(), []
        def column(path, reservoir, label):
            calls.append(label)
            return [None]+[100.0 if label == 'minimum flow' else 20.0]*365
        ns.update(_getResvName=lambda r: 'Detroit', _resolveConfigPath=lambda *a: 'csv',
                  _columnTable=column, _genericDayOfYear=lambda t: 1,
                  getHecTimeFromRuntimestep=lambda t: t)
        ns['initRuleScript'](rule, network)
        self.assertEqual(ns['runRuleScript'](rule, network, None).value, 120)
        network.enabled = False
        calls.clear()
        ns['initRuleScript'](rule, network)
        self.assertEqual(calls, ['minimum flow'])
        self.assertEqual(ns['runRuleScript'](rule, network, None).value, 100)
        rule.varPut('minFlowTable', [None]*366)
        self.assertEqual(ns['runRuleScript'](rule, network, None).value, 0)
        # Downstream mass balance still applies to the remaining minimum.
        rule.varPut('minFlowTable', [None]+[100.0]*365)
        rule.varPut('downstreamSpec', {'reservoir': 'Foster'})
        rule.varPut('localFlowTS', 'local inflow')
        ns['releaseForDownstreamTarget'] = lambda *a: 75
        self.assertEqual(ns['runRuleScript'](rule, network, None).value, 75)
        network.enabled = True
        ns['initRuleScript'](rule, network)
        self.assertEqual(rule.varGet('withdrawalTable')[1], 20)

    def test_config_strict_boolean_and_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'flag.json'
            class Network:
                def makeAbsolutePathFromWatershed(self, relative): return str(path)
            for value in (True, False):
                path.write_text(json.dumps({'diversion_demands_enabled': value}))
                self.assertIs(config.enabled(Network()), value)
            for value in ('false', 0, None):
                path.write_text(json.dumps({'diversion_demands_enabled': value}))
                with self.assertRaises(ValueError): config.enabled(Network())

    def test_sandbox_copy_preserves_source_and_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            source, dest = Path(temp)/'source', Path(temp)/'copy'
            rules = source/'scripts/externalRules'
            rules.mkdir(parents=True)
            for name in ('DiversionFromCSV', 'MinFlowPlusWithdrawal'):
                data = (ROOT/'standalone-review/scripts/externalRules'/(name+'.py')).read_bytes()
                (rules/(name+'.py')).write_bytes(data)
            (source/'simulation.dss').write_bytes(b'\x00DSS unchanged')
            installer.prepare(source, dest)
            self.assertEqual((source/'simulation.dss').read_bytes(), (dest/'simulation.dss').read_bytes())
            for name in ('DiversionFromCSV', 'MinFlowPlusWithdrawal'):
                self.assertNotIn('DIVERSION_DEMAND_SWITCH', (rules/(name+'.py')).read_text())
            self.assertTrue(json.loads((dest/'scripts/diversion-demands.json').read_text())['diversion_demands_enabled'])
            with self.assertRaises(ValueError): installer.prepare(source, dest)
            with self.assertRaises(ValueError): installer.patch('DiversionFromCSV', 'unknown')

if __name__ == '__main__': unittest.main()
