import java.nio.file.*;
import org.python.util.PythonInterpreter;

/** Run the existing threading-cleanup analogue after a completed parser read.
 * The registered executor thread is introduced by IdleCleanup, not by a claim
 * that either parser alone creates a thread. Each case needs a separate JVM.
 */
public class ParserThreadCleanupProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !(args[0].equals("configparser") || args[0].equals("csv"))
                || !(args[1].equals("shared") || args[1].equals("isolated")))
            throw new IllegalArgumentException("configparser|csv shared|isolated");
        boolean ini = args[0].equals("configparser");
        Path input = Files.createTempFile("parser-thread-cleanup-", ini ? ".ini" : ".csv");
        Files.writeString(input, ini ? "[rule]\nflow=123\n" : "flow\n123\n");
        PythonInterpreter loader = new PythonInterpreter();
        loader.set("input_path", input.toString());
        loader.exec(ini
            ? "import ConfigParser\nparser = ConfigParser.ConfigParser()\nassert parser.read(input_path)\nassert parser.getint('rule', 'flow') == 123\n"
            : "import csv\nwith open(input_path, 'r') as stream:\n    rows = list(csv.DictReader(stream))\nassert int(rows[0]['flow']) == 123\n");
        Files.delete(input);
        System.out.println("Parser read completed before threading test: " + args[0]);
        IdleCleanup.main(new String[] { args[1] });
    }
}
