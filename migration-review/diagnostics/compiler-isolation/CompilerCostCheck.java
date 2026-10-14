import java.util.concurrent.*;
import org.python.core.*;
import org.python.util.PythonInterpreter;
import cwms.diagnostics.IsolatedCompilerInterpreter;
public class CompilerCostCheck {
 public static void main(String[] args) throws Exception {
  boolean reuse=args.length>0 && args[0].equals("reuse");
  new PythonInterpreter();
  ExecutorService pool=Executors.newFixedThreadPool(4);
  long started=System.nanoTime();
  java.util.List<Future<Integer>> results=new java.util.ArrayList<>();
  for(int w=0;w<4;w++)results.add(pool.submit(()->{
   PySystemState caller=new PySystemState();Py.setSystemState(caller);
   PythonInterpreter cached=reuse?new PythonInterpreter(null,new PySystemState()):null;
   Py.setSystemState(caller);
   for(int i=0;i<30;i++) {
    if(reuse){cached.compile("answer = 42","rule.py");Py.setSystemState(caller);}
    else {try(IsolatedCompilerInterpreter compiler=new IsolatedCompilerInterpreter()){compiler.compile("answer = 42","rule.py");}}
    if(Py.getSystemState()!=caller)throw new AssertionError("Caller not restored");
   }
   return 30;
  }));
  int count=0;for(Future<Integer> f:results)count+=f.get(90,TimeUnit.SECONDS);
  System.out.printf("%s: %d compilations, %.3f seconds%n",reuse?"reuse-prototype":"bundled-adapter",count,(System.nanoTime()-started)/1e9);
  System.exit(0);
 }
}
