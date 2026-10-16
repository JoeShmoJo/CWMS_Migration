import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'migration-review/ExternalPython'))
import standalone_model_check as checks


class ModelCheckLaunchTests(unittest.TestCase):
    def test_exact_ensemble_member_and_por_output_selection_without_shared_config_edits(self):
        for mode,member,fpart in [('ensemble',2001,'C:002001|CON_SEASON0'),('por',None,'CON_SEASON0')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                watershed=Path(temporary);root=watershed/'rss/Simulation';root.mkdir(parents=True)
                source=root/'simulation.dss';source.write_bytes(b'original')
                folder=watershed/'scripts/model_check';folder.mkdir(parents=True);(folder/'extract_dss.py').write_text('# kept')
                applied=root/'baseline-configurations/sets/test';(applied/'tables').mkdir(parents=True)
                table=applied/'tables/firo.csv';table.write_text('Month,Day\n')
                resolved=applied/'resolved.json';resolved.write_text(json.dumps({'table_paths':{'firoSpaceConfigCSV':'tables/firo.csv'}}))
                (root/'standalone-baseline-config-active.json').write_text(json.dumps({'id':'test','directory':'baseline-configurations/sets/test',
                    'model_alternative':'Con_Season','resolved_sha256':checks.digest_file(resolved)}))
                paths=['//Lookout Point-Pool/ELEV//1DAY/'+code+'/' for code in ('CON_SEASON0','C:002000|CON_SEASON0','C:002001|CON_SEASON0')]
                class DSS:
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def getPathnameList(self,pattern):return paths
                extractor=SimpleNamespace();checker=SimpleNamespace(configPath=lambda root,alt,key,default:default)
                called={}
                def extract(filename,alternative):
                    called['fpart']=extractor.fPartFor(paths,alternative)
                    target=Path(extractor.OUTPUT_ROOT)/'extracted';target.mkdir()
                    return str(target)
                def check(directory):
                    called['root']=checker.CONFIG_ROOT
                    called['table']=checker.configPath(str(watershed),{},'firoSpaceConfigCSV','wrong.csv')
                    (Path(directory)/'report.html').write_text('report')
                extractor.main=extract;checker.main=check
                fake=SimpleNamespace(HecDss=SimpleNamespace(Open=lambda filename:DSS()))
                with patch.dict(sys.modules,{'pydsstools.heclib.dss':fake}),patch.object(checks,'load',side_effect=[extractor,checker]):
                    report=checks.run(root,'Con_Season','CON_SEASON0',mode,member)
                self.assertEqual(called['fpart'],fpart)
                self.assertEqual(called['root'],str(watershed))
                self.assertEqual(called['table'],str(table))
                self.assertTrue(report.is_file())
                context=json.loads((report.parent.parent/'check-context.json').read_text())
                self.assertEqual(context['status'],'complete')
                self.assertEqual(context['member'],member)
                self.assertEqual(source.read_bytes(),b'original')

    def test_real_por_catalog_automatic_target(self):
        import csv
        catalog=Path(__file__).resolve().parents[1]/'model_check/output/Flood_96_3hour_catalog.csv'
        with catalog.open() as stream:paths=[row['example_path'] for row in csv.DictReader(stream)]
        self.assertEqual(checks.select_output(paths,'Temp3Hour','por'),'Temp3Hour-0')
        with self.assertRaisesRegex(ValueError,'No unique output'):
            checks.select_output(paths,'OtherAlt','por')

    def test_dedicated_por_page_has_no_member_or_archive_choices(self):
        from standalone_results import CHECK_PAGE
        page=CHECK_PAGE.replace('__MEMBER__','')
        self.assertNotIn('id="member"',page)
        self.assertNotIn('id="output"',page)
        self.assertNotIn('id="kind"',page)
        self.assertIn('Report name (optional)',page)

    def test_legacy_system_exit_is_returned_to_browser_as_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            request=Path(temporary)/'request.json';response=Path(temporary)/'response.json'
            request.write_text('{}')
            with patch.object(checks,'run',side_effect=SystemExit('needs reservoirs.csv and limits.csv')),patch('traceback.print_exc'):
                self.assertEqual(checks.run_request(request,response),1)
            self.assertIn('needs reservoirs.csv',json.loads(response.read_text())['error'])

    def test_native_process_failure_does_not_escape_as_lost_connection(self):
        import standalone_results
        with patch('subprocess.run',return_value=SimpleNamespace(returncode=3221225477)):
            with self.assertRaisesRegex(ValueError,'possible native reader failure'):
                standalone_results.model_check_job('/unused','Con_Season','ensemble',1985)

    def test_ensemble_requires_single_member_before_reading_data(self):
        with self.assertRaisesRegex(ValueError,'single ensemble member'):
            checks.run(Path('/unused/rss/Simulation'),'Con_Season','CON_SEASON0','ensemble')

if __name__=='__main__':unittest.main()
