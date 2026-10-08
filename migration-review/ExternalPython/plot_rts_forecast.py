"""Plot actual RTS ensemble outputs without standalone naming assumptions."""
import argparse
import csv
from datetime import datetime
from pathlib import Path
import re
import tempfile

CONTROL_POINTS = ('ALBO', 'NBGO', 'SLMO', 'WTLO', 'MEHO', 'JFFO', 'MNRO',
                  'HARO', 'VIDO', 'EUGO', 'GOSO', 'JASO')


def parse_members(text):
    members = set()
    for item in text.split(','):
        item = item.strip()
        if not item:
            continue
        if '-' in item:
            first, last = map(int, item.split('-'))
            if first > last:
                raise ValueError('Descending member range: ' + item)
            members.update(range(first, last + 1))
        else:
            members.add(int(item))
    return members


def target_record(parts):
    location, parameter = parts[2].upper(), parts[3].upper()
    if location.endswith('-POOL') and parameter in ('ELEV', 'ELEVATION', 'FLOW-OUT'):
        return True
    if parameter == 'FLOW':
        return (location.startswith(CONTROL_POINTS)
                or location.startswith('WILLAMETTE_AT ')
                or location.startswith('WILLAMETTE AT '))
    return False


def output_groups(paths, run_code, members):
    groups = {}
    for path in paths:
        parts = path.split('/')
        if len(parts) != 8 or not target_record(parts):
            continue
        match = re.fullmatch(r'C:(\d{6})\|(.+)', parts[6])
        if not match or match.group(2).upper() != run_code.upper():
            continue
        member = int(match.group(1))
        if member not in members:
            continue
        key = (parts[1], parts[2], parts[3], parts[5])
        # Read the whole logical series, rather than assuming calendar-year blocks.
        parts[4] = ''
        groups.setdefault(key, {})[member] = '/'.join(parts)
    return groups


def clean_series(record):
    import numpy as np
    import pandas as pd
    values = np.ma.asarray(record.values, dtype=float).filled(np.nan)
    times = pd.DatetimeIndex(pd.to_datetime(record.pytimes))
    if len(values) != len(times):
        raise ValueError('DSS timestamp/value length mismatch')
    # Both DSS undefined sentinels and nonfinite values are absent observations.
    values[~np.isfinite(values) | (np.abs(values) > 1e30)] = np.nan
    series = pd.Series(values, index=times)
    series = series[~series.index.duplicated(keep='last')].sort_index()
    return series


def quantiles(frame):
    import pandas as pd
    q = pd.DataFrame(index=frame.index)
    for value in (0.05, 0.25, 0.50, 0.75, 0.95):
        q[value] = frame.quantile(value, axis=1)
    q['member_count'] = frame.notna().sum(axis=1)
    return q


def unit_key(units):
    value = str(units).strip().upper()
    return 'FT' if value in ('FT', 'FEET', 'FOOT') else value


def load_rule_curve(dss, location, units, begin, end, csv_path):
    import pandas as pd
    rule_path = '//{}/ELEV//1DAY/RULE CURVE/'.format(location[:-5])
    try:
        record = dss.read_ts(rule_path, trim_missing=True)
        if unit_key(record.units) != unit_key(units):
            raise ValueError('Rule curve/output units differ')
        curve = clean_series(record)
        curve = curve[(curve.index >= begin) & (curve.index <= end)]
        if curve.dropna().empty:
            raise ValueError('No valid DSS rule-curve values in plot window')
        return curve, 'Rule curve (DSS)'
    except Exception as exc:
        print('DSS RULE CURVE WARNING:', rule_path, exc, flush=True)
    if unit_key(units) != 'FT':
        raise ValueError('Supplied CSV rule curves are in feet; plot units are ' + str(units))
    from write_rule_curves import annual_table, expand
    dates, values = expand(annual_table(csv_path), begin.to_pydatetime(), end.to_pydatetime())
    curve = pd.Series(values[location[:-5].upper()], index=dates)
    curve = curve[(curve.index >= begin) & (curve.index <= end)]
    print('RULE CURVE: using supplied annual CSV schedule for', location, flush=True)
    return curve, 'Rule curve (CSV schedule)'


def make_figure(frame, title, units, rule_curve=None, rule_label='Rule curve'):
    import plotly.graph_objects as go
    q = quantiles(frame)
    fig = go.Figure()
    for low, high, color, label in [(0.05, 0.95, 'rgba(90,110,150,0.15)', '5–95%'),
                                    (0.25, 0.75, 'rgba(90,110,150,0.30)', '25–75%')]:
        fig.add_trace(go.Scatter(x=q.index, y=q[low], mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=q.index, y=q[high], mode='lines', line=dict(width=0), fill='tonexty', fillcolor=color, name=label))
    for member in frame.columns:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[member], mode='lines',
                                line=dict(width=1), opacity=0.35, name=str(member),
                                connectgaps=False))
    fig.add_trace(go.Scatter(x=q.index, y=q[0.50], mode='lines', line=dict(color='black', width=2),
                            customdata=q['member_count'], name='Median',
                            hovertemplate='%{x}<br>Median: %{y:.2f}<br>Members: %{customdata}<extra></extra>'))
    if rule_curve is not None:
        fig.add_trace(go.Scatter(x=rule_curve.index, y=rule_curve, mode='lines',
                                line=dict(color='green', width=2, dash='dash'), name=rule_label, connectgaps=False))
    fig.update_layout(title=title, xaxis_title='Forecast local date/time', yaxis_title=units,
                      template='plotly_white', hovermode='closest')
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    parser.add_argument('--run-code', default='C0', help='Exact output suffix, e.g. C0')
    parser.add_argument('--members', default='1981-2025', help='Members included in output bands')
    parser.add_argument('--start', help='Optional local ISO date/time limit')
    parser.add_argument('--end', help='Optional local ISO date/time limit')
    parser.add_argument('--location', help='Optional exact DSS B-part, e.g. Detroit-Pool')
    args = parser.parse_args()
    root = Path(args.forecast_root)
    source = root / 'forecast.dss'
    if not source.is_file():
        raise FileNotFoundError(source)
    members = parse_members(args.members)
    if not members:
        raise ValueError('No requested members')
    import pandas as pd
    from pydsstools.heclib.dss import HecDss
    import plotly.offline
    import plotly.graph_objects
    if args.start and args.end and pd.Timestamp(args.start) > pd.Timestamp(args.end):
        raise ValueError('Start must precede end')
    output_root = root / 'output_plots'
    output_root.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='rts-ensemble-' + datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=str(output_root)))
    (output / '_plotly.min.js').write_text(plotly.offline.get_plotlyjs(), encoding='utf-8')
    audit, links = [], []
    with HecDss.Open(str(source)) as dss:
        groups = output_groups(dss.getPathnameList('/*/*/*/*/*/*/'), args.run_code, members)
        if args.location:
            groups = {key: value for key, value in groups.items() if key[1].upper() == args.location.upper()}
        if not groups:
            raise RuntimeError('No matching reservoir/control-point outputs for {} and members {}'.format(args.run_code, args.members))
        for number, (key, paths) in enumerate(sorted(groups.items()), 1):
            series = {}
            units_seen = set()
            for member, pathname in sorted(paths.items()):
                row = dict(location=key[1], parameter=key[2], member=member, path=pathname)
                try:
                    record = dss.read_ts(pathname, trim_missing=True)
                    values = clean_series(record)
                    if args.start:
                        values = values[values.index >= pd.Timestamp(args.start)]
                    if args.end:
                        values = values[values.index <= pd.Timestamp(args.end)]
                    valid_values = values.dropna()
                    if valid_values.empty:
                        raise ValueError('No valid values in requested window')
                    units = str(record.units).strip()
                    units_seen.add(unit_key(units))
                    series[member] = values
                    row.update(status='read', samples=len(valid_values), first=str(valid_values.index[0]), last=str(valid_values.index[-1]), units=units)
                except Exception as exc:
                    row.update(status='failed', error=str(exc))
                    print('READ WARNING:', pathname, exc, flush=True)
                audit.append(row)
            if not series:
                print('No readable results:', key, flush=True)
                continue
            if len(units_seen) != 1:
                raise ValueError('Cannot combine different units for {}: {}'.format(key, units_seen))
            frame = pd.concat(series, axis=1).sort_index()
            title = '{} — {} — {} ({} members read)'.format(key[1], key[2], args.run_code, len(series))
            filename = '{:02d}_{}.html'.format(number, re.sub(r'[^A-Za-z0-9_-]+', '_', key[1] + '_' + key[2] + '_' + key[3]))
            rule_curve = None
            rule_label = 'Rule curve'
            if key[1].upper().endswith('-POOL') and key[2].upper() in ('ELEV', 'ELEVATION'):
                try:
                    rule_curve, rule_label = load_rule_curve(dss, key[1], next(iter(units_seen)), frame.index.min(), frame.index.max(),
                                                            Path(__file__).with_name('CON_SEASON_RULE_CURVES.csv'))
                except Exception as exc:
                    print('RULE CURVE WARNING:', key[1], exc, flush=True)
            make_figure(frame, title, next(iter(units_seen)), rule_curve, rule_label).write_html(output / filename, include_plotlyjs='_plotly.min.js')
            frame.to_csv(output / filename.replace('.html', '_series.csv'))
            quantiles(frame).to_csv(output / filename.replace('.html', '_bands.csv'))
            links.append((filename, title))
            missing = sorted(members - set(series))
            print('PLOT:', title, 'Missing members:', missing, flush=True)
    fields = ['location', 'parameter', 'member', 'path', 'status', 'samples', 'first', 'last', 'units', 'error']
    with (output / 'read-report.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit)
    if not links:
        raise RuntimeError('No plots produced; see ' + str(output / 'read-report.csv'))
    import html
    body = '<html><head><meta charset="utf-8"><title>RTS ensemble plots</title></head><body><h1>RTS ensemble plots</h1>'
    body += '<p>Output quantiles across readable members; these are not model outputs from daily percentile inflow traces. Missing members are reported in read-report.csv. Time-varying sample counts are in each bands CSV and median hover.</p><ul>'
    body += ''.join('<li><a href="{}">{}</a></li>'.format(html.escape(name), html.escape(title)) for name, title in links)
    body += '</ul></body></html>'
    (output / 'index.html').write_text(body, encoding='utf-8')
    print('Plots created:', len(links), flush=True)
    print('Open:', output / 'index.html', flush=True)


if __name__ == '__main__':
    main()
