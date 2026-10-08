import ast
import datetime
import json
from pathlib import Path
import sys
import tempfile
import pickle
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'
sys.path.insert(0, str(SCRIPTS))
import prepare_rts_augmentation as preparation
from prepare_rts_augmentation import load_functions, calculate, validate_daily, sha256, read_config, read_water_year_type
from load_rts_augmentation import validate_manifest


class PreparationTests(unittest.TestCase):
    def test_abundant_code_is_explicit_and_not_converted_as_storage(self):
        dates = pd.date_range('2027-05-15', periods=2)
        dss = types.SimpleNamespace(read_ts=lambda *a, **k: types.SimpleNamespace(
            units='ac-ft', values=[4.0, 4.0], pytimes=dates))
        with self.assertRaisesRegex(ValueError, 'unexpected units'):
            read_water_year_type(dss, '/', 'storage-maf')
        self.assertEqual(list(read_water_year_type(dss, '/', 'fixed-abundant')), [4.0, 4.0])
        dss.read_ts = lambda *a, **k: types.SimpleNamespace(units='ac-ft', values=[4.0, 3.0], pytimes=dates)
        with self.assertRaisesRegex(ValueError, 'every water-year-type value'):
            read_water_year_type(dss, '/', 'fixed-abundant')

    def test_config_comments_with_trailing_cells_and_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.csv'
            path.write_text('\ufeff# Description,,,,\n"# Comment, with comma",,,,\n'
                            '  # Other comment,,,,\n\n'
                            'Variable,Lookout Point,Hills Creek,,\n'
                            'Abbreviation,LOP,HCR,,\n'
                            'SupportsSalem,TRUE,FALSE,,\nSupportsAlbany,TRUE,FALSE,,\n'
                            'MinConStor,118800,155400,,\nMaxRelease,2700,1800,,\n'
                            'TravelTimeDays,2,2,,\n', encoding='utf-8')
            aliases, flags, floors, limits, travel, selected = read_config(path)
            self.assertEqual(selected, ['Lookout Point'])
            self.assertEqual(floors['Hills Creek'], 155400)
            self.assertEqual(aliases['Lookout Point'], 'LOP')

    def test_prepare_archives_baseline_and_never_writes_live_dss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'forecast'
            scripts = Path(directory) / 'scripts/ExternalPython'
            sv = scripts.parent / 'externalSVs'
            root.mkdir()
            scripts.mkdir(parents=True)
            sv.mkdir()
            live = root / 'forecast.dss'
            live.write_bytes(b'original baseline')
            (sv / 'MinFlowSalemAlbanyConfig.csv').write_text(
                'Variable,Lookout Point,Hills Creek\nAbbreviation,LOP,HCR\n'
                'SupportsSalem,TRUE,FALSE\nSupportsAlbany,TRUE,FALSE\n'
                'MinConStor,118800,155400\nMaxRelease,2700,1800\nTravelTimeDays,2,2\n')
            for gauge in ('Salem', 'Albany'):
                (sv / ('MinFlow' + gauge + '_2008BiOp.csv')).write_text(
                    'WY_type,1-Jan,1-Apr,1-Nov\n1.48,0,1000,0\n')
            import shutil
            shutil.copy2(SCRIPTS / 'MainstemAugmentation.py', scripts / 'MainstemAugmentation.py')
            median = {alias: pd.Series(0.0, index=pd.date_range('2001-04-01', '2001-05-20').strftime('%m-%d'))
                      for alias in ('LOP', 'HCR')}
            with open(scripts / 'median_remaining_by_day.pkl', 'wb') as handle:
                pickle.dump(median, handle)
            dates = pd.date_range('2027-03-30', '2027-05-20')
            writes = []
            class FakeDss:
                def __init__(self, filename, version=None):
                    self.filename = Path(filename)
                    if version == 7:
                        self.filename.write_bytes(b'prepared DSS')
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read_ts(self, path, **kwargs):
                    parameter = path.split('/')[3]
                    value = {'STOR': 500000, 'FLOW-IN': 1000, 'FLOW-OUT': 500,
                             'FLOW-SPEC': 100, 'FLOW': 500, 'STOR-MAF': 1.48}[parameter]
                    units = {'STOR': 'ACRE-FT', 'STOR-MAF': 'MAF'}.get(parameter, 'CFS')
                    return types.SimpleNamespace(values=np.full(len(dates), value), pytimes=dates.to_pydatetime(), units=units)
                def put_ts(self, ts):
                    writes.append((self.filename, ts.pathname))
            modules = {name: types.ModuleType(name) for name in
                       ('pydsstools', 'pydsstools.heclib', 'pydsstools.heclib.dss', 'pydsstools.core')}
            modules['pydsstools.heclib.dss'].HecDss = types.SimpleNamespace(Open=FakeDss)
            modules['pydsstools.core'].TimeSeriesContainer = types.SimpleNamespace
            override = Path(directory) / 'override' / 'MinFlowSalemAlbanyConfig.csv'
            override.parent.mkdir()
            override.write_text((sv / 'MinFlowSalemAlbanyConfig.csv').read_text().replace('2700', '50'))
            args = ['prepare', '--config-csv', str(override), '--forecast-root', str(root), '--scheme', 'test', '--members', '1981',
                    '--season-year', '2027', '--season-end', '2027-05-20']
            with patch.object(preparation, '__file__', str(scripts / 'prepare_rts_augmentation.py')), \
                    patch.object(sys, 'argv', args), patch.dict(sys.modules, modules):
                preparation.main()
            self.assertEqual(live.read_bytes(), b'original baseline')
            self.assertEqual((root / 'augmentation-archives/baseline/forecast.dss').read_bytes(), live.read_bytes())
            manifest = json.loads((root / 'augmentation-archives/test/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'prepared-not-computed')
            self.assertEqual(len(manifest['paths']), 3)
            self.assertEqual(manifest['summary'][0]['maximum_cfs'], 50)
            self.assertIn('2700', (sv / 'MinFlowSalemAlbanyConfig.csv').read_text())
            self.assertIn('50', (root / 'augmentation-archives/test/MinFlowSalemAlbanyConfig.csv').read_text())
            self.assertTrue(all(path != live for path, _ in writes))
            self.assertFalse((root / 'rts-augmentation-active.json').exists())

    def test_load_functions_does_not_execute_standalone_top_level(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'old.py'
            source.write_text("raise RuntimeError('must not execute')\ndef answer():\n    return 42\n")
            self.assertEqual(load_functions(source, {}).answer(), 42)

    def test_missing_daily_input_is_not_filled(self):
        index = pd.to_datetime(['2027-04-01', '2027-04-03'])
        with self.assertRaisesRegex(ValueError, 'Missing/invalid'):
            validate_daily(pd.DataFrame({'flow': [1, 3]}, index=index), index[0], index[-1])

    def test_real_functions_storage_floor_once_and_travel_shift(self):
        aliases = {'Lookout Point': 'LOP', 'Hills Creek': 'HCR'}
        namespace = {'pd': pd, 'np': np, 'datetime': datetime,
                     'timedelta': datetime.timedelta, 'Path': Path,
                     'ALIAS_DICT': aliases, 'MAX_FLOW_DICT': {'Lookout Point': 2700}}
        calc = load_functions(SCRIPTS / 'MainstemAugmentation.py', namespace)
        dates = pd.date_range('2027-03-30', '2027-05-20')
        data = pd.DataFrame(index=dates)
        for alias in ('LOP', 'HCR'):
            data[alias + '_stor'] = 500000
            data[alias + '_inflow'] = 1000
            data[alias + '_outflow'] = 500
            data[alias + '_minflow'] = 100
        data['SLM_flow'] = data['ALB_flow'] = 0
        data['WY_type'] = 1.48
        flags = {'Lookout Point': {'Salem': True, 'Albany': True},
                 'Hills Creek': {'Salem': False, 'Albany': False}}
        floors = {'Lookout Point': 118800, 'Hills Creek': 155400}
        median = {alias: pd.Series(0.0, index=pd.date_range('2001-04-01', '2001-05-20').strftime('%m-%d'))
                  for alias in ('LOP', 'HCR')}
        targets = {gauge: {1.48: {'1-Jan': 0, '1-Apr': 1000, '1-Nov': 0, '31-Dec': 0}}
                   for gauge in ('Salem', 'Albany')}
        captured = {}
        original = calc.create_total_available_volume_pivot_tables
        def capture(short, days, usable, remaining):
            captured['usable'] = usable.loc[2027, 'LOP_stor']
            return original(short, days, usable, remaining)
        calc.create_total_available_volume_pivot_tables = capture
        result = calculate(data, calc, aliases, flags, floors, {'Lookout Point': 2, 'Hills Creek': 2},
                           ['Lookout Point'], 2027, pd.Timestamp('2027-05-20'), 10, median, targets)
        self.assertEqual(captured['usable'], 1000000 - 118800 - 155400)
        self.assertEqual(result.loc['2027-03-30', 'LOP_min_flow_with_aug'], 1500)
        self.assertEqual(result.loc['2027-05-18', 'LOP_min_flow_with_aug'], 1500)
        self.assertEqual(result.loc['2027-05-19', 'LOP_min_flow_with_aug'], 0)
        self.assertTrue(np.isfinite(result['LOP_min_flow_with_aug']).all())

    def test_modified_scheme_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scheme = root / 'augmentation-archives/test'
            baseline = root / 'augmentation-archives/baseline'
            scheme.mkdir(parents=True)
            baseline.mkdir()
            (baseline / 'forecast.dss').write_bytes(b'baseline')
            (baseline / 'manifest.json').write_text(json.dumps({'sha256': sha256(baseline / 'forecast.dss'),
                'run_code': 'C0', 'forecast_root': str(root)}))
            (scheme / 'augmentation.dss').write_bytes(b'scheme')
            manifest = {'status': 'prepared-not-computed', 'forecast_root': str(root),
                        'augmentation_sha256': sha256(scheme / 'augmentation.dss'),
                        'baseline_sha256': sha256(baseline / 'forecast.dss'),
                        'configuration_sha256': {}}
            validate_manifest(root, scheme, manifest)
            (scheme / 'augmentation.dss').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                validate_manifest(root, scheme, manifest)

    def test_standalone_trial_logic_and_rts_switch(self):
        # Execute the actual SV initializer against minimal stand-ins. Standalone
        # NoFlowAug and RTS baseline must return before needing model IO.
        source = SCRIPTS.parent / 'externalSVs/MainstemFlowAugSV.py'
        tree = ast.parse(source.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        initializer = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'initialization')
        import os
        namespace = {'os': os, 'json': json}
        exec(compile(ast.Module(body=[initializer], type_ignores=[]), str(source), 'exec'), namespace)
        from types import SimpleNamespace
        for rts in (False, True):
            values = {'mainstemFlowAugMethod': 'NoFlowAug', 'cwmsCompute': rts,
                      'fileNameSimulation': '/nonexistent/forecast.dss'}
            network = SimpleNamespace(getStateVariable=lambda name: SimpleNamespace(varGet=lambda key: values[key]),
                                      printMessage=lambda message: None)
            instance = SimpleNamespace()
            self.assertTrue(namespace['initialization'](instance, network, None))
            self.assertFalse(instance.computeSV)

    def test_active_rts_c0_reads_current_member_while_standalone_zero_is_omitted(self):
        from types import SimpleNamespace
        import os
        source = SCRIPTS.parent / 'externalSVs/MainstemFlowAugSV.py'
        tree = ast.parse(source.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        initializer = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'initialization')
        class JythonDict(dict):
            def values(self):
                return list(super().values())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'rts-augmentation-active.json').write_text(json.dumps({
                'run_code': 'C0', 'members': [1981], 'scheme': 'test',
                'supporting_reservoirs': ['Lookout Point'], 'scheme_directory': str(root)}))
            values = {'mainstemFlowAugMethod': 'AutoDetect', 'cwmsCompute': True,
                      'fileNameSimulation': str(root / 'forecast.dss'),
                      'mainstemFlowAugReservoirConfigCSV': 'config.csv',
                      'dssOutputFpart': 'C:001981|C0', 'omitTrialsFromFlowAug': '0,2,3',
                      'flowAugRuleTSPathTemplate': '//%RESV_NAME%/FLOW-MIN-EXTERNALFLOWAUG//%TIMESTEP%/%FPART%/',
                      'minFlowTargetCSV_Salem': 'salem.csv', 'minFlowTargetCSV_Albany': 'albany.csv'}
            read_paths = []
            def get(path, *args):
                read_paths.append(path)
                return SimpleNamespace(times=[0])
            dss = SimpleNamespace(get=get, close=lambda: None)
            namespace = {'os': os, 'json': json,
                         'loadReservoirConfig': lambda path: JythonDict({'SupportsSalem':
                             {'Lookout Point': 'TRUE', 'Hills Creek': 'FALSE'}}),
                         'cDSS': SimpleNamespace(openDSSFile=lambda path: dss),
                         'loadMinFlowTable': lambda path: None,
                         'getWYTypeTS': lambda network: None,
                         'getResvConStorage': lambda *args: {'Lookout Point': 100, 'Hills Creek': 50},
                         'MAINSTEM_LOCATIONS': ['Salem', 'Albany'],
                         'RESSIM_JUNCTION_NAMES': {'Salem': 'Willamette_at Salem', 'Albany': 'Willamette_at Albany'}}
            exec(compile(ast.Module(body=[initializer], type_ignores=[]), str(source), 'exec'), namespace)
            network = SimpleNamespace(getStateVariable=lambda name: SimpleNamespace(varGet=lambda key: values[key]),
                printMessage=lambda message: None, makeAbsolutePathFromWatershed=lambda path: path,
                getRssRun=lambda: SimpleNamespace(getTSRecordByPathParts=lambda *args: None))
            current = SimpleNamespace(getTimeSeries=lambda: SimpleNamespace(getTimeSeriesContainer=lambda:
                SimpleNamespace(fullName='//CODE/CODE//1DAY/C:001981|C0/')), localTimeSeriesNew=lambda *args: None)
            instance = SimpleNamespace(initializeLocalTSCs=lambda *args: None)
            self.assertTrue(namespace['initialization'](instance, network, current))
            self.assertTrue(instance.useExternalTS)
            self.assertEqual(read_paths, ['//LOOKOUT POINT/FLOW-MIN-EXTERNALFLOWAUG//1DAY/C:001981|C0/'])
            values['cwmsCompute'] = False
            instance = SimpleNamespace()
            read_paths.clear()
            self.assertTrue(namespace['initialization'](instance, network, current))
            self.assertFalse(instance.computeSV)
            self.assertEqual(read_paths, [])


if __name__ == '__main__':
    unittest.main()
