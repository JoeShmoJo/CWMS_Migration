# RTS adapter; maintained standalone implementation is installed separately.
import sys

def initRuleScript(currentRule, network):
    scripts = str(network.makeAbsolutePathFromWatershed("scripts"))
    if scripts not in sys.path:
        sys.path.append(scripts)
    from rts_baseline_runtime import initialize_rule
    return initialize_rule("DraftToRC", currentRule, network)

def runRuleScript(currentRule, network, currentRuntimestep):
    from rts_baseline_runtime import run_rule
    return run_rule(currentRule, network, currentRuntimestep)
