package cwms.diagnostics;

import org.python.core.Py;
import org.python.core.PySystemState;
import org.python.util.PythonInterpreter;

/** Experimental compiler-only boundary; never use for executing model scripts. */
public final class IsolatedCompilerInterpreter extends PythonInterpreter {
    static {
        System.out.println("EXPERIMENTAL COMPILER ISOLATION ACTIVE: "
            + IsolatedCompilerInterpreter.class.getProtectionDomain().getCodeSource().getLocation());
    }

    private final PySystemState callerState;

    public IsolatedCompilerInterpreter() {
        this(Py.getSystemState());
    }

    private IsolatedCompilerInterpreter(PySystemState caller) {
        super(null, new PySystemState());
        callerState = caller;
    }

    @Override
    public void close() {
        try {
            super.close();
        } finally {
            Py.setSystemState(callerState);
        }
    }
}
