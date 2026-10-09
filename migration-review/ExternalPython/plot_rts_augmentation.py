"""Archive current RTS results and compare them with a scheme's fixed baseline.

Capturing records does not certify that RTS reported a successful compute.
Historical comparisons use paired members; synthetic traces stay separate.
"""
import argparse
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd

from plot_rts_forecast import (parse_members, output_groups, clean_series, quantiles,
                               unit_key, index_page, load_rule_curve, SYNTHETIC_LABELS)
from load_rts_augmentation import validate_manifest
from prepare_rts_augmentation import sha256, read_config
from baseline_versions import (baseline_directory, baseline_identity, registry, event,
                               result_directory, write_archive_index)


def capture(root, scheme, manifest):
    active = json.loads((root / 'rts-augmentation-active.json').read_text())
    if active['scheme'] != manifest['scheme'] or active['augmentation_sha256'] != manifest['augmentation_sha256']:
        raise ValueError('Current active scheme differs from selected comparison scheme')
    live = root / 'forecast.dss'
    directory = Path(tempfile.mkdtemp(prefix='results-', dir=str(scheme)))
    target = directory / 'forecast.dss'
    shutil.copy2(live, target)
    digest = sha256(target)
    if digest != sha256(live):
        (directory / 'FAILED.txt').write_text('Live DSS changed during snapshot. Do not use this capture.')
        raise ValueError('Live DSS changed during capture; finish compute and close forecast/DSSVue')
    (directory / 'capture.json').write_text(json.dumps({
        'status': 'captured-compute-status-unverified', 'scheme': manifest['scheme'],
        'captured_utc': datetime.now(timezone.utc).isoformat(), 'sha256': digest,
        'baseline_sha256': manifest['baseline_sha256'],
        'baseline_id': baseline_identity(root, manifest),
        'note': 'Check RTS compute status/logs. Existing records can survive an unsuccessful recompute.'}, indent=2))
    event(root, 'result-archived', scheme=manifest['scheme'], directory=str(directory),
          baseline_id=baseline_identity(root, manifest))
    write_archive_index(root)
    return directory


def paired_frames(baseline, augmented):
    common = sorted(set(baseline.columns) & set(augmented.columns))
    if not common:
        return pd.DataFrame(), pd.DataFrame()
    left, right = baseline[common].align(augmented[common], join='inner', axis=0)
    valid = left.notna() & right.notna()
    return left.where(valid), right.where(valid)


def comparison_figure(baseline, augmented, title, units, synthetic_base=None,
                      synthetic_aug=None, requirement=None, requirement_label=None,
                      rule_curve=None):
    import plotly.graph_objects as go
    fig = go.Figure()
    for frame, name, color, fill in [(baseline, 'Baseline', '#555555', 'rgba(80,80,80,.15)'),
                                    (augmented, 'Augmented', '#0072B2', 'rgba(0,114,178,.18)')]:
        if frame.empty:
            continue
        q = quantiles(frame)
        fig.add_trace(go.Scatter(x=q.index, y=q[.25], line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=q.index, y=q[.75], line=dict(width=0), fill='tonexty',
                                fillcolor=fill, name=name + ' 25–75%', connectgaps=False))
        fig.add_trace(go.Scatter(x=q.index, y=q[.5], line=dict(color=color, width=3),
                                name=name + ' median', customdata=q.member_count,
                                hovertemplate='%{x}<br>%{y:.2f}<br>Paired members: %{customdata}<extra>%{fullData.name}</extra>'))
    for member in baseline.columns:
        for frame, name, dash, show in [(baseline, 'Baseline', 'dash', True), (augmented, 'Augmented', 'solid', False)]:
            fig.add_trace(go.Scatter(x=frame.index, y=frame[member], name='{} paired traces'.format(member) if show else str(member) + ' augmented',
                                    legendgroup=str(member), showlegend=show, visible='legendonly',
                                    line=dict(width=1.5, dash=dash), connectgaps=False,
                                    hovertemplate='%{x}<br>%{y:.2f}<extra>' + name + ' ' + str(member) + '</extra>'))
    for frame, name, dash in [(synthetic_base, 'Baseline', 'dash'), (synthetic_aug, 'Augmented', 'solid')]:
        if frame is None:
            continue
        for member in frame.columns:
            fig.add_trace(go.Scatter(x=frame.index, y=frame[member],
                                    name=name + ' ' + SYNTHETIC_LABELS.get(member, str(member)),
                                    line=dict(width=2, dash=dash), connectgaps=False))
    if requirement is not None and not requirement.empty:
        low, high = requirement.min(axis=1), requirement.max(axis=1)
        if low.equals(high):
            fig.add_trace(go.Scatter(x=low.index, y=low, name=requirement_label,
                                    line=dict(color='#D55E00', width=2, dash='dot'), connectgaps=False))
        else:
            # Release requirements differ by ensemble; expose exact values,
            # never mislabel their median as a requirement used by the model.
            for member in requirement.columns:
                fig.add_trace(go.Scatter(x=requirement.index, y=requirement[member],
                                        name='{} — {}'.format(requirement_label, member),
                                        line=dict(width=1, dash='dot'), visible='legendonly', connectgaps=False))
    if rule_curve is not None:
        fig.add_trace(go.Scatter(x=rule_curve.index, y=rule_curve, name='Rule curve',
                                line=dict(color='green', dash='dash'), connectgaps=False))
    fig.update_layout(title=title, template='plotly_white', xaxis_title='Forecast local date/time',
                      yaxis_title=units, hovermode='closest', legend=dict(groupclick='togglegroup'))
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    parser.add_argument('--scheme', required=True)
    parser.add_argument('--result-dir', help='Plot an existing capture without reading or changing the live forecast')
    parser.add_argument('--members', default='1981-1991')
    parser.add_argument('--synthetic-members', default='3000-3002')
    args = parser.parse_args()
    if not args.scheme or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.scheme):
        raise ValueError('Invalid scheme name')
    historical, synthetic = parse_members(args.members), parse_members(args.synthetic_members)
    if historical & synthetic:
        raise ValueError('Historical and synthetic members overlap')
    root = Path(args.forecast_root).resolve()
    scheme = root / 'augmentation-archives' / args.scheme
    manifest = json.loads((scheme / 'manifest.json').read_text())
    validate_manifest(root, scheme, manifest)
    if not (historical | synthetic) <= set(manifest['members']):
        raise ValueError('Requested comparison members not covered by scheme')
    if args.result_dir:
        results = result_directory(root, args.result_dir)
        if results.parent != scheme:
            raise ValueError('Selected result belongs to a different scheme')
        captured = json.loads((results / 'capture.json').read_text())
        if sha256(results / 'forecast.dss') != captured['sha256']:
            raise ValueError('Archived result checksum mismatch')
    else:
        results = capture(root, scheme, manifest)
    identity = baseline_identity(root, manifest)
    baseline_status = 'Current baseline' if identity == registry(root)['current'] else 'Previous baseline'
    # Preserve earlier plots when regenerating an archived comparison.
    destination = Path(tempfile.mkdtemp(prefix='plots-', dir=str(results)))
    from plotly.offline import get_plotlyjs
    (destination / 'plotly.min.js').write_text(get_plotlyjs(), encoding='utf-8')
    from run_data_cache import open_cached_run
    rows, links = [], []
    requirements = {}
    # Scheme CSVs hold exact release and mainstem target values by member.
    aliases, *_ = read_config(scheme / 'MinFlowSalemAlbanyConfig.csv')
    for member in sorted(historical | synthetic):
        requirements[member] = pd.read_csv(scheme / ('member-{}.csv'.format(member)), index_col=0, parse_dates=True)
    baseline_file = baseline_directory(root, manifest) / 'forecast.dss'
    with open_cached_run(baseline_file, manifest['run_code']) as baseline_dss, open_cached_run(results / 'forecast.dss', manifest['run_code']) as augmented_dss:
        bg = output_groups(baseline_dss.getPathnameList('/*/*/*/*/*/*/'), manifest['run_code'], historical | synthetic)
        ag = output_groups(augmented_dss.getPathnameList('/*/*/*/*/*/*/'), manifest['run_code'], historical | synthetic)
        for index, key in enumerate(sorted(set(bg) | set(ag))):
            _, location, parameter, interval = key
            frames, units = [], None
            for dss, groups, label in [(baseline_dss, bg, 'baseline'), (augmented_dss, ag, 'augmented')]:
                series = {}
                for member in sorted(historical | synthetic):
                    path = groups.get(key, {}).get(member)
                    try:
                        if path is None:
                            raise ValueError('Output record absent')
                        record = dss.read_ts(path, trim_missing=True)
                        record_units = unit_key(record.units)
                        if units is not None and record_units != units:
                            raise ValueError('Output units differ: ' + record_units)
                        units = record_units
                        values = clean_series(record)
                        if values.dropna().empty:
                            raise ValueError('No valid output values')
                        series[member] = values
                        rows.append([location, parameter, member, label, 'read', int(values.notna().sum()), ''])
                    except Exception as exc:
                        rows.append([location, parameter, member, label, 'missing/error', 0, str(exc)])
                frames.append(pd.DataFrame(series))
            left, right = paired_frames(frames[0].reindex(columns=sorted(historical)), frames[1].reindex(columns=sorted(historical)))
            # All-NaN columns are not contributing members.
            paired = [member for member in left.columns if left[member].notna().any()]
            left, right = left[paired], right[paired]
            if left.empty and not any(member in frame for frame in frames for member in synthetic):
                continue
            requirement, label = None, None
            name = location[:-5] if location.upper().endswith('-POOL') else location
            reservoir = next((n for n in aliases if n.upper() == name.upper()), None)
            column = None
            if parameter.upper() == 'FLOW-OUT' and reservoir:
                column = aliases[reservoir] + '_min_flow_with_aug'
                label = 'Prepared augmentation minimum release'
            elif parameter.upper() == 'FLOW' and location.upper() in ('WILLAMETTE_AT SALEM', 'WILLAMETTE_AT ALBANY'):
                column = ('SLM' if 'SALEM' in location.upper() else 'ALB') + '_minflow'
                label = 'Prepared mainstem flow target'
            if column:
                requirement = pd.DataFrame({m: data[column] for m, data in requirements.items() if column in data})
            rule = None
            if parameter.upper() in ('ELEV', 'ELEVATION') and reservoir:
                try:
                    valid_index = frames[0].index.union(frames[1].index)
                    rule, _ = load_rule_curve(baseline_dss, location, units, valid_index.min(), valid_index.max(),
                                             Path(__file__).with_name('CON_SEASON_RULE_CURVES.csv'), prefer_csv=True)
                except Exception as exc:
                    rows.append([location, parameter, '', 'rule curve', 'missing/error', 0, str(exc)])
            filename = 'comparison-{:03d}.html'.format(index)
            title = '{} — {} — baseline vs {} ({} paired historical members)'.format(location, parameter, args.scheme, len(paired))
            fig = comparison_figure(left, right, title, units,
                frames[0][[m for m in sorted(synthetic) if m in frames[0]]],
                frames[1][[m for m in sorted(synthetic) if m in frames[1]]], requirement, label, rule)
            fig.write_html(str(destination / filename), include_plotlyjs='plotly.min.js')
            stem = destination / filename[:-5]
            for frame, tag in [(frames[0], 'baseline'), (frames[1], 'augmented')]:
                frame.to_csv(str(stem) + '-' + tag + '.csv', index_label='forecast_local_datetime')
            if not left.empty:
                (right - left).to_csv(str(stem) + '-paired-difference.csv', index_label='forecast_local_datetime')
            if requirement is not None:
                requirement.to_csv(str(stem) + '-prepared-requirement.csv', index_label='forecast_local_datetime')
            links.append((filename, title, location, parameter))
            print('Compared:', location, parameter, 'Paired historical:', len(paired), flush=True)
    with (destination / 'read-report.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['location', 'parameter', 'member', 'source', 'status', 'valid_samples', 'error'])
        writer.writerows(rows)
    page = index_page(links, root.parent.name, manifest['run_code'])
    notice = '<p><strong>' + html.escape(baseline_status + ' (' + identity + ')') + '</strong></p><p><strong>Baseline vs ' + html.escape(args.scheme) + '.</strong> Grey baseline; blue augmented. Historical bands use paired valid values; synthetic traces are separate. Click a member in the legend to show its paired traces. Targets and prepared releases are overlays. Check RTS status: captured records do not certify compute success.</p>'
    page = page.replace('<body>', '<body>' + notice, 1)
    (destination / 'index.html').write_text(page, encoding='utf-8')
    print('Augmented results archived:', results)
    print('Open:', destination / 'index.html')
    print('Check read-report.csv for missing records. RTS compute success remains to be verified.')


if __name__ == '__main__':
    main()
