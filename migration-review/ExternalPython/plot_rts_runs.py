"""Plot one saved RTS run or compare two; never reads live forecast outputs."""
import argparse
from contextlib import ExitStack
import csv
import html
import json
from pathlib import Path
import tempfile

import pandas as pd

from baseline_versions import (baseline_directory, digest_file, registry, result_directory, event)
from load_rts_augmentation import validate_manifest
from plot_rts_augmentation import paired_frames, comparison_figure
from plot_rts_forecast import (clean_series, output_groups, unit_key, make_figure,
                               index_page, load_rule_curve, SYNTHETIC_LABELS)
from prepare_rts_augmentation import read_config
from workflow_simple import inspect_run


def validate_run(root, descriptor):
    if descriptor['kind'] == 'baseline':
        data = registry(root)
        identity = descriptor['baseline_id']
        if identity not in data['versions'] or descriptor['id'] != identity:
            raise ValueError('Unknown baseline selection')
        item = data['versions'][identity]
        directory = baseline_directory(root, {'baseline_id': identity, 'baseline_sha256': item['sha256']})
        digest, code = item['sha256'], item['run_code']
        scheme = None
    elif descriptor['kind'] == 'augmented':
        directory = result_directory(root, descriptor['directory'])
        metadata = json.loads((directory / 'capture.json').read_text())
        scheme = directory.parent
        manifest = json.loads((scheme / 'manifest.json').read_text())
        validate_manifest(root, scheme, manifest)
        digest, code = metadata['sha256'], manifest['run_code']
    else:
        raise ValueError('Unknown saved run type')
    if directory.resolve() != Path(descriptor['directory']).resolve():
        raise ValueError('Saved run selection directory mismatch')
    if digest_file(directory / 'forecast.dss') != digest:
        raise ValueError('Saved run checksum mismatch')
    return directory / 'forecast.dss', code, scheme


def requirements(scheme, location, parameter, members):
    if scheme is None:
        return []
    aliases, *_ = read_config(scheme / 'MinFlowSalemAlbanyConfig.csv')
    column = label = None
    reservoir = next((name for name in aliases if location.upper() == name.upper() + '-POOL'), None)
    if parameter.upper() == 'FLOW-OUT' and reservoir:
        column, label = aliases[reservoir] + '_min_flow_with_aug', 'Prepared augmentation minimum release'
    elif parameter.upper() == 'FLOW' and location.upper() in ('WILLAMETTE_AT SALEM', 'WILLAMETTE_AT ALBANY'):
        column = ('SLM' if 'SALEM' in location.upper() else 'ALB') + '_minflow'
        label = 'Prepared mainstem flow target'
    if column is None:
        return []
    data = {}
    for member in members:
        table = pd.read_csv(scheme / ('member-{}.csv'.format(member)), index_col=0, parse_dates=True)
        if column in table:
            data[member] = table[column]
    return [(pd.DataFrame(data), label)] if data else []


def add_requirements(figure, frame, label):
    import plotly.graph_objects as go
    low, high = frame.min(axis=1), frame.max(axis=1)
    if low.equals(high):
        figure.add_trace(go.Scatter(x=low.index, y=low, name=label,
                        line=dict(width=2, dash='dot'), connectgaps=False))
    else:
        figure.add_trace(go.Scatter(x=low.index, y=low, showlegend=False,
                        line=dict(width=1, dash='dot', color='#D55E00'), connectgaps=False))
        figure.add_trace(go.Scatter(x=high.index, y=high, name=label + ' range across members',
                        line=dict(width=1, dash='dot', color='#D55E00'),
                        fill='tonexty', fillcolor='rgba(213,94,0,.08)', connectgaps=False))
        for member in frame:
            figure.add_trace(go.Scatter(x=frame.index, y=frame[member], name=label + ' ' + str(member),
                            line=dict(width=1, dash='dot'), visible='legendonly', connectgaps=False))


def plot_saved_runs(root, descriptors):
    root = Path(root)
    if len(descriptors) not in (1, 2):
        raise ValueError('Choose one or two saved runs')
    sources = [validate_run(root, descriptor) for descriptor in descriptors]
    details = [inspect_run(filename, code) for filename, code, _ in sources]
    all_members = set(member for detail in details for member in detail['members'] + detail['synthetic_members'])
    historical = {member for member in all_members if member < 3000}
    synthetic = all_members - historical
    output_root = root / 'output_plots'
    output_root.mkdir(exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix='saved-runs-', dir=str(output_root)))
    from plotly.offline import get_plotlyjs
    (destination / 'plotly.min.js').write_text(get_plotlyjs(), encoding='utf-8')
    audit, links = [], []
    with ExitStack() as stack:
        from pydsstools.heclib.dss import HecDss
        handles = [stack.enter_context(HecDss.Open(str(filename))) for filename, _, _ in sources]
        groups = [output_groups(handle.getPathnameList('/*/*/*/*/*/*/'), source[1], all_members)
                  for handle, source in zip(handles, sources)]
        keys = set().union(*(set(group) for group in groups))
        for number, key in enumerate(sorted(keys), 1):
            _, location, parameter, _ = key
            frames, units = [], set()
            for descriptor, handle, group in zip(descriptors, handles, groups):
                data = {}
                for member, path in group.get(key, {}).items():
                    try:
                        record = handle.read_ts(path, trim_missing=True)
                        series = clean_series(record)
                        if series.dropna().empty:
                            raise ValueError('No finite samples')
                        units.add(unit_key(record.units))
                        data[member] = series
                        audit.append([descriptor['id'], location, parameter, member, 'read', ''])
                    except Exception as exc:
                        audit.append([descriptor['id'], location, parameter, member, 'missing/error', str(exc)])
                frames.append(pd.DataFrame(data))
            if len(units) > 1:
                raise ValueError('Units differ between selected saved runs: ' + location + ' ' + parameter)
            if not units:
                continue
            label = ' vs '.join(item['label'] for item in descriptors)
            title = '{} — {} — {}'.format(location, parameter, label)
            rule = None
            if parameter.upper() in ('ELEV', 'ELEVATION') and location.upper().endswith('-POOL'):
                try:
                    valid = frames[0].index
                    if len(valid):
                        rule, _ = load_rule_curve(handles[0], location, next(iter(units)), valid.min(), valid.max(),
                                        Path(__file__).with_name('CON_SEASON_RULE_CURVES.csv'))
                except Exception as exc:
                    audit.append([descriptors[0]['id'], location, parameter, '', 'rule curve', str(exc)])
            if len(frames) == 1:
                frame = frames[0]
                hist = frame[[member for member in frame if member in historical]]
                synth = frame[[member for member in frame if member in synthetic]]
                if hist.empty:
                    continue
                figure = make_figure(hist, title, next(iter(units)), rule, 'Rule curve', synth)
            else:
                left, right = paired_frames(frames[0].reindex(columns=sorted(historical)),
                                            frames[1].reindex(columns=sorted(historical)))
                valid = [member for member in left if left[member].notna().any()]
                left, right = left[valid], right[valid]
                if left.empty and not any(member in frame for frame in frames for member in synthetic):
                    continue
                figure = comparison_figure(left, right, title, next(iter(units)),
                    frames[0][[member for member in frames[0] if member in synthetic]],
                    frames[1][[member for member in frames[1] if member in synthetic]], rule_curve=rule)
                for trace in figure.data:
                    if trace.name:
                        trace.name = trace.name.replace('Baseline', 'Run 1').replace('Augmented', 'Run 2')
                    if trace.hovertemplate:
                        trace.hovertemplate = trace.hovertemplate.replace('Baseline', 'Run 1').replace('Augmented', 'Run 2')
                (right - left).to_csv(destination / ('plot-{:03d}-paired-difference.csv'.format(number)), index_label='forecast_local_datetime')
            filename = 'plot-{:03d}.html'.format(number)
            for index, (frame, source) in enumerate(zip(frames, sources), 1):
                frame.to_csv(destination / ('plot-{:03d}-run-{}.csv'.format(number, index)), index_label='forecast_local_datetime')
                for requirement, requirement_label in requirements(source[2], location, parameter, sorted(frame.columns)):
                    add_requirements(figure, requirement, 'Run {} {}'.format(index, requirement_label))
                    requirement.to_csv(destination / ('plot-{:03d}-run-{}-requirements.csv'.format(number, index)), index_label='forecast_local_datetime')
            figure.write_html(str(destination / filename), include_plotlyjs='plotly.min.js')
            links.append((filename, title, location, parameter))
            print('Plotted saved results:', location, parameter, flush=True)
    if not links:
        raise ValueError('No readable matching results were found')
    with (destination / 'read-report.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['run', 'location', 'parameter', 'member', 'status', 'error'])
        writer.writerows(audit)
    data = registry(root)
    notes = []
    for number, item in enumerate(descriptors, 1):
        status = 'Current baseline' if item['baseline_id'] == data['current'] else 'Previous baseline'
        notes.append('Run {}: {} — {} ({})'.format(number, item['label'], status, item['baseline_id']))
    if len({item['baseline_id'] for item in descriptors}) > 1:
        notes.append('These runs use different baselines. Differences include baseline changes as well as augmentation.')
    page = index_page(links, root.parent.name, sources[0][1])
    page = page.replace('<body>', '<body><p>' + '<br>'.join(html.escape(note) for note in notes) + '</p>', 1)
    (destination / 'index.html').write_text(page, encoding='utf-8')
    atomic = {'runs': descriptors, 'note': 'Completed computes were confirmed by the operator, not verified from RTS logs.'}
    (destination / 'selection.json').write_text(json.dumps(atomic, indent=2), encoding='utf-8')
    event(root, 'saved-runs-plotted', runs=[item['id'] for item in descriptors], directory=str(destination))
    print('Open:', destination / 'index.html', flush=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    parser.add_argument('--runs-json', required=True)
    args = parser.parse_args()
    descriptors = json.loads(Path(args.runs_json).read_text(encoding='utf-8-sig'))
    plot_saved_runs(Path(args.forecast_root).resolve(), descriptors)


if __name__ == '__main__':
    main()
