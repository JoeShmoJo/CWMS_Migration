package cwms.diagnostics;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Timing only: no caching, model mutation, or file access during measured calls. */
public final class ConfigReadTimings {
    private static final ConcurrentMap<String, Stats> DATA = new ConcurrentHashMap<>();
    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final ThreadLocal<Deque<Token>> STACK = new ThreadLocal<Deque<Token>>() {
        @Override protected Deque<Token> initialValue() { return new ArrayDeque<>(); }
    };
    private static volatile String outputRoot;
    static {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            if (outputRoot != null) try { System.out.println(writeReport()); }
            catch (Exception e) { System.err.println("CONFIG TIMING REPORT FAILED: " + e); }
        }, "Config timing report"));
    }
    private static final class Stats {
        final AtomicLong calls = new AtomicLong(), failures = new AtomicLong();
        final AtomicLong inclusive = new AtomicLong(), exclusive = new AtomicLong(), maximum = new AtomicLong();
    }
    public static final class Token {
        final long start = System.nanoTime();
        final String key;
        long children;
        private Token(String key) { this.key = key; }
    }
    public static synchronized void configure(String root) {
        if (outputRoot != null && !outputRoot.equals(root))
            throw new IllegalStateException("Different diagnostic model already used: restart ResSim");
        if (outputRoot == null) {
            outputRoot = root;
            System.out.println("CONFIG READ TIMING ACTIVE (no caching): " + root);
        }
    }
    public static Token begin(String category, String loader, String filename) {
        Token token = new Token(category+'\t'+loader+'\t'+filename);
        STACK.get().push(token); ACTIVE.incrementAndGet();
        return token;
    }
    public static void finish(Token token, boolean failed) {
        long elapsed = System.nanoTime()-token.start;
        Deque<Token> stack = STACK.get();
        if (stack.poll() != token) throw new IllegalStateException("Timing scopes out of order");
        if (!stack.isEmpty()) stack.peek().children += elapsed;
        Stats stats = DATA.computeIfAbsent(token.key, key -> new Stats());
        stats.calls.incrementAndGet();
        if (failed) stats.failures.incrementAndGet();
        stats.inclusive.addAndGet(elapsed);
        stats.exclusive.addAndGet(Math.max(0, elapsed-token.children));
        stats.maximum.accumulateAndGet(elapsed, Math::max);
        ACTIVE.decrementAndGet();
    }
    private static String csv(String value) { return "\""+value.replace("\"", "\"\"")+"\""; }
    public static synchronized String writeReport() throws IOException {
        if (outputRoot == null) throw new IllegalStateException("No instrumented scripts have run");
        int active = ACTIVE.get();
        Path directory = Paths.get(outputRoot, "capture-"+UUID.randomUUID());
        Files.createDirectories(directory);
        List<String> keys = new ArrayList<>(DATA.keySet()); Collections.sort(keys);
        long readCalls=0, loaderCalls=0, readNs=0, loaderExclusiveNs=0, failures=0;
        try (PrintWriter out = new PrintWriter(Files.newBufferedWriter(directory.resolve("timings.csv"), StandardCharsets.UTF_8))) {
            out.println("category,loader,filename,calls,failures,inclusive_ms,exclusive_ms,max_ms");
            for (String key : keys) {
                String[] fields=key.split("\t",3); Stats s=DATA.get(key);
                long calls=s.calls.get(), inc=s.inclusive.get(), exc=s.exclusive.get();
                failures+=s.failures.get();
                if (fields[0].equals("read")) { readCalls+=calls; readNs+=exc; }
                else { loaderCalls+=calls; loaderExclusiveNs+=exc; }
                out.printf(Locale.ROOT,"%s,%s,%s,%d,%d,%.6f,%.6f,%.6f%n",csv(fields[0]),csv(fields[1]),csv(fields[2]),calls,s.failures.get(),inc/1e6,exc/1e6,s.maximum.get()/1e6);
            }
            if (out.checkError()) throw new IOException("Unable to write timing CSV");
        }
        try (PrintWriter out = new PrintWriter(Files.newBufferedWriter(directory.resolve("summary.txt"), StandardCharsets.UTF_8))) {
            out.println("TIMING ONLY: no configuration caching or altered operating calculations.");
            out.println("In-flight timed calls at snapshot: "+active+" (must be zero for a completed snapshot)");
            out.println("Timed read calls: "+readCalls);
            out.println("Timed config-loader calls: "+loaderCalls);
            out.println("Failed timed calls: "+failures);
            out.printf(Locale.ROOT,"Summed read exclusive seconds: %.6f%n",readNs/1e9);
            out.printf(Locale.ROOT,"Summed loader exclusive seconds: %.6f%n",loaderExclusiveNs/1e9);
            out.println("Worker timings overlap; summed seconds are NOT wall-clock savings.");
            out.println("Loader exclusive time excludes nested instrumented reads/loaders, but includes allocation and scheduling.");
            out.println("Scope: cFile read helpers and top-level load/read functions with config in their names.");
            out.println("Direct open(), native JSON readers, and exports outside these helpers are not included.");
            out.println("Includes any instrumented initialization since this fresh JVM started; use one compute only.");
            if (out.checkError()) throw new IOException("Unable to write timing summary");
        }
        return "CONFIG TIMING REPORT: "+directory.toAbsolutePath();
    }
}
