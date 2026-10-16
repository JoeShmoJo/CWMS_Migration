"""Jython-only smoke check; argument is the generated standalone runtime path."""
import sys, os, tempfile, shutil, json
sys.path.insert(0,os.path.dirname(os.path.abspath(sys.argv[1])))
import standalone_baseline_runtime as runtime
root=tempfile.mkdtemp()
try:
    simulation=os.path.join(root,'rss','Test')
    scripts=os.path.join(root,'scripts','_standalone_baseline_originals','externalRules')
    os.makedirs(simulation);os.makedirs(scripts)
    source=os.path.join(scripts,'DraftToRC.py')
    with open(source,'w') as handle:handle.write('DAYS_LOOKAHEAD=3\n')
    class Store(object):
        def varPut(self,key,value):pass
    class Run(object):
        def getDSSOutputFile(self):return os.path.join(simulation,'simulation.dss')
        def getOutputFPart(self):return 'CON_SEASON0'
    class Alternative(object):
        name='Con_Season'
        def getName(self):return ':'+self.name
    alternative=Alternative()
    class Network(object):
        def getRssRun(self):return Run()
        def getAlternative(self):return alternative
        def makeAbsolutePathFromWatershed(self,path):return os.path.join(root,path)
        def getStateVariable(self,name):return Store()
        def printMessage(self,message):pass
    network=Network()
    namespace={'DAYS_LOOKAHEAD':3,'_rts_original_initRuleScript':lambda rule,network:True}
    for identifier,days in [('first',7),('second',5)]:
        relative=os.path.join('baseline-configurations','sets',identifier)
        stage=os.path.join(simulation,relative);os.makedirs(stage)
        data={'schema_version':1,'name':identifier,'rules':{
            'draft_to_rc':{'settings':{'active':True,'days_lookahead':days}},
            'irrm':{'settings':{'active':{},'target_elevation_ft':{}}}},
            'table_paths':{},'table_sha256':{},'script_sha256':{'DraftToRC':runtime.digest(source)}}
        resolved=os.path.join(stage,'resolved.json')
        with open(resolved,'w') as handle:json.dump(data,handle)
        with open(os.path.join(simulation,'standalone-baseline-config-active.json'),'w') as handle:
            json.dump({'id':identifier,'model_alternative':'Con_Season','directory':relative,'resolved_sha256':runtime.digest(resolved)},handle)
        assert runtime.initialize_rule('DraftToRC',Store(),network,namespace)
        assert namespace['DAYS_LOOKAHEAD']==days
        receipts=os.listdir(os.path.join(stage,'initialization-receipts'))
        assert len(receipts)==1
        with open(os.path.join(stage,'initialization-receipts',receipts[0])) as handle:
            assert json.load(handle)['member'] is None
    alternative.name='Other'
    assert runtime.initialize_rule('DraftToRC',Store(),network,namespace)
    assert namespace['DAYS_LOOKAHEAD']==3
    print('PASS: Jython successive applies, non-ensemble receipts, caller alternative isolation and defaults restoration')
finally:shutil.rmtree(root)
