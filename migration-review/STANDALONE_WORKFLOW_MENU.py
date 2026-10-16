# Paste into the standalone ResSim Script Editor (Jython).
import os
from java.lang import Thread, Runnable, System, ProcessBuilder
from java.io import File
from java.util import ArrayList
from java.awt import GridLayout, BorderLayout
from javax.swing import (JFrame, JPanel, JButton, JTextArea, JScrollPane,
                         JOptionPane, SwingUtilities, WindowConstants, JLabel, JTextField, JComboBox)
from hec.script import ClientAppWrapper

root = str(ClientAppWrapper.getWatershed().getWkspDir())
scripts = os.path.join(root, 'scripts', 'ExternalPython')
python = os.path.join(str(System.getenv('LOCALAPPDATA')),
                      'miniconda3', 'envs', 'hydro39', 'python.exe')
if not os.path.isfile(python):
    raise RuntimeError('Python not found: ' + python)
if not os.path.isfile(os.path.join(scripts, 'CONFIG.py')):
    raise RuntimeError('ExternalPython/CONFIG.py missing in loaded watershed: ' + root)

class Call(Runnable):
    def __init__(self, fn): self.fn = fn
    def run(self): self.fn()

class Menu:
    def __init__(self):
        self.busy = False
        self.log = None
        self.frame = JFrame('Standalone ResSim workflow')
        self.frame.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        self.text = JTextArea(9, 90)
        self.text.setEditable(False)
        self.text.setLineWrap(True)
        self.text.setWrapStyleWord(True)
        self.text.setText('Baseline settings can be saved/loaded/applied through the shared editor. Use one model alternative; recompute after Apply.\nLoaded watershed: ' + root + '\n\nSelect the simulation and alternative below for Baseline Configuration. Other jobs still use ExternalPython/CONFIG.py; these selections do not change CONFIG.py. Finish computes and close DSS views before file-writing steps. Compute manually in ResSim.\n')
        buttons = JPanel(GridLayout(0, 2, 5, 5))
        buttons.add(JLabel('Baseline target simulation (select explicitly)'))
        self.simulation = JComboBox()
        self.simulation.addItem('-- Select simulation --')
        rss = os.path.join(root, 'rss')
        if os.path.isdir(rss):
            for name in sorted(os.listdir(rss)):
                if os.path.isdir(os.path.join(rss, name)):
                    self.simulation.addItem(name)
        buttons.add(self.simulation)
        buttons.add(JLabel('Baseline target alternative (as shown in ResSim)'))
        self.alternative = JTextField('')
        buttons.add(self.alternative)
        buttons.add(JButton('Baseline Configuration', actionPerformed=lambda e: self.open_baseline()))
        jobs = [
          ('Extract inputs (all four steps)', ['CWMS_Downloader_Module.py', 'RFC_Downloader_Module.py', 'Dummy_0_and_WY_Abundant_Module.py', 'OSI_Ensemble_Year.py']),
          ('Calculate augmentation', ['MainstemAugmentation.py']),
          ('Plot ensemble', ['Ensemble_Plots.py']),
          ('Plot alternative/trial comparison', ['ALT_COMPARISON_PLOTS.py'])]
        for title, files in jobs:
            buttons.add(JButton(title, actionPerformed=lambda e, t=title, f=files: self.start(t, f)))
        self.frame.add(buttons, BorderLayout.NORTH)
        self.frame.add(JScrollPane(self.text), BorderLayout.CENTER)
        self.frame.pack()
        self.frame.setLocationRelativeTo(None)
        self.frame.setVisible(True)
    def message(self, value):
        SwingUtilities.invokeLater(Call(lambda: self.text.append(value + '\n')))
    def open_baseline(self):
        if self.busy: return
        simulation = str(self.simulation.getSelectedItem())
        alternative = str(self.alternative.getText()).strip()
        if self.simulation.getSelectedIndex() == 0 or not alternative:
            JOptionPane.showMessageDialog(self.frame, 'Select the simulation and enter the alternative shown in ResSim Simulation Control.')
            return
        filename = os.path.join(scripts, 'standalone_configuration.py')
        if not os.path.isfile(filename):
            JOptionPane.showMessageDialog(self.frame, 'Install the standalone configuration editor first.')
            return
        if JOptionPane.showConfirmDialog(self.frame, 'Finish all computes before Apply. Confirm this matches ResSim Simulation Control:\nSimulation: ' + simulation + '\nAlternative: ' + alternative + '\nDirectory: ' + os.path.join(root, 'rss', simulation), 'Standalone configuration', JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        directory = os.path.join(root, 'standalone-workflow-logs')
        if not os.path.isdir(directory): os.makedirs(directory)
        self.log = os.path.join(directory, 'configuration-' + str(System.currentTimeMillis()) + '.log')
        command = ArrayList()
        for arg in [python, '-u', filename, '--watershed', root, '--simulation', simulation, '--alternative', alternative]: command.add(arg)
        builder = ProcessBuilder(command)
        builder.directory(File(scripts))
        builder.redirectErrorStream(True)
        builder.redirectOutput(File(self.log))
        builder.start()
        self.message('Configuration editor starting. Browser opens after settings load. Log: ' + self.log)
    def start(self, title, files):
        if self.busy:
            JOptionPane.showMessageDialog(self.frame, 'A job is already running.')
            return
        if JOptionPane.showConfirmDialog(self.frame,
            title + '\nUses CONFIG.py settings in:\n' + scripts + '\n\nConfirm configuration is saved and no compute is running.',
            'Run standalone scripts', JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        self.busy = True
        Thread(Call(lambda: self.run(title, files)), 'Standalone workflow job').start()
    def run(self, title, files):
        try:
            for name in files:
                if not os.path.isfile(os.path.join(scripts, name)):
                    raise RuntimeError('Missing script: ' + name)
            directory = os.path.join(root, 'standalone-workflow-logs')
            if not os.path.isdir(directory): os.makedirs(directory)
            self.log = os.path.join(directory, 'job-' + str(System.currentTimeMillis()) + '.log')
            self.message(title + '\nLog: ' + self.log)
            for name in files:
                self.message('Running ' + name)
                command = ArrayList()
                for arg in [python, '-u', os.path.join(scripts, name)]: command.add(arg)
                builder = ProcessBuilder(command)
                builder.directory(File(scripts))
                builder.redirectErrorStream(True)
                builder.redirectOutput(ProcessBuilder.Redirect.appendTo(File(self.log)))
                code = builder.start().waitFor()
                if code != 0: raise RuntimeError(name + ' exited with code ' + str(code))
            self.message('Finished. Review the log for warnings or missing data. Compute remains manual in ResSim.')
        except Exception as error:
            self.message('FAILED: ' + str(error))
        finally:
            self.busy = False

SwingUtilities.invokeLater(Call(Menu))
