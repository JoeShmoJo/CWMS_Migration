# Run with Jython 2.7.3; no RTS or live DSS required.
# Headless mode checks the table; with a display it also opens both dialogs.
import os, sys, types
for name in ('usace', 'usace.cavi', 'usace.cavi.client'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['usace.cavi.client'].CAVI = object
filename = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'migration-review', 'RTS_WORKFLOW_MENU.py'))
source = open(filename).read().replace('SwingUtilities.invokeLater(OnUI(show_menu))', '')
namespace = {'__file__': filename}
exec(compile(source, filename, 'exec'), namespace)
class StandIn(object): pass
owner = StandIn()
from javax.swing import JTable, JTextField, JComboBox
owner.table, owner.config_name_field, owner.days = JTable(), JTextField(), JTextField()
owner.wy_mode = JComboBox(['fixed-abundant', 'storage-maf'])
config = {'schema': 1, 'name': 'example', 'columns': ['Variable', 'Lookout Point', 'Hills Creek'],
          'rows': [['Abbreviation', 'LOP', 'HCR'], ['SupportsSalem', 'TRUE', 'FALSE'],
                   ['SupportsAlbany', 'TRUE', 'FALSE'], ['MinConStor', '118800', '155400'],
                   ['MaxRelease', '2700', '1800'], ['TravelTimeDays', '2', '2']],
          'calculation': {'forecast_days': 10, 'wy_type_mode': 'fixed-abundant'}}
namespace['ConfigurationWindow'].populate.im_func(owner, config)
assert not owner.model.isCellEditable(0, 0)
assert not owner.model.isCellEditable(0, 1)
assert owner.model.isCellEditable(0, 2)
assert 'BooleanRenderer' in str(type(owner.table.getDefaultRenderer(owner.model.getColumnClass(2))))
assert namespace['ConfigurationWindow'].configuration.im_func(owner) == config
owner.model.setValueAt('2000', 0, 5)
changed = namespace['ConfigurationWindow'].configuration.im_func(owner)
assert changed['rows'][4][1] == '2000'
from javax.swing import JFrame
assert hasattr(JFrame, 'DO_NOTHING_ON_CLOSE')
print('Jython 2.7.3: menu compiled; real Swing table checkboxes, read-only columns and portable configuration round-trip passed.')

# With a display, exercise the actual Java dialog constructors as RTS does.
# Method-only tests cannot catch collisions with inherited Java properties.
from java.awt import GraphicsEnvironment
from javax.swing import SwingUtilities
from java.lang import Runnable
if not GraphicsEnvironment.isHeadless():
    class DialogCheck(Runnable):
        def run(self):
            frame = JFrame('Workflow test')
            dialogs = []
            try:
                state = {'current_baseline': 'baseline-0001', 'configuration': config,
                         'outputs': {'seasons': [{'year': 2027}], 'first': '2026-10-10',
                                     'last': '2027-10-01', 'members': [1981], 'synthetic_members': [3000]},
                         'runs': [{'id': 'baseline-0001', 'kind': 'baseline', 'status': 'Current baseline',
                                   'baseline_id': 'baseline-0001', 'label': 'Baseline'}]}
                configuration = namespace['ConfigurationWindow'](frame, state)
                dialogs.append(configuration)
                configuration.setVisible(True)
                assert configuration.workflow_menu is frame
                assert configuration.configuration() == config
                assert configuration.process_button.isEnabled()
                results = namespace['ResultsWindow'](frame, state)
                dialogs.append(results)
                results.setVisible(True)
                assert results.workflow_menu is frame
                assert results.selected() == state['runs']
                results.populate({'runs': []})
                assert results.selected() == []
                print('Actual Jython ConfigurationWindow and ResultsWindow constructors and display passed.')
            finally:
                for dialog in dialogs:
                    dialog.dispose()
                frame.dispose()
    SwingUtilities.invokeAndWait(DialogCheck())
