"""Jython 2.7 runtime adapter. No writes to standalone configuration files."""
import copy
import hashlib
try:
    import imp
except ImportError:
    imp = None
import json
import os
import sys
import uuid

RULE_KEYS = {'DeepDrawdown': 'deep_drawdown', 'SpringSpill': 'spring_spill',
    'NoDraft': 'no_draft', 'SecondaryFloodDraftLimit': 'secondary_flood_draft',
    'FIRO_SPACE': 'firo_space', 'MinFlowPlusWithdrawal': 'minimum_flow_withdrawal',
    'DiversionFromCSV': 'diversions', 'IRRM': 'irrm', 'DraftToRC': 'draft_to_rc',
    'FillLOPfirst': 'fill_lop_first', 'HCR_LOP_Balance': 'hcr_lop_balance'}
CONSTANTS = {'target_buffer_ft':'TARGET_BUFFER', 'glide_days':'GLIDE_DAYS',
    'mode':'MODE', 'mode_by_reservoir':'MODE_BY_RESERVOIR', 'deadband_ft':'DEADBAND_FT',
    'interpolate_gaps_up_to_days':'INTERPOLATE_GAPS_UP_TO_DAYS',
    'require_reservoir_in_config':'REQUIRE_RESERVOIR_IN_CONFIG',
    'downstream_refill_days':'DOWNSTREAM_REFILL_DAYS', 'days_lookahead':'DAYS_LOOKAHEAD',
    'buffer_ac_ft':'BUFFER', 'high_flow_cfs':'HIGH_FLOW', 'low_flow_cfs':'LOW_FLOW',
    'start_month':'START_MONTH', 'start_day':'START_DAY', 'end_month':'END_MONTH', 'end_day':'END_DAY',
    'spillway_elevation_ft':'SPILLWAY_ELEV', 'minimum_conservation_elevation_ft':'minConElev',
    'maximum_conservation_elevation_ft':'maxConElev', 'highest_minimum_flow_cfs':'HIGHEST_MIN_FLOW',
    'release_above_inflow_cfs':'RELEASE_ABOVE_INFLOW', 'minimum_flow_low_limit_cfs':'MIN_FLOW_LOW_LIMIT',
    'lop_drawdown_rule_name':'LOP_DRAWDOWN_RULE_NAME'}
_CACHE = {}


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def active(network):
    output = str(network.getRssRun().getDSSOutputFile())
    output = network.makeAbsolutePathFromWatershed(output)
    directory = os.path.abspath(os.path.dirname(str(output)))
    # Ensemble output may be in EnsembleRuns/member. Select by this compute's
    # output path, never by the selected GUI forecast or a watershed global.
    for ignored in range(5):
        marker = os.path.join(directory, 'rts-baseline-config-active.json')
        if os.path.isfile(marker):
            with open(marker) as handle:
                pointer = json.load(handle)
            source = os.path.abspath(os.path.join(directory, pointer['directory']))
            allowed = os.path.join(directory, 'baseline-configurations', 'sets') + os.sep
            if not source.startswith(allowed):
                raise RuntimeError('Invalid RTS baseline configuration path')
            filename = os.path.join(source, 'resolved.json')
            cache_key = (filename, pointer['resolved_sha256'])
            if cache_key not in _CACHE:
                if digest(filename) != pointer['resolved_sha256']:
                    raise RuntimeError('RTS baseline configuration checksum mismatch')
                with open(filename) as handle:
                    data = json.load(handle)
                if data['schema_version'] != 1:
                    raise RuntimeError('Unsupported RTS baseline configuration')
                if len(_CACHE) >= 16:
                    _CACHE.clear()
                _CACHE[cache_key] = data
            data = _CACHE[cache_key]
            # Generated tables are small; verify rather than silently use edits
            # made after Apply. Applying a new set creates a new immutable copy.
            for relative, expected in data['table_sha256'].items():
                if digest(os.path.join(source, relative)) != expected:
                    raise RuntimeError('Applied baseline table changed; reapply configuration: ' + relative)
            return source, data, pointer
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return None


def alternative_overrides(network):
    found = active(network)
    if found is None:
        return {}
    source, data, pointer = found
    result = dict((key, os.path.join(source, relative)) for key, relative in data['table_paths'].items())
    result['draftToRCActive'] = copy.deepcopy(data['rules']['draft_to_rc']['settings']['active'])
    result['irrmActive'] = copy.deepcopy(data['rules']['irrm']['settings']['active'])
    result['irrmTargetElevs'] = copy.deepcopy(data['rules']['irrm']['settings']['target_elevation_ft'])
    network.printMessage('RTS baseline configuration: %s [%s]' % (data['name'], pointer['id']))
    return result


def initialize_rule(module_name, rule, network):
    scripts = str(network.makeAbsolutePathFromWatershed('scripts'))
    path = os.path.join(scripts, '_rts_baseline_originals', 'externalRules', module_name + '.py')
    module_id = '_rts_rule_' + module_name + '_' + uuid.uuid4().hex
    if imp is not None:
        module = imp.load_source(module_id, path)
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_id, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    sys.modules.pop(module_id, None)
    found = active(network)
    if found:
        source, data, pointer = found
        if digest(path) != data['script_sha256'][module_name]:
            raise RuntimeError('Rule script changed since Apply; reapply baseline configuration: ' + module_name)
        settings = data['rules'][RULE_KEYS[module_name]]['settings']
        # Isolated module instance per rule: do not mutate shared globals across
        # reservoirs, forecasts or ensemble members.
        for key, constant in CONSTANTS.items():
            if key in settings:
                setattr(module, constant, copy.deepcopy(settings[key]))
        sv = network.getStateVariable('Alternative_Setup')
        for key, value in alternative_overrides(network).items():
            sv.varPut(key, value)
        # These readers can run before Alternative_Setup initialization.
        if hasattr(module, '_resolveConfigPath'):
            paths = dict((key, os.path.join(source, relative)) for key, relative in data['table_paths'].items())
            if module_name == 'FIRO_SPACE':
                module._resolveConfigPath = lambda unused: paths['firoSpaceConfigCSV']
            else:
                module._resolveConfigPath = lambda unused, key, default: paths.get(key, network.makeAbsolutePathFromWatershed(default))
        network.printMessage('RTS baseline init: %s [%s]' % (module_name, pointer['id']))
    rule.varPut('_rts_baseline_module', module)
    outcome = module.initRuleScript(rule, network)
    if found and outcome:
        source, data, pointer = found
        import re
        match = re.search(r'C:(\d{6})\|', str(network.getRssRun().getOutputFPart()))
        if not match:
            raise RuntimeError('Cannot identify ensemble member for baseline initialization receipt')
        directory = os.path.join(source, 'initialization-receipts')
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError:
                if not os.path.isdir(directory):
                    raise
        # Unique immutable receipts avoid concurrent reservoir writes colliding.
        with open(os.path.join(directory, uuid.uuid4().hex + '.json'), 'w') as handle:
            json.dump({'configuration_id': pointer['id'], 'member': int(match.group(1)),
                       'module': module_name, 'resolved_sha256': pointer['resolved_sha256']}, handle)
    return outcome


def run_rule(rule, network, timestep):
    return rule.varGet('_rts_baseline_module').runRuleScript(rule, network, timestep)
