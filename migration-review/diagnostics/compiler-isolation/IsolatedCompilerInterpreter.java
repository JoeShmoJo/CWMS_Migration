package cwms.diagnostics;

import org.python.core.Py;
import org.python.core.PySystemState;
import org.python.util.PythonInterpreter;

/** Compiler-only adapter: cache private module state, never execute model code. */
public final class IsolatedCompilerInterpreter extends PythonInterpreter {
    private static final ThreadLocal<PySystemState> COMPILER_STATE =
        new ThreadLocal<PySystemState>() {
            @Override protected PySystemState initialValue() {
                return new PySystemState();
            }
        };

    static {
        System.out.println("EXPERIMENTAL COMPILER ISOLATION V2 ACTIVE (cached per worker): "
            + IsolatedCompilerInterpreter.class.getProtectionDomain().getCodeSource().getLocation());
    }

    private final PySystemState callerState;
    private boolean released;

    public IsolatedCompilerInterpreter() {
        // Evaluate caller first, before creating/activating compiler state.
        this(Py.getSystemState(), COMPILER_STATE.get());
    }

    private IsolatedCompilerInterpreter(PySystemState caller, PySystemState compiler) {
        // Each compilation gets fresh globals/compiler flags; only modules and
        // private runtime state are reused by this Java worker thread.
        super(null, compiler);
        callerState = caller;
    }

    @Override
    public void close() {
        if (!released) {
            released = true;
            // Intentionally retain the compiler-only environment until worker/
            // JVM lifetime ends. Never clean up the live model's interpreter.
            // The native compiler invokes compile only, not exec/eval/file I/O.
            Py.setSystemState(callerState);
        }
    }
}
