# Run from the RTS watershed Script Editor. Jython 2.7 compatible.
# No model compute is launched by this menu.
import codecs
import json
import os
import tempfile
import uuid

from javax.swing import (JFrame, JPanel, JLabel, JButton, JTextField, JComboBox,
                         JTextArea, JScrollPane, JProgressBar, SwingWorker, JCheckBox,
                         SwingUtilities, BorderFactory, JFileChooser, JOptionPane, JDialog,
                         JTable, JList, DefaultListModel, ListSelectionModel)
from javax.swing.table import DefaultTableModel
from java.lang import Boolean, String
from java.awt import BorderLayout, GridLayout, Desktop
from java.lang import Runnable, ProcessBuilder
from java.lang import Exception as JavaException
from java.io import File, BufferedReader, InputStreamReader
from usace.cavi.client import CAVI

EXTERNAL_PYTHON_DIR = r'C:\CWMS\watershed\ResSimMaster\scripts\ExternalPython'
script_file = globals().get('__file__')
if script_file and os.path.isfile(script_file):
    sibling = os.path.join(os.path.dirname(os.path.abspath(script_file)), 'ExternalPython')
    if os.path.isfile(os.path.join(sibling, 'rts_workflow.py')):
        EXTERNAL_PYTHON_DIR = sibling


class NoForecastError(RuntimeError):
    pass


def forecast_context():
    tab = CAVI.getCaviFrame().getForecastTab()
    if tab is None:
        raise NoForecastError('Open a forecast and select its run in RTS first.')
    forecast, run = tab.getForecast(), tab.getSelectedForecastRun()
    if forecast is None or run is None:
        raise NoForecastError('Open a forecast and select its run in RTS first.')
    window, zone = run.getRunTimeWindow(), tab.getTimeZone()
    if window is None or zone is None:
        raise RuntimeError('Forecast time window or timezone is unavailable.')
    return {'forecast_name': str(forecast.getName()), 'run_name': str(run.getName()),
            'dss_path': str(run.getForecastDssFilename()), 'timezone': str(zone.getID()),
            'lookback': [str(window.getLookbackDateString()), str(window.getLookbackHrMinString())],
            'start': [str(window.getStartDateString()), str(window.getStartHrMinString())],
            'end': [str(window.getEndDateString()), str(window.getEndHrMinString())]}


def python_executable():
    roots = [os.path.join(os.environ.get(base, ''), name)
             for base in ('LOCALAPPDATA', 'USERPROFILE')
             for name in ('miniconda3', 'anaconda3')]
    roots += [r'C:\ProgramData\miniconda3', r'C:\ProgramData\anaconda3',
              r'C:\Miniconda3', r'C:\Anaconda3', r'C:\Programs\Miniconda3', r'C:\Programs\Anaconda3']
    for root in roots:
        candidate = os.path.join(root, 'envs', 'hydro39', 'python.exe')
        if os.path.isfile(candidate):
            return candidate
    raise IOError('Could not find the hydro39 Python environment.')


class OnUI(Runnable):
    def __init__(self, function, *args):
        self.function, self.args = function, args
    def run(self):
        self.function(*self.args)


class BackgroundTask(SwingWorker):
    def __init__(self, owner, action, context, executable):
        SwingWorker.__init__(self)
        self.owner, self.action, self.context, self.executable = owner, action, context, executable
        self.extraction, self.html_path, self.state_path = None, None, None
    def doInBackground(self):
        descriptor, context_path = tempfile.mkstemp(prefix='rts-menu-', suffix='.json')
        os.close(descriptor)
        root = os.path.dirname(self.context['dss_path'])
        log_dir = os.path.join(root, 'workflow-logs')
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        self.log_path = os.path.join(log_dir, self.action + '-' + str(uuid.uuid4()) + '.log')
        try:
            with open(context_path, 'w') as handle:
                json.dump(self.context, handle)
            command = [self.executable, '-u', os.path.join(EXTERNAL_PYTHON_DIR, 'rts_workflow.py'),
                       '--context', context_path, '--action', self.action]
            builder = ProcessBuilder(command)
            builder.directory(File(EXTERNAL_PYTHON_DIR))
            builder.environment().put('PYTHONIOENCODING', 'utf-8')
            builder.redirectErrorStream(True)
            process = builder.start()
            reader = BufferedReader(InputStreamReader(process.getInputStream(), 'UTF-8'))
            try:
                with codecs.open(self.log_path, 'w', 'utf-8') as log:
                    while True:
                        line = reader.readLine()
                        if line is None:
                            break
                        line = unicode(line)
                        log.write(line + '\n')
                        log.flush()
                        SwingUtilities.invokeLater(OnUI(self.owner.append, line))
                        if line.startswith('MENU_EXTRACT: '):
                            self.extraction = line[len('MENU_EXTRACT: '):].strip()
                        if line.startswith('MENU_STATE: '):
                            self.state_path = line[len('MENU_STATE: '):].strip()
                        if line.startswith('Open: '):
                            self.html_path = line[len('Open: '):].strip()
            finally:
                reader.close()
            return process.waitFor()
        finally:
            if os.path.isfile(context_path):
                os.remove(context_path)
    def done(self):
        callback = self.owner.after_task
        self.owner.after_task = None
        success = False
        try:
            status = self.get()
            if status != 0:
                raise RuntimeError('Task failed (exit %s). See output and log.' % status)
            if self.html_path:
                self.owner.last_html = self.html_path
                Desktop.getDesktop().browse(File(self.html_path).toURI())
            self.owner.append('Completed: ' + self.action)
            success = True
        except (Exception, JavaException) as exc:
            self.owner.append('FAILED: ' + str(exc))
            JOptionPane.showMessageDialog(self.owner, str(exc), 'RTS workflow error', JOptionPane.ERROR_MESSAGE)
        finally:
            if hasattr(self, 'log_path'):
                self.owner.append('Log: ' + self.log_path)
            self.owner.set_busy(False)
            self.owner.update_status()
        if success and callback:
            try:
                data = None
                if self.state_path:
                    with codecs.open(self.state_path, 'r', 'utf-8') as handle:
                        data = json.load(handle)
                callback(data)
            except (Exception, JavaException) as exc:
                JOptionPane.showMessageDialog(self.owner, str(exc), 'RTS workflow', JOptionPane.ERROR_MESSAGE)


class ReservoirModel(DefaultTableModel):
    def __init__(self, data, columns):
        DefaultTableModel.__init__(self, data, columns)
    def getColumnClass(self, column):
        return Boolean if str(self.getColumnName(column)).startswith('Supports') else String
    def isCellEditable(self, row, column):
        return column > 0 and str(self.getColumnName(column)) != 'Abbreviation'


class ConfigurationWindow(JDialog):
    def __init__(self, owner, state):
        JDialog.__init__(self, owner, 'Augmentation configuration', False)
        self.owner, self.state = owner, state
        self.controls = []
        pane = JPanel(BorderLayout(8, 8))
        pane.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12))
        top = JPanel(GridLayout(0, 2, 5, 5))
        self.name = JTextField()
        top.add(JLabel('Configuration name'))
        top.add(self.name)
        self.controls.append(self.name)
        self.days = JTextField()
        top.add(JLabel('Short forecast days'))
        self.days.setToolTipText('Days of forecast inflows used before the median remaining-inflow estimate.')
        top.add(self.days)
        self.controls.append(self.days)
        self.wy_mode = JComboBox(['fixed-abundant', 'storage-maf'])
        top.add(JLabel('Water-year input interpretation'))
        top.add(self.wy_mode)
        self.controls.append(self.wy_mode)
        seasons = state['outputs']['seasons']
        self.season = JComboBox([str(item['year']) for item in seasons])
        top.add(JLabel('Covered conservation season (forecast metadata)'))
        top.add(self.season)
        self.controls.append(self.season)
        pane.add(top, BorderLayout.NORTH)
        self.table = JTable()
        self.table.setAutoResizeMode(JTable.AUTO_RESIZE_OFF)
        self.controls.append(self.table)
        pane.add(JScrollPane(self.table), BorderLayout.CENTER)
        bottom = JPanel(GridLayout(0, 1, 4, 4))
        details = state['outputs']
        bottom.add(JLabel('Baseline: %s  |  %s to %s  |  %s historical, %s synthetic members' %
            (state['current_baseline'], details['first'], details['last'], len(details['members']), len(details['synthetic_members']))))
        bottom.add(JLabel('Salem and Albany currently require the same supporting reservoirs. Hills Creek is combined with Lookout Point.'))
        bottom.add(JLabel('All CSV parameters are retained. The calculator uses participation, storage floors, release limits and travel times.'))
        buttons = JPanel(GridLayout(1, 3, 5, 5))
        for title, handler in [('Open Configuration', self.open_configuration), ('Save Configuration', self.save_configuration)]:
            button = JButton(title, actionPerformed=handler)
            buttons.add(button)
            self.controls.append(button)
        self.process_button = JButton('Process and Load Releases', actionPerformed=self.process)
        buttons.add(self.process_button)
        self.controls.append(self.process_button)
        bottom.add(buttons)
        pane.add(bottom, BorderLayout.SOUTH)
        self.setContentPane(pane)
        self.populate(state['configuration'])
        self.process_button.setEnabled(bool(seasons))
        self.setSize(1050, 520)
        self.setLocationRelativeTo(owner)
        self.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
    def populate(self, config):
        if (config.get('schema') != 1 or not config.get('columns') or config['columns'][0] != 'Variable'
                or any(len(row) != len(config['columns']) for row in config.get('rows', []))):
            raise RuntimeError('Choose a reusable RTS configuration JSON file.')
        self.config = config
        self.name.setText(config['name'])
        self.days.setText(str(config['calculation']['forecast_days']))
        self.wy_mode.setSelectedItem(config['calculation']['wy_type_mode'])
        columns = ['Reservoir'] + [row[0] for row in config['rows']]
        data = []
        for number, reservoir in enumerate(config['columns'][1:], 1):
            values = [reservoir]
            for row in config['rows']:
                value = row[number]
                values.append(value.upper() == 'TRUE' if row[0].startswith('Supports') else value)
            data.append(values)
        self.model = ReservoirModel(data, columns)
        self.table.setModel(self.model)
        for index in range(self.table.getColumnCount()):
            self.table.getColumnModel().getColumn(index).setPreferredWidth(135 if index == 0 else 115)
    def configuration(self):
        if self.table.isEditing() and not self.table.getCellEditor().stopCellEditing():
            raise RuntimeError('Finish editing the table cell first.')
        rows = []
        for column in range(1, self.model.getColumnCount()):
            variable = str(self.model.getColumnName(column))
            values = [variable]
            for row in range(self.model.getRowCount()):
                value = self.model.getValueAt(row, column)
                values.append(('TRUE' if str(value).upper() == 'TRUE' else 'FALSE') if variable.startswith('Supports') else str(value).strip())
            rows.append(values)
        return {'schema': 1, 'name': str(self.name.getText()).strip(), 'columns': self.config['columns'], 'rows': rows,
                'calculation': {'forecast_days': int(str(self.days.getText()).strip()), 'wy_type_mode': str(self.wy_mode.getSelectedItem())}}
    def open_configuration(self, event):
        try:
            chooser = JFileChooser(self.owner.configuration_library())
            if chooser.showOpenDialog(self) == JFileChooser.APPROVE_OPTION:
                with codecs.open(str(chooser.getSelectedFile().getAbsolutePath()), 'r', 'utf-8-sig') as handle:
                    self.populate(json.load(handle))
        except (Exception, JavaException) as exc:
            JOptionPane.showMessageDialog(self, str(exc), 'Configuration', JOptionPane.ERROR_MESSAGE)
    def save_configuration(self, event):
        try:
            config = self.configuration()
            chooser = JFileChooser(self.owner.configuration_library())
            chooser.setSelectedFile(File(chooser.getCurrentDirectory(), config['name'] + '.json'))
            if chooser.showSaveDialog(self) == JFileChooser.APPROVE_OPTION:
                filename = str(chooser.getSelectedFile().getAbsolutePath())
                if os.path.isfile(filename) and JOptionPane.showConfirmDialog(self, 'Replace this configuration file?\n' + filename,
                        'Save configuration', JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
                    return
                self.owner.start('save-config', {'configuration': config, 'configuration_file': filename})
        except (Exception, JavaException) as exc:
            JOptionPane.showMessageDialog(self, str(exc), 'Configuration', JOptionPane.ERROR_MESSAGE)
    def process(self, event):
        try:
            config = self.configuration()
            complete = self.owner.confirm_completed('Archive any completed current results before loading new releases?')
            if complete is None:
                return
            self.owner.start('process-config', {'configuration': config, 'season_year': str(self.season.getSelectedItem()),
                'expected_baseline_id': self.state['current_baseline'], 'confirm_completed': complete}, self.processed)
        except (Exception, JavaException) as exc:
            JOptionPane.showMessageDialog(self, str(exc), 'Configuration', JOptionPane.ERROR_MESSAGE)
    def processed(self, state):
        JOptionPane.showMessageDialog(self, 'Releases are loaded.\nReopen the forecast and run the model in RTS.\nThen use Plot Results to archive and view the completed run. Do not re-extract.')
        self.dispose()


class ResultsWindow(JDialog):
    def __init__(self, owner, state):
        JDialog.__init__(self, owner, 'Plot saved results', False)
        self.owner, self.controls = owner, []
        pane = JPanel(BorderLayout(8, 8))
        pane.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12))
        pane.add(JLabel('Select one saved run, or two to compare (Ctrl-click). Previous-baseline results retain their original data.'), BorderLayout.NORTH)
        self.model = DefaultListModel()
        self.list = JList(self.model)
        self.list.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
        pane.add(JScrollPane(self.list), BorderLayout.CENTER)
        self.controls.append(self.list)
        buttons = JPanel(GridLayout(1, 3, 5, 5))
        for title, handler in [('Plot Selected', self.plot), ('Delete Selected Augmented Result', self.delete), ('Open Last Plots', self.open_last)]:
            button = JButton(title, actionPerformed=handler)
            buttons.add(button)
            self.controls.append(button)
        pane.add(buttons, BorderLayout.SOUTH)
        self.setContentPane(pane)
        self.populate(state)
        self.setSize(1000, 400)
        self.setLocationRelativeTo(owner)
        self.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
    def populate(self, state):
        self.runs = state['runs']
        self.model.clear()
        for item in self.runs:
            self.model.addElement('%s | %s | %s' % (item['status'], item['baseline_id'], item['label']))
        if self.runs:
            self.list.setSelectedIndex(len(self.runs) - 1)
    def selected(self):
        return [self.runs[int(index)] for index in self.list.getSelectedIndices()]
    def plot(self, event):
        rows = self.selected()
        if len(rows) not in (1, 2):
            JOptionPane.showMessageDialog(self, 'Select one or two saved runs.')
            return
        self.owner.start('plot-selected', {'selected_runs': [row['id'] for row in rows]})
    def delete(self, event):
        rows = self.selected()
        if len(rows) != 1 or rows[0]['kind'] != 'augmented':
            JOptionPane.showMessageDialog(self, 'Select exactly one augmented result. Baselines are retained.')
            return
        message = 'Permanently delete this archived result and plots that include it?\n' + rows[0]['label'] + '\nBaseline and configuration inputs remain; deletion is recorded in the history.'
        if JOptionPane.showConfirmDialog(self, message, 'Delete archived result', JOptionPane.YES_NO_OPTION) == JOptionPane.YES_OPTION:
            self.owner.start('delete-result', {'result_dir': rows[0]['directory'], 'include_plots': True}, self.deleted)
    def deleted(self, state):
        self.owner.start('results', {'confirm_completed': False}, self.populate)
    def open_last(self, event):
        self.owner.open_plots(event)


class WorkflowMenu(JFrame):
    def __init__(self):
        JFrame.__init__(self, 'RTS ensemble workflow')
        self.context, self.executable = forecast_context(), python_executable()
        self.busy, self.last_html, self.after_task = False, None, None
        self.controls, self.dialogs = [], []
        if not os.path.isfile(os.path.join(EXTERNAL_PYTHON_DIR, 'workflow_simple.py')):
            raise IOError('Install the updated RTS workflow files first.')
        pane = JPanel(BorderLayout(8, 8))
        pane.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12))
        top = JPanel(BorderLayout(5, 5))
        metadata = JPanel(GridLayout(0, 2, 5, 3))
        self.metadata = {}
        for key, label in [('forecast_name', 'Forecast'), ('run_name', 'Forecast alternative'), ('dss_path', 'DSS'),
                           ('lookback', 'Lookback'), ('start', 'Forecast start'), ('end', 'End'), ('timezone', 'Timezone')]:
            field = JTextField()
            field.setEditable(False)
            field.setEnabled(False)
            self.metadata[key] = field
            metadata.add(JLabel(label))
            metadata.add(field)
        top.add(metadata, BorderLayout.CENTER)
        options = JPanel(GridLayout(0, 1, 3, 3))
        self.status = JLabel()
        options.add(self.status)
        options.add(JLabel('Compute stays in RTS. Finish compute and close DSSVue before file operations.'))
        self.use_closed = JCheckBox('Use this displayed forecast after closing it in RTS', False)
        options.add(self.use_closed)
        self.controls.append(self.use_closed)
        refresh = JButton('Refresh forecast metadata', actionPerformed=self.refresh)
        options.add(refresh)
        self.controls.append(refresh)
        top.add(options, BorderLayout.SOUTH)
        pane.add(top, BorderLayout.NORTH)
        center = JPanel(BorderLayout(6, 6))
        buttons = JPanel(GridLayout(2, 2, 8, 8))
        for title, handler in [('Initial Extract', self.extract), ('Augmentation Configuration', self.configuration),
                               ('Plot Results', self.results), ('Reset Baseline', self.reset)]:
            button = JButton(title, actionPerformed=handler)
            buttons.add(button)
            self.controls.append(button)
        center.add(buttons, BorderLayout.NORTH)
        self.text = JTextArea(13, 85)
        self.text.setEditable(False)
        center.add(JScrollPane(self.text), BorderLayout.CENTER)
        pane.add(center, BorderLayout.CENTER)
        self.progress = JProgressBar()
        self.progress.setStringPainted(True)
        self.progress.setString('Ready')
        pane.add(self.progress, BorderLayout.SOUTH)
        self.setContentPane(pane)
        self.update_metadata()
        self.append('Initial Extract archives and loads inputs. Modify the base alternative if needed, then compute in RTS.')
        self.append('After compute, Augmentation Configuration or Plot Results can accept and archive completed results.')
        self.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
        self.pack()
        self.setLocationRelativeTo(None)
        self.setVisible(True)
    def append(self, line):
        self.text.append(unicode(line) + '\n')
        self.text.setCaretPosition(self.text.getDocument().getLength())
    def update_metadata(self):
        for key, field in self.metadata.items():
            value = self.context[key]
            field.setText(' '.join(value) if isinstance(value, list) else value)
            field.setToolTipText(field.getText())
        self.update_status()
    def update_status(self):
        root = os.path.dirname(self.context['dss_path'])
        baseline, mode = 'not saved yet', 'no augmentation'
        try:
            with open(os.path.join(root, 'augmentation-archives', 'baseline-versions.json')) as handle:
                baseline = str(json.load(handle)['current'])
        except IOError:
            pass
        except (Exception, JavaException):
            baseline = 'unreadable registry'
        try:
            with open(os.path.join(root, 'rts-augmentation-active.json')) as handle:
                active = json.load(handle)
            mode = active.get('configuration_name', active['scheme'])
        except IOError:
            pass
        except (Exception, JavaException):
            mode = 'unreadable activation marker - inspect before computing'
        self.status.setText('Baseline: %s   |   Next compute: %s' % (baseline, mode))
    def set_busy(self, busy):
        self.busy = busy
        for control in self.controls:
            control.setEnabled(not busy)
        for dialog in self.dialogs:
            for control in dialog.controls:
                control.setEnabled(not busy)
            dialog.setDefaultCloseOperation(JDialog.DO_NOTHING_ON_CLOSE if busy else JDialog.DISPOSE_ON_CLOSE)
            if isinstance(dialog, ConfigurationWindow):
                dialog.process_button.setEnabled(not busy and bool(dialog.state['outputs']['seasons']))
        self.progress.setIndeterminate(busy)
        self.progress.setString('Running - see output below' if busy else 'Ready')
        self.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE if busy else JFrame.DISPOSE_ON_CLOSE)
    def refresh(self, event):
        try:
            if self.busy:
                return
            current = forecast_context()
            if current != self.context:
                for dialog in self.dialogs:
                    dialog.dispose()
                self.dialogs = []
                self.last_html = None
                self.use_closed.setSelected(False)
            self.context = current
            self.update_metadata()
        except (Exception, JavaException) as exc:
            JOptionPane.showMessageDialog(self, str(exc))
    def confirm_completed(self, purpose):
        message = purpose + '\nHas the current manual RTS compute finished successfully?\nYes: accept/archive its results. No: use previously saved results only. Cancel: stop.'
        answer = JOptionPane.showConfirmDialog(self, message, 'Accept completed results', JOptionPane.YES_NO_CANCEL_OPTION)
        if answer == JOptionPane.CANCEL_OPTION or answer == JOptionPane.CLOSED_OPTION:
            return None
        return answer == JOptionPane.YES_OPTION
    def extract(self, event):
        message = 'Download, archive and load initial inputs for the displayed forecast?\nAfterwards, modify the base alternative if needed and compute in RTS.'
        if JOptionPane.showConfirmDialog(self, message, 'Initial Extract', JOptionPane.YES_NO_OPTION) == JOptionPane.YES_OPTION:
            self.start('initial-extract', {}, self.extracted)
    def extracted(self, state):
        JOptionPane.showMessageDialog(self, 'Initial inputs are loaded and archived.\nReopen the forecast, modify the base alternative if needed, and run the model in RTS.')
    def configuration(self, event):
        complete = self.confirm_completed('Accept the current results before opening augmentation configuration?')
        if complete is not None:
            self.start('begin-config', {'confirm_completed': complete}, self.open_configuration)
    def open_configuration(self, state):
        for dialog in self.dialogs:
            if isinstance(dialog, ConfigurationWindow):
                dialog.dispose()
        dialog = ConfigurationWindow(self, state)
        self.dialogs.append(dialog)
        dialog.setVisible(True)
    def results(self, event):
        complete = self.confirm_completed('Accept the current results before choosing saved runs to plot?')
        if complete is not None:
            self.start('results', {'confirm_completed': complete}, self.open_results)
    def open_results(self, state):
        for dialog in self.dialogs:
            if isinstance(dialog, ResultsWindow):
                dialog.dispose()
        dialog = ResultsWindow(self, state)
        self.dialogs.append(dialog)
        dialog.setVisible(True)
    def reset(self, event):
        message = 'Disable augmentation for the next compute?\nModify the base alternative if needed, then run it in RTS.\nThe baseline may change. Older results become Previous baseline only after different unaugmented results are accepted.'
        if JOptionPane.showConfirmDialog(self, message, 'Reset Baseline', JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
            return
        complete = self.confirm_completed('Archive the current completed results before resetting?')
        if complete is not None:
            self.start('reset-baseline', {'confirm_completed': complete}, self.reset_done)
    def reset_done(self, state):
        for dialog in self.dialogs:
            if isinstance(dialog, ConfigurationWindow):
                dialog.dispose()
        JOptionPane.showMessageDialog(self, 'Augmentation is disabled.\nModify the base alternative if needed, then run it in RTS.\nAfter it finishes, open Augmentation Configuration or Plot Results and confirm completion to accept the baseline.')
    def configuration_library(self):
        directory = os.path.join(os.path.dirname(EXTERNAL_PYTHON_DIR), 'rts-augmentation-configurations')
        if not os.path.isdir(directory):
            os.makedirs(directory)
        return directory
    def open_plots(self, event):
        if self.last_html and os.path.isfile(self.last_html):
            Desktop.getDesktop().browse(File(self.last_html).toURI())
        else:
            JOptionPane.showMessageDialog(self, 'Create plots first.')
    def start(self, action, settings, callback=None):
        if self.busy:
            return
        try:
            try:
                current = forecast_context()
            except NoForecastError:
                if not self.use_closed.isSelected():
                    raise RuntimeError('Forecast is closed. Reopen it or select Use this displayed forecast after closing it in RTS.')
                current = self.context
            if current != self.context:
                raise RuntimeError('Forecast selection or dates changed. Refresh forecast metadata first.')
            context = dict(self.context)
            context['menu_settings'] = settings
            self.after_task = callback
            self.append('\nStarting: ' + action)
            self.set_busy(True)
            self.worker = BackgroundTask(self, action, context, self.executable)
            self.worker.execute()
        except (Exception, JavaException) as exc:
            self.after_task = None
            self.set_busy(False)
            JOptionPane.showMessageDialog(self, str(exc), 'RTS workflow', JOptionPane.ERROR_MESSAGE)


def show_menu():
    try:
        WorkflowMenu()
    except (Exception, JavaException) as exc:
        JOptionPane.showMessageDialog(None, str(exc), 'RTS workflow', JOptionPane.ERROR_MESSAGE)


SwingUtilities.invokeLater(OnUI(show_menu))
