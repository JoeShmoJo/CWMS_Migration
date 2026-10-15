"""Create a separate watershed with a coupled diversion/withdrawal switch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('timing_preparation', HERE.parent/'config-timing/prepare_config_timing.py')
rebasing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rebasing)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unrecognized script version; expected exactly one: ' + old)
    return text.replace(old, new, 1)


def patch(name, text):
    if 'DIVERSION_DEMAND_SWITCH' in text or 'CONFIG_READ_TIMING_DIAGNOSTIC' in text or '_rts_original_' in text:
        raise ValueError('Use the working standalone watershed, without timing instrumentation or RTS adapters')
    text = replace_once(text, 'from hec.rss.model import OpValue',
                        '# DIVERSION_DEMAND_SWITCH: sandbox only\nfrom diversion_demand_config import enabled as _demands_enabled\nfrom hec.rss.model import OpValue')
    if name == 'DiversionFromCSV':
        text = replace_once(text, '    elementName = _getElementName(currentRule)', '''    demandEnabled = _demands_enabled(network)
    currentRule.varPut("diversionDemandsEnabled", demandEnabled)
    # Always replace prior compute state, including when switching OFF.
    currentRule.varPut("dayTable", [None] * (DAYS_IN_YEAR + 1))
    if not demandEnabled:
        return
    elementName = _getElementName(currentRule)''')
        text = replace_once(text, '    opValue = OpValue()', '''    opValue = OpValue()
    if not currentRule.varGet("diversionDemandsEnabled"):
        opValue.init(OpRule.RULETYPE_SPEC, 0.0)
        return opValue''')
    else:
        text = replace_once(text, '    withdrawalTable = _columnTable(withdrawalPath, resvName, "withdrawal")', '''    demandEnabled = _demands_enabled(network)
    currentRule.varPut("diversionDemandsEnabled", demandEnabled)
    if demandEnabled:
        withdrawalTable = _columnTable(withdrawalPath, resvName, "withdrawal")
    else:
        withdrawalTable = [None] * (DAYS_IN_YEAR + 1)''')
    compile(text, name+'.py', 'exec')
    return text


def prepare(source, destination):
    source, destination = source.resolve(), destination.resolve()
    if destination.exists() or source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Destination must be new and outside the source watershed')
    if not (source/'scripts').is_dir():
        raise ValueError('Watershed scripts directory missing')
    for filename in ('diversion-demands.json', 'diversion_demand_config.py'):
        if (source/'scripts'/filename).exists():
            raise ValueError('Source already has diversion switch files')
    changes = []
    for name in ('DiversionFromCSV', 'MinFlowPlusWithdrawal'):
        relative = Path('scripts/externalRules')/(name+'.py')
        raw = (source/relative).read_bytes()
        patch(name, raw.decode('utf-8-sig'))  # Validate both before copying anything.
        changes.append((name, relative, hashlib.sha256(raw).hexdigest()))
    shutil.copytree(source, destination)
    rebased = rebasing.rewrite_references(destination, source)
    for name, relative, digest in changes:
        target = destination/relative
        target.write_text(patch(name, target.read_text(encoding='utf-8-sig')), encoding='utf-8')
        target.with_name(target.stem+'$py.class').unlink(missing_ok=True)
    shutil.copy2(HERE/'diversion_demand_config.py', destination/'scripts/diversion_demand_config.py')
    (destination/'scripts/diversion-demands.json').write_text(json.dumps({'diversion_demands_enabled': True}, indent=2)+'\n')
    marker = {'sandbox_only': True, 'source': str(source), 'rebased_files': rebased,
              'original_scripts': {str(relative): digest for _, relative, digest in changes}}
    (destination/'diversion-switch-sandbox.json').write_text(json.dumps(marker, indent=2))
    print('PREPARED ONLY:', destination)
    print('Configuration:', destination/'scripts/diversion-demands.json')
    print('Default ON preserves existing demands. Set false to disable diversions, returns, and added withdrawal releases.')
    print('Use the working V2 application to open this copied watershed. No compute started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    prepare(args.watershed, args.destination)
