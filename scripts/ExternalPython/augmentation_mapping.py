"""RTS reservoir release requirements used by the two-step calculation.

MinFlowPlusWithdrawal transforms the Foster target into Green Peter's release
requirement using Foster's rule-curve fill rate and local inflow. Read that
saved Green Peter result; the Foster target itself is not a GPR release.
"""
MINIMUM_LOCATIONS = {
    'BLU': 'BLUE RIVER', 'COT': 'COTTAGE GROVE', 'CGR': 'COUGAR',
    'DET': 'DETROIT', 'DOR': 'DORENA', 'FAL': 'FALL CREEK',
    'FRN': 'FERN RIDGE', 'HCR': 'HILLS CREEK', 'LOP': 'LOOKOUT POINT',
    'GPR': 'GREEN PETER',
}


def minimum_path(alias, member, run_code):
    return '//{}-COMBINED MIN TRIB/FLOW-SPEC//1DAY/C:{:06d}|{}/'.format(
        MINIMUM_LOCATIONS[alias], member, run_code)
