# Does ConfigParser bypass temporary-compiler cleanup?

Tested 2026-10-15 with Java 21 and Jython 2.7.2, without HEC/native dependencies.

**Result:** changing from CSV to `ConfigParser.ConfigParser` did not eliminate
shared-state cleanup effects in these controlled reproductions. This is not a
native ResSim test of converted operational rules.

| Scenario | ConfigParser | CSV |
| --- | --- | --- |
| Read completely, close file, then shared compiler cleanup | Parsed values remain usable | Parsed values remain usable |
| Compiler cleanup interrupts an open-file read | Closed-file/closer error | Closed-file/closer error |
| Same interrupted read with isolated compiler state | Read succeeds | Read succeeds |
| Completed read, then existing registered-thread cleanup analogue | Shared cleanup stalls; isolated cleanup completes | Same |

Eight parser/file cases passed their expected assertions (two parsers, two read
scenarios, shared/isolated compiler state). Four threading cases produced the
expected outcomes: two shared-state stalls with diagnostic exit 2, two isolated
completions with exit 0. Exit 2 here confirms the reproduced problem; it is not a
successful application computation.

Raw outputs are saved in `CONFIGPARSER_RESULTS.txt`.

## Method and limits

`ConfigParserCleanupProbe.java` uses actual `ConfigParser.ConfigParser().read()`
on a small INI file and `csv.DictReader` on an equivalent CSV. For the interrupted
case only, a file wrapper triggers a temporary compile/close just after the file
opens and before the first read. The ConfigParser module's open function is
replaced locally in that test JVM to insert the wrapper; CSV receives the same
wrapper explicitly. This deliberately forced ordering tests file ownership,
not natural race frequency or parser performance. Shared cleanup can produce a
closed-file ValueError or a secondary `unregisterCloser`/null-system-state error
when finally closing the already-cleaned file. The assertion requires the
observed file to have been closed and recognizes only these specific failures.
Normal loaded cases use
unmodified readers. Each case runs in a fresh JVM.

`ParserThreadCleanupProbe.java` first finishes the actual parser read and closes
the file, then calls the existing `IdleCleanup` analogue. That analogue explicitly
imports threading and registers an executor worker before closing a compiler on
another worker. We are not claiming that ConfigParser itself creates threads or
hangs alone. The test checks whether selecting ConfigParser protects an already
threaded shared runtime; it did not.

No installed JARs, model scripts, or user configuration files were changed.
Configuration parsers and file timing may still affect a particular model's
failure rate. Reading everything into memory before concurrent work could reduce
exposure to premature file closure, but CSV can do that too; it does not by itself
address the separate threading exit-handler path.

ConfigParser normally reads section/key INI files. It is not a direct replacement
for the daily reservoir schedules stored as CSV tables. Each worker should own
its parser; this experiment does not establish safety of a shared mutable parser.

The supplied active rule snapshots contain no ConfigParser reader calls. An older
standalone archive contains ConfigParser usage in a bundled headless forecasting
example, not in the affected daily-rule readers.

## Reproduce

Use an existing Jython 2.7.2 JAR and Java 11+ (Java 21 was used). In this directory,
compile the three sources:

```
javac -cp JYTHON_JAR ConfigParserCleanupProbe.java ParserThreadCleanupProbe.java IdleCleanup.java
```

On Windows run each file case in its own JVM, substituting the parser
(`configparser` or `csv`), phase (`loaded` or `interrupted`) and compiler ownership
(`shared` or `isolated`):

```
java -cp "JYTHON_JAR;." ConfigParserCleanupProbe configparser interrupted shared
java -cp "JYTHON_JAR;." ConfigParserCleanupProbe configparser interrupted isolated
java -cp "JYTHON_JAR;." ParserThreadCleanupProbe configparser shared
java -cp "JYTHON_JAR;." ParserThreadCleanupProbe configparser isolated
```

Repeat with `csv` and with `loaded` for the file probe. On Linux use `:` instead
of `;`. The threading analogue explicitly exits its test JVM after completion or
a five-second stall; do not call it inside ResSim or another application JVM.

A specific HEC-recommended ConfigParser usage pattern could be tested separately.
These results argue against changing every reader on the assumption that the
parser alone prevents shared interpreter teardown.
