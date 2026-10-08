# Run from the RTS watershed Script Editor. Jython 2.7 compatible.
# No model compute is launched by this menu.
import codecs
import json
import os
import tempfile
import uuid

from javax.swing import (JFrame, JPanel, JLabel, JButton, JTextField, JComboBox,
                         JTextArea, JScrollPane, JProgressBar, SwingWorker, JCheckBox,
                         SwingUtilities, BorderFactory, JFileChooser, JOptionPane)
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
        self.extraction, self.html_path = None, None
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
                        if line.startswith('Open: '):
                            self.html_path = line[len('Open: '):].strip()
            finally:
                reader.close()
            return process.waitFor()
        finally:
            if os.path.isfile(context_path):
                os.remove(context_path)
    def done(self):
        try:
            status = self.get()
            if status != 0:
                raise RuntimeError('Task failed (exit %s). See output and log.' % status)
            if self.extraction:
                self.owner.extraction.setText(self.extraction)
            if self.html_path:
                self.owner.last_html = self.html_path
            self.owner.append('Completed: ' + self.action)
            if self.action == 'load-extract':
                self.owner.append('NEXT: compute the baseline using RTS, then Prepare augmentation.')
            elif self.action == 'load-baseline':
                self.owner.append('NEXT: edit the model and compute unaugmented in RTS, then Save as baseline.')
            elif self.action == 'save-baseline':
                self.owner.append('Prepare a new named scheme against the current baseline. Older results retain their original pairing.')
            elif self.action == 'load-scheme':
                self.owner.append('NEXT: compute in RTS, then Compare plots. Do not re-extract.')
        except (Exception, JavaException) as exc:
            self.owner.append('FAILED: ' + str(exc))
            JOptionPane.showMessageDialog(self.owner, str(exc), 'RTS workflow error', JOptionPane.ERROR_MESSAGE)
        finally:
            if hasattr(self, 'log_path'):
                self.owner.append('Log: ' + self.log_path)
            self.owner.set_busy(False)
            self.owner.update_active_label()


class WorkflowMenu(JFrame):
    def __init__(self):
        JFrame.__init__(self, 'RTS ensemble workflow')
        self.busy, self.last_html = False, None
        self.context = forecast_context()
        self.executable = python_executable()
        if not os.path.isfile(os.path.join(EXTERNAL_PYTHON_DIR, 'rts_workflow.py')):
            raise IOError('Install the RTS workflow files first.')
        self.controls = []
        pane = JPanel(BorderLayout(8, 8))
        pane.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12))
        top = JPanel(GridLayout(0, 1, 3, 3))
        self.forecast_label, self.window_label, self.active_label = JLabel(), JLabel(), JLabel()
        for label in (self.forecast_label, self.window_label, self.active_label):
            top.add(label)
        top.add(JLabel('Finish compute and close DSSVue before preparing, loading, or capturing results. Compute stays in RTS.'))
        self.use_closed = JCheckBox('Use the displayed forecast after closing it in RTS', False)
        self.use_closed.setToolTipText('Refresh after any date changes before closing the forecast to release DSS locks. This keeps the displayed target explicit.')
        top.add(self.use_closed)
        self.controls.append(self.use_closed)
        pane.add(top, BorderLayout.NORTH)
        fields = JPanel(GridLayout(0, 2, 5, 3))
        year = self.context['end'][0][-4:]
        values = [('scheme', 'Scheme name (new for each preparation)', 'scheme_03'),
                  ('run_code', 'ResSim output run code', 'C0'),
                  ('members', 'Historical members', '1981-1991'),
                  ('synthetic_members', 'Synthetic members (separate)', '3000-3002'),
                  ('season_year', 'Augmentation season year', year),
                  ('season_end', 'Last target date (within baseline coverage)', year + '-09-30'),
                  ('forecast_days', 'Short forecast days', '10')]
        self.fields = {}
        for name, label, value in values:
            field = JTextField(value)
            self.fields[name] = field
            fields.add(JLabel(label))
            fields.add(field)
            self.controls.append(field)
        self.wy_mode = JComboBox(['fixed-abundant', 'storage-maf'])
        fields.add(JLabel('Water-year input (fixed-abundant verifies constant 4)'))
        fields.add(self.wy_mode)
        self.controls.append(self.wy_mode)
        self.extraction = JTextField('')
        fields.add(JLabel('Completed extraction folder'))
        fields.add(self.extraction)
        self.controls.append(self.extraction)
        self.result = JTextField('')
        self.result.setEditable(False)
        fields.add(JLabel('Selected archived result (for plotting or deletion)'))
        fields.add(self.result)
        self.controls.append(self.result)
        center = JPanel(BorderLayout(6, 6))
        center.add(fields, BorderLayout.NORTH)
        self.text = JTextArea(16, 95)
        self.text.setEditable(False)
        center.add(JScrollPane(self.text), BorderLayout.CENTER)
        pane.add(center, BorderLayout.CENTER)
        bottom = JPanel(BorderLayout(4, 4))
        buttons = JPanel(GridLayout(0, 3, 5, 5))
        actions = [('1. Extract to archive', 'extract'), ('2. Load extract / baseline', 'load-extract'),
                   ('3. Prepare augmentation', 'prepare'), ('4. Load selected scheme', 'load-scheme'),
                   ('5. Current forecast plots', 'plots'), ('6. Archive + compare plots', 'compare'),
                   ('Load baseline (augmentation off)', 'load-baseline'), ('Save as baseline after compute', 'save-baseline'),
                   ('List archived results', 'list-results'), ('Plot selected archived pair', 'plot-archive'),
                   ('Delete selected archived result', 'delete-result'),
                   ('Reset augmentation', 'reset'), ('Link existing baseline', 'link-baseline')]
        for title, action in actions:
            button = JButton(title, actionPerformed=lambda event, selected=action: self.start(selected))
            buttons.add(button)
            self.controls.append(button)
        for title, handler in [('Refresh selected forecast', self.refresh), ('Choose extraction folder', self.choose_extract),
                               ('Choose saved scheme', self.choose_scheme), ('Choose archived result', self.choose_result),
                               ('Open last plots', self.open_plots)]:
            button = JButton(title, actionPerformed=handler)
            buttons.add(button)
            self.controls.append(button)
        bottom.add(buttons, BorderLayout.CENTER)
        self.progress = JProgressBar()
        self.progress.setStringPainted(True)
        self.progress.setString('Ready')
        bottom.add(self.progress, BorderLayout.SOUTH)
        pane.add(bottom, BorderLayout.SOUTH)
        self.setContentPane(pane)
        self.update_labels()
        self.append('Baseline edits: Load baseline, edit and compute in RTS, then Save as baseline. No automatic model compute.')
        self.append('Use the steps in order. Prepare creates a scheme; Load activates it; compute manually in RTS.')
        self.append('For this existing forecast, use Link existing baseline once, then Choose saved scheme to select scheme_02.')
        self.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
        self.pack()
        self.setLocationRelativeTo(None)
        self.setVisible(True)
    def append(self, line):
        self.text.append(unicode(line) + '\n')
        self.text.setCaretPosition(self.text.getDocument().getLength())
    def update_labels(self):
        c = self.context
        self.forecast_label.setText('Forecast: %s   Run: %s   DSS: %s' % (c['forecast_name'], c['run_name'], c['dss_path']))
        self.window_label.setText('Lookback: %s   Forecast: %s   End: %s   %s' %
            (' '.join(c['lookback']), ' '.join(c['start']), ' '.join(c['end']), c['timezone']))
        self.update_active_label()
    def update_active_label(self):
        marker = os.path.join(os.path.dirname(self.context['dss_path']), 'rts-augmentation-active.json')
        try:
            with open(marker, 'r') as handle:
                scheme = json.load(handle)['scheme']
            self.active_label.setText('Active augmentation: ' + scheme + self.baseline_label())
        except IOError:
            self.active_label.setText('Active augmentation: baseline / disabled' + self.baseline_label())
        except (Exception, JavaException):
            self.active_label.setText('Active augmentation: unreadable marker (inspect before computing)')
    def baseline_label(self):
        path = os.path.join(os.path.dirname(self.context['dss_path']), 'augmentation-archives', 'baseline-versions.json')
        try:
            with open(path) as handle:
                return '   Current baseline: ' + str(json.load(handle)['current'])
        except IOError:
            return '   Baseline not versioned yet'
        except (Exception, JavaException):
            return '   Baseline registry unreadable'
    def set_busy(self, busy):
        self.busy = busy
        for control in self.controls:
            control.setEnabled(not busy)
        self.progress.setIndeterminate(busy)
        self.progress.setString('Running - see output below' if busy else 'Ready')
        self.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE if busy else JFrame.DISPOSE_ON_CLOSE)
    def refresh(self, event):
        try:
            context = forecast_context()
            if context != self.context:
                self.use_closed.setSelected(False)
                self.extraction.setText('')
                self.result.setText('')
                self.last_html = None
                self.fields['season_year'].setText(context['end'][0][-4:])
                self.fields['season_end'].setText(context['end'][0][-4:] + '-09-30')
            self.context = context
            self.update_labels()
        except (Exception, JavaException) as exc:
            JOptionPane.showMessageDialog(self, str(exc))
    def choose_extract(self, event):
        chooser = JFileChooser(os.path.dirname(self.context['dss_path']))
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY)
        if chooser.showOpenDialog(self) == JFileChooser.APPROVE_OPTION:
            self.extraction.setText(str(chooser.getSelectedFile().getAbsolutePath()))
    def choose_scheme(self, event):
        root = os.path.join(os.path.dirname(self.context['dss_path']), 'augmentation-archives')
        chooser = JFileChooser(root)
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY)
        if chooser.showOpenDialog(self) == JFileChooser.APPROVE_OPTION:
            path = str(chooser.getSelectedFile().getAbsolutePath())
            if os.path.normcase(os.path.dirname(path)) != os.path.normcase(root):
                JOptionPane.showMessageDialog(self, 'Choose a scheme directory inside this forecast augmentation-archives folder.')
                return
            self.fields['scheme'].setText(os.path.basename(path))
    def choose_result(self, event):
        root = os.path.join(os.path.dirname(self.context['dss_path']), 'augmentation-archives')
        try:
            with open(os.path.join(root, 'archive-index.json')) as handle:
                index = json.load(handle)
            rows = index['results']
            if not rows:
                raise RuntimeError('No archived results. Archive + compare after computing a loaded scheme first.')
            labels = ['%s | %s | %s | %s' %
                      (row['baseline_status'], row['scheme'], row.get('captured_utc', ''),
                       os.path.basename(row['directory'])) for row in rows]
            selected = JOptionPane.showInputDialog(self, 'Choose a result paired with its original baseline:',
                'Archived results', JOptionPane.QUESTION_MESSAGE, None, labels, labels[0])
            if selected is not None:
                row = rows[labels.index(str(selected))]
                self.result.setText(row['directory'])
                self.fields['scheme'].setText(row['scheme'])
                self.append('Selected: ' + row['baseline_status'] + ' ' + row['baseline_id'])
        except (Exception, JavaException) as exc:
            JOptionPane.showMessageDialog(self, str(exc) + '\nUse List archived results to refresh the catalog.')
    def open_plots(self, event):
        if self.last_html and os.path.isfile(self.last_html):
            Desktop.getDesktop().browse(File(self.last_html).toURI())
        else:
            JOptionPane.showMessageDialog(self, 'Create plots in this menu first.')
    def start(self, action):
        if self.busy:
            return
        try:
            try:
                current = forecast_context()
            except NoForecastError:
                if not self.use_closed.isSelected():
                    raise RuntimeError('Forecast is closed. Reopen it, or check Use the displayed forecast after closing it in RTS.')
                current = self.context
                self.append('Forecast closed: using the displayed forecast ' + current['forecast_name'])
            if current != self.context:
                raise RuntimeError('Selected forecast/run/time window changed. Click Refresh selected forecast before running a task.')
            if action == 'save-baseline':
                message = 'Have you finished an unaugmented compute in RTS?\nSave the displayed forecast as baseline. If its time series changed, older augmented results will be labelled Previous baseline.\nThe script cannot verify RTS compute success. Check its status first.'
                if JOptionPane.showConfirmDialog(self, message, 'Save computed baseline', JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
                    return
            if action == 'delete-result':
                selected = str(self.result.getText()).strip()
                if not selected:
                    raise RuntimeError('Choose an archived result first.')
                message = 'Permanently delete this archived augmented result and its plots?\n' + selected + '\nBaseline and scheme inputs will remain. This action is recorded in the history.'
                if JOptionPane.showConfirmDialog(self, message, 'Delete archived result', JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
                    return
            if action == 'link-baseline':
                message = 'Link the existing baseline to the displayed forecast dates?\nDo this only if the model, dates, and downloaded inputs are unchanged since that baseline was computed.\nThe baseline DSS will remain unchanged.'
                if JOptionPane.showConfirmDialog(self, message, 'Link existing baseline', JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
                    return
            settings = dict((name, str(field.getText())) for name, field in self.fields.items())
            settings['wy_type_mode'] = str(self.wy_mode.getSelectedItem())
            settings['extraction_dir'] = str(self.extraction.getText()).strip()
            settings['result_dir'] = str(self.result.getText()).strip()
            context = dict(self.context)
            context['menu_settings'] = settings
            self.append('\nStarting: ' + action)
            self.set_busy(True)
            self.worker = BackgroundTask(self, action, context, self.executable)
            self.worker.execute()
        except (Exception, JavaException) as exc:
            self.set_busy(False)
            JOptionPane.showMessageDialog(self, str(exc), 'RTS workflow', JOptionPane.ERROR_MESSAGE)


def show_menu():
    try:
        WorkflowMenu()
    except (Exception, JavaException) as exc:
        JOptionPane.showMessageDialog(None, str(exc), 'RTS workflow', JOptionPane.ERROR_MESSAGE)


SwingUtilities.invokeLater(OnUI(show_menu))
