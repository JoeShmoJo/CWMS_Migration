import java.nio.file.*;
import org.python.core.*;
import org.python.util.PythonInterpreter;
/** Demonstrates compiler close affecting a live interpreter; no HEC dependencies. */
public class CompilerCleanupProbe {
 public static void main(String[] args) throws Exception {
  boolean isolated=args.length>0 && args[0].equals("isolated");
  Path input=Files.createTempFile("cleanup-probe-", ".txt");
  Files.writeString(input,"configuration value\n");
  PythonInterpreter rule=new PythonInterpreter();
  rule.set("input_path",input.toString());
  rule.exec("config_file = open(input_path, 'r')");
  PythonInterpreter compiler=isolated ? new PythonInterpreter(null,new PySystemState()) : new PythonInterpreter();
  boolean same=rule.getSystemState()==compiler.getSystemState();
  compiler.compile("x = 1");
  compiler.close();
  Py.setSystemState(rule.getSystemState());
  boolean closed=rule.eval("config_file.closed").__nonzero__();
  System.out.println("Shared state: "+same+"; live rule file closed by compiler: "+closed);
  if(closed==isolated) throw new AssertionError("Unexpected cleanup behavior");
  if(!closed) rule.exec("assert config_file.read() == 'configuration value\\n'\nconfig_file.close()");
  Files.delete(input);
  System.out.println("PASS: "+(isolated?"isolated compiler preserves live file":"shared compiler reproduces premature file close"));
 }
}
