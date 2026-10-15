"""Coupled diversion/return and withdrawal switch; read at rule initialization."""
import json


def enabled(network):
    path = network.makeAbsolutePathFromWatershed('scripts/diversion-demands.json')
    with open(path, 'r') as stream:
        config = json.load(stream)
    value = config.get('diversion_demands_enabled')
    if not isinstance(value, bool):
        raise ValueError('diversion_demands_enabled must be JSON true or false: ' + path)
    return value
