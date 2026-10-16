"""Common standalone/RTS synthetic member IDs, separate from historical years."""
FORECAST_PERCENTILES = ((3000, 0.25), (3001, 0.50), (3002, 0.75))
STANDALONE_PERCENTILES = FORECAST_PERCENTILES
FORECAST_OSI_MEMBER = 3003
STANDALONE_OSI_MEMBER = FORECAST_OSI_MEMBER


def add_percentile_members(frame, forecast=False):
    assignments = FORECAST_PERCENTILES if forecast else STANDALONE_PERCENTILES
    collisions = set(frame.columns).intersection(member for member, _ in assignments)
    if collisions:
        raise ValueError('Synthetic member IDs collide with RFC members: {}'.format(sorted(collisions)))
    result = frame.copy()
    for member, quantile in assignments:
        result[member] = frame.quantile(quantile, axis=1, interpolation='linear')
    return result


def computed_standalone_members(filename, alternative):
    """Use actual baseline output members, including the common synthetic IDs."""
    import re
    from pydsstools.heclib.dss import HecDss
    suffix=alternative.replace(' ','-').ljust(10,'-')+'0'
    members=set()
    with HecDss.Open(str(filename)) as dss:
        for path in dss.getPathnameList('/*/*/*/*/*/*/'):
            parts=str(path).split('/')
            if len(parts)!=8 or not parts[2].upper().endswith('-POOL') or parts[3].upper()!='FLOW-OUT':continue
            match=re.fullmatch(r'C:(\d{6})\|'+re.escape(suffix),parts[6],re.I)
            if match:members.add(int(match[1]))
    if not members:raise ValueError('No computed baseline pool outflows for '+suffix)
    return sorted(members)
