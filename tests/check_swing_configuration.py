# Run with Jython 2.7.3 and -Djava.awt.headless=true; no RTS or live DSS required.
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
owner.table, owner.name, owner.days = JTable(), JTextField(), JTextField()
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
