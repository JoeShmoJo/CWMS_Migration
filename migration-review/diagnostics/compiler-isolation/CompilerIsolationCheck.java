import java.nio.file.*;
import java.util.concurrent.*;
import org.python.core.*;
import org.python.util.PythonInterpreter;
import cwms.diagnostics.IsolatedCompilerInterpreter;

/** Checks the actual bundled helper, including two concurrent callers. */
public class CompilerIsolationCheck {
    public static void main(String[] args) throws Exception {
        final CyclicBarrier gate = new CyclicBarrier(2);
        final PySystemState common = args.length > 0 ? new PySystemState() : null;
        final java.util.Set<PySystemState> privateStates = java.util.Collections.newSetFromMap(
            new java.util.concurrent.ConcurrentHashMap<PySystemState, Boolean>());
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Callable<Integer> check = () -> {
            PySystemState live = common == null ? new PySystemState() : common;
            Py.setSystemState(live);
            PythonInterpreter rule = new PythonInterpreter();
            Path input = Files.createTempFile("ressim-helper-check-", ".txt");
            Files.write(input, "configuration\n".getBytes("UTF-8"));
            rule.set("input_path", input.toString());
            rule.exec("import threading\nheld_thread = threading.current_thread()\nconfig_file = open(input_path, 'r')");
            gate.await(15, TimeUnit.SECONDS);
            PySystemState retainedCompilerState = null;
            for (int i = 0; i < 25; i++) {
                PyCode code;
                try (IsolatedCompilerInterpreter compiler = new IsolatedCompilerInterpreter()) {
                    if (compiler.getSystemState() == live) throw new AssertionError("Compiler shares live state");
                    if (retainedCompilerState != null && compiler.getSystemState() != retainedCompilerState)
                        throw new AssertionError("Worker did not reuse its compiler state");
                    retainedCompilerState = compiler.getSystemState();
                    privateStates.add(retainedCompilerState);
                    try (IsolatedCompilerInterpreter nested = new IsolatedCompilerInterpreter()) {
                        nested.compile("nested = 1");
                    }
                    if (Py.getSystemState() != retainedCompilerState) throw new AssertionError("Nested caller state lost");
                    compiler.compile("from __future__ import division", "future-rule.py");
                    code = compiler.compile("answer = 42", "test-rule.py");
                }
                if (Py.getSystemState() != live) throw new AssertionError("Caller state not restored");
                rule.exec(code);
                if (rule.eval("answer == 42 and not config_file.closed").__nonzero__() == false)
                    throw new AssertionError("Code or live file damaged");
                boolean rejected = false;
                try (IsolatedCompilerInterpreter compiler = new IsolatedCompilerInterpreter()) {
                    compiler.compile("if :", "invalid-rule.py");
                } catch (PyException expected) { rejected = true; }
                try (IsolatedCompilerInterpreter freshFlags = new IsolatedCompilerInterpreter()) {
                    rule.exec(freshFlags.compile("division_result = 1 / 2", "fresh-flags.py"));
                }
                if (!rule.eval("division_result == 0").__nonzero__())
                    throw new AssertionError("Compiler future flags leaked across scripts");
                if (!rejected || Py.getSystemState() != live)
                    throw new AssertionError("Syntax failure swallowed or caller state lost");
            }
            rule.exec("assert config_file.read() == 'configuration\\n'\nconfig_file.close()");
            Files.delete(input);
            return 25;
        };
        try {
            Future<Integer> a = pool.submit(check), b = pool.submit(check);
            int count = a.get(45, TimeUnit.SECONDS) + b.get(45, TimeUnit.SECONDS);
            if (privateStates.size() != 2) throw new AssertionError("Compiler state shared across workers");
            System.out.println("PASS (" + (common == null ? "distinct callers" : "shared caller") + "): " + count + " concurrent compiler cycles; live files preserved; compiled code executable; syntax errors propagate; caller state restored");
            System.exit(0);
        } catch (Throwable failure) {
            failure.printStackTrace(); System.exit(1);
        }
    }
}
