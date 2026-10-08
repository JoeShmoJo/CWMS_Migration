"""RTS local-minimum inputs corresponding to the legacy two-step calculation.

Green Peter intentionally uses Foster's requirement, matching the legacy GPR
input. Do not substitute Green Peter's own requirement without model review.
"""
MINIMUM_LOCATIONS = {
    'BLU': 'BLUE RIVER', 'COT': 'COTTAGE GROVE', 'CGR': 'COUGAR',
    'DET': 'DETROIT', 'DOR': 'DORENA', 'FAL': 'FALL CREEK',
    'FRN': 'FERN RIDGE', 'HCR': 'HILLS CREEK', 'LOP': 'LOOKOUT POINT',
    'GPR': 'FOSTER',
}


def minimum_path(alias, member, run_code):
    return '//{}-COMBINED MIN TRIB/FLOW-SPEC//1DAY/C:{:06d}|{}/'.format(
        MINIMUM_LOCATIONS[alias], member, run_code)
