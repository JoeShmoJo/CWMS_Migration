

# RTS initialization adapter; original runRuleScript above remains unchanged.
_rts_baseline_direct = True
_rts_original_initRuleScript = initRuleScript

def initRuleScript(currentRule, network):
    import sys
    scripts = str(network.makeAbsolutePathFromWatershed("scripts"))
    if scripts not in sys.path:
        sys.path.append(scripts)
    from rts_baseline_runtime import initialize_rule
    return initialize_rule("FIRO_SPACE", currentRule, network, globals())
