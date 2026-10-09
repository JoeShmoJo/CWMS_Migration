import os, sys, tempfile, json, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'migration-review', 'baseline-runtime'))
import rts_baseline_runtime as r
root=tempfile.mkdtemp(); scripts=os.path.join(root,'scripts'); legacy=os.path.join(scripts,'_rts_baseline_originals','externalRules');os.makedirs(legacy)
path=os.path.join(legacy,'DraftToRC.py')
with open(path,'w') as f:f.write('DAYS_LOOKAHEAD=3\ndef initRuleScript(rule, network):\n return True\ndef runRuleScript(rule, network, step):\n return DAYS_LOOKAHEAD\n')
class Store:
 def __init__(self):self.values={}
 def varPut(self,k,v):self.values[k]=v
 def varGet(self,k):return self.values[k]
class Run:
 def getDSSOutputFile(self):return os.path.join(root,'EnsembleRuns','1981','forecast.dss')
 def getOutputFPart(self):return 'C:001981|C0'
class Network:
 def getRssRun(self):return Run()
 def makeAbsolutePathFromWatershed(self,p):return os.path.join(root,p)
 def getStateVariable(self,k):return Store()
 def printMessage(self,s):pass
n=Network();old=Store();r.initialize_rule('DraftToRC',old,n);assert r.run_rule(old,n,None)==3
stage=os.path.join(root,'baseline-configurations','sets','test');os.makedirs(stage)
data={'schema_version':1,'name':'test','rules':{'draft_to_rc':{'settings':{'days_lookahead':7,'active':True}},'irrm':{'settings':{'active':{},'target_elevation_ft':{}}}},'table_paths':{},'table_sha256':{},'script_sha256':{'DraftToRC':r.digest(path)}}
with open(os.path.join(stage,'resolved.json'),'w') as f:json.dump(data,f)
with open(os.path.join(root,'rts-baseline-config-active.json'),'w') as f:json.dump({'id':'test','directory':'baseline-configurations/sets/test','resolved_sha256':r.digest(os.path.join(stage,'resolved.json'))},f)
new=Store();r.initialize_rule('DraftToRC',new,n);assert r.run_rule(new,n,None)==7;assert r.run_rule(old,n,None)==3
assert len(os.listdir(os.path.join(stage,'initialization-receipts')))==1
import shutil
shutil.rmtree(root)
print('Jython 2.7.3: isolated initialization, settings reload, and receipt passed')
