import java.nio.file.*;
import org.python.core.*;
import org.python.util.PythonInterpreter;

/** Compare actual ConfigParser.read and csv.DictReader under compiler cleanup.
 * No HEC dependencies. The interrupted test injects cleanup after open, before
 * iteration, to make the resource-ownership problem deterministic.
 */
public class ConfigParserCleanupProbe {
    public static final class InterruptCompiler {
        private final boolean isolated;
        public int calls;
        public InterruptCompiler(boolean isolated) { this.isolated = isolated; }
        public void run() {
            calls++;
            PySystemState caller = Py.getSystemState();
            PythonInterpreter compiler = isolated
                ? new PythonInterpreter(null, new PySystemState())
                : new PythonInterpreter();
            try { compiler.compile("compiled_value = 42"); compiler.close(); }
            finally { Py.setSystemState(caller); }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !(args[0].equals("configparser") || args[0].equals("csv"))
                || !(args[1].equals("loaded") || args[1].equals("interrupted"))
                || !(args[2].equals("shared") || args[2].equals("isolated")))
            throw new IllegalArgumentException("configparser|csv loaded|interrupted shared|isolated");
        boolean ini = args[0].equals("configparser");
        boolean interrupted = args[1].equals("interrupted");
        boolean isolated = args[2].equals("isolated");
        Path input = Files.createTempFile("parser-cleanup-", ini ? ".ini" : ".csv");
        Files.writeString(input, ini ? "[rule]\nflow=123\n" : "flow\n123\n");
        PythonInterpreter rule = new PythonInterpreter();
        rule.set("input_path", input.toString());
        InterruptCompiler interrupt = new InterruptCompiler(isolated);
        rule.set("interrupt", interrupt);
        rule.exec("import __builtin__\n" +
            "observed_files = []\n" +
            "class PausingFile(object):\n" +
            "    def __init__(self, stream):\n" +
            "        self.stream = stream\n" +
            "        self.paused = False\n" +
            "        observed_files.append(stream)\n" +
            "    def __iter__(self): return self\n" +
            "    def _pause(self):\n" +
            "        if not self.paused:\n" +
            "            self.paused = True\n" +
            "            interrupt.run()\n" +
            "    def next(self):\n" +
            "        self._pause()\n" +
            "        return self.stream.next()\n" +
            "    def readline(self):\n" +
            "        self._pause()\n" +
            "        return self.stream.readline()\n" +
            "    def close(self): self.stream.close()\n");
        String load;
        if (ini) {
            rule.exec("import ConfigParser\nparser = ConfigParser.ConfigParser()\n");
            if (interrupted)
                rule.exec("ConfigParser.open = lambda *a: PausingFile(__builtin__.open(*a))\n");
            load = "loaded_paths = parser.read(input_path)\nvalue = parser.getint('rule', 'flow')\n";
        } else {
            rule.exec("import csv\n");
            load = interrupted
                ? "stream = PausingFile(open(input_path, 'r'))\ntry:\n    rows = list(csv.DictReader(stream))\nfinally:\n    stream.close()\nvalue = int(rows[0]['flow'])\n"
                : "with open(input_path, 'r') as stream:\n    rows = list(csv.DictReader(stream))\nvalue = int(rows[0]['flow'])\n";
        }
        boolean expectedFailure = interrupted && !isolated;
        boolean failed = false;
        try { rule.exec(load); }
        catch (RuntimeException error) {
            boolean closedFile = error instanceof PyException
                && ((PyException)error).match(Py.ValueError)
                && error.toString().toLowerCase().contains("closed");
            boolean brokenCloser = error.toString().contains("unregisterCloser")
                && error.toString().contains("this.sys");
            if (!expectedFailure || !(closedFile || brokenCloser)) throw error;
            if (!rule.eval("len(observed_files) == 1 and observed_files[0].closed").__nonzero__())
                throw new AssertionError("Expected cleanup to close the observed file");
            failed = true;
            System.out.println("Read failed: " + error.toString().trim());
        }
        if (!interrupted) interrupt.run();
        if (failed != expectedFailure || interrupt.calls != 1)
            throw new AssertionError("Unexpected parser/cleanup behavior");
        if (!failed && rule.eval("value == 123").__nonzero__() == false)
            throw new AssertionError("Parsed value incorrect");
        Files.delete(input);
        System.out.println("PASS " + args[0] + " " + args[1] + " " + args[2] + ": " +
            (failed ? "shared cleanup interrupted open-file reading" : "parsed value remains usable"));
    }
}
