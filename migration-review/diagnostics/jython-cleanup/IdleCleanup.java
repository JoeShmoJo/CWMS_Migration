import java.util.concurrent.*;
import org.python.core.*;
import org.python.util.PythonInterpreter;
public class IdleCleanup {
 public static void main(String[] args) throws Exception {
  boolean isolated=args.length>0 && args[0].equals("isolated");
  PythonInterpreter host=new PythonInterpreter();
  PySystemState shared=host.getSystemState();
  host.exec("import threading\nheld_threads = []");
  ExecutorService pool=Executors.newFixedThreadPool(2);
  pool.submit(()->{Py.setSystemState(shared);new PythonInterpreter().exec("import threading\nthreading._held = threading.current_thread()\n");}).get(15,TimeUnit.SECONDS);
  Future<?> f=pool.submit(()->{Py.setSystemState(shared);PythonInterpreter compiler=isolated?new PythonInterpreter(null,new PySystemState()):new PythonInterpreter();try{compiler.compile("x=1");compiler.close();}finally{Py.setSystemState(shared);}});
  try {f.get(5,TimeUnit.SECONDS);System.out.println("COMPLETED");System.exit(0);}
  catch(TimeoutException e){System.out.println("STALLED: temporary compiler close waits for idle pool worker");for(Thread t:Thread.getAllStackTraces().keySet()){if(t.getName().startsWith("pool-")){System.out.println(t.getName());for(StackTraceElement s:t.getStackTrace())System.out.println("  "+s);}}System.exit(2);}
 }
}
