"""Separate synthetic traces from historical RFC year identifiers."""
FORECAST_PERCENTILES = ((3000, 0.25), (3001, 0.50), (3002, 0.75))
STANDALONE_PERCENTILES = ((2026, 0.25), (2027, 0.50), (2028, 0.75))
FORECAST_OSI_MEMBER = 3003


def add_percentile_members(frame, forecast=False):
    assignments = FORECAST_PERCENTILES if forecast else STANDALONE_PERCENTILES
    collisions = set(frame.columns).intersection(member for member, _ in assignments)
    if collisions:
        raise ValueError('Synthetic member IDs collide with RFC members: {}'.format(sorted(collisions)))
    result = frame.copy()
    for member, quantile in assignments:
        result[member] = frame.quantile(quantile, axis=1, interpolation='linear')
    return result
