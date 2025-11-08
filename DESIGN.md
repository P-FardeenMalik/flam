# Architecture Design Document

## System Architecture

### Overview

QueueCTL is a CLI-based job queue system designed for single-machine deployments. It provides reliable background job processing with automatic retries and failure handling.

### Core Components

#### 1. CLI Layer (`cli.py`)
- **Responsibility**: User interface and command routing
- **Technology**: Click framework for command parsing
- **Features**:
  - Command validation
  - Output formatting with colors (colorama)
  - Error handling and user feedback

#### 2. Queue Manager (`queue.py`)
- **Responsibility**: Job lifecycle management
- **Key Functions**:
  - Job enqueueing with validation
  - State transitions (pending → processing → completed/failed/dead)
  - Retry scheduling with exponential backoff
  - DLQ management

#### 3. Storage Layer (`storage.py`)
- **Responsibility**: Data persistence and atomic operations
- **Technology**: SQLite with transaction support
- **Schema**:
  ```sql
  jobs (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER,
    max_retries INTEGER,
    created_at TEXT,
    updated_at TEXT,
    locked_by TEXT,
    locked_at TEXT,
    next_retry_at TEXT,
    error TEXT,
    output TEXT
  )
  ```
- **Indexes**: state, next_retry_at for query optimization

#### 4. Worker Process (`worker.py`)
- **Responsibility**: Job execution
- **Lifecycle**:
  1. Poll for available jobs
  2. Acquire lock atomically
  3. Execute command via subprocess
  4. Update job state based on exit code
  5. Release lock
- **Features**:
  - Signal handling for graceful shutdown
  - Lock-based concurrency control
  - Cross-platform command execution

#### 5. Configuration (`config.py`)
- **Responsibility**: System configuration management
- **Storage**: JSON file in `~/.queuectl/config.json`
- **Runtime**: Loaded once at startup, persisted on changes

### Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    1. User Enqueues Job                  │
│                    queuectl enqueue                      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              2. Job Saved to SQLite Database             │
│              State: PENDING, Attempts: 0                 │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│            3. Worker Polls for Pending Jobs              │
│            SELECT * FROM jobs WHERE state='pending'      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│         4. Worker Acquires Lock (Atomic UPDATE)          │
│         SET locked_by=worker_id WHERE locked_by IS NULL  │
└────────────────────────────┬────────────────────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
    ┌─────────────────────┐   ┌──────────────────┐
    │   5a. Success       │   │  5b. Failure     │
    │   Exit Code: 0      │   │  Exit Code: !=0  │
    └──────────┬──────────┘   └────────┬─────────┘
               │                       │
               ▼                       ▼
    ┌─────────────────────┐   ┌──────────────────┐
    │ State: COMPLETED    │   │ Attempts++       │
    │ Output: stdout      │   │ Error: stderr    │
    └─────────────────────┘   └────────┬─────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         │                           │
                         ▼                           ▼
              ┌──────────────────┐        ┌────────────────┐
              │ Attempts < Max   │        │ Attempts ≥ Max │
              │ State: FAILED    │        │ State: DEAD    │
              │ next_retry_at:   │        │ → DLQ          │
              │ now + 2^attempts │        └────────────────┘
              └──────────────────┘
```

### Concurrency Model

#### Lock-Based Job Processing

```python
# Atomic lock acquisition
UPDATE jobs 
SET locked_by = ?, locked_at = ?, state = 'processing'
WHERE id = ? AND locked_by IS NULL AND state IN ('pending', 'failed')
```

**Key Points**:
- SQLite transactions ensure atomicity
- Only one worker can acquire a job
- Locks prevent duplicate processing
- Stale lock cleanup handles crashed workers

#### Worker Isolation

- Each worker is a separate OS process
- No shared memory between workers
- Communication via database only
- Process crashes don't affect others

### Retry Mechanism

#### Exponential Backoff Formula

```
delay_seconds = backoff_base ^ attempts

Examples (base=2):
Attempt 1: 2^1 = 2 seconds
Attempt 2: 2^2 = 4 seconds
Attempt 3: 2^3 = 8 seconds
```

#### Implementation

```python
next_retry = datetime.utcnow() + timedelta(seconds=backoff_base ** attempts)
```

Workers query for jobs where:
```sql
state = 'failed' AND (next_retry_at IS NULL OR next_retry_at <= NOW())
```

### State Machine

```
          ┌─────────────────────────────────┐
          │         JOB ENQUEUED            │
          │         State: PENDING          │
          └────────────┬────────────────────┘
                       │
                       ▼
          ┌─────────────────────────────────┐
          │       WORKER ACQUIRES LOCK       │
          │       State: PROCESSING          │
          └────────────┬────────────────────┘
                       │
          ┌────────────┴─────────────┐
          │                          │
          ▼                          ▼
    ┌─────────┐              ┌──────────┐
    │ SUCCESS │              │ FAILURE  │
    └────┬────┘              └─────┬────┘
         │                         │
         ▼                         ▼
    ┌─────────┐         ┌──────────────────┐
    │COMPLETED│         │ attempts < max?  │
    └─────────┘         └─────┬──────┬─────┘
                              │      │
                          Yes │      │ No
                              │      │
                              ▼      ▼
                         ┌────────┐ ┌──────┐
                         │ FAILED │ │ DEAD │
                         │ +retry │ │ DLQ  │
                         └───┬────┘ └──────┘
                             │
                             └──(after backoff)──→ PENDING
```

### Scalability Considerations

#### Current Limitations

| Aspect | Limit | Reason |
|--------|-------|--------|
| Workers | ~100 | SQLite write concurrency |
| Jobs/sec | ~1000 | Polling interval + DB I/O |
| Job size | ~10KB | TEXT field in SQLite |
| Distribution | 1 machine | Shared filesystem required |

#### Optimization Opportunities

1. **Connection Pooling**: Reduce DB connection overhead
2. **Batch Operations**: Process multiple jobs per transaction
3. **Index Tuning**: Add compound indexes for common queries
4. **WAL Mode**: Enable SQLite Write-Ahead Logging
5. **Push Notifications**: Replace polling with triggers

### Security Considerations

#### Current Implementation

- ✅ No SQL injection (parameterized queries)
- ✅ Config file permissions
- ❌ No command sandboxing
- ❌ No input validation on commands
- ❌ No resource limits

#### Recommendations for Production

1. **Command Whitelist**: Only allow approved commands
2. **Sandboxing**: Use containers or VMs for execution
3. **Resource Limits**: CPU/memory quotas per job
4. **Authentication**: Add user/role management
5. **Audit Logging**: Track all job operations

### Error Handling Strategy

#### Transient Errors (Retryable)
- Network timeouts
- Temporary resource unavailability
- Rate limit errors

**Handling**: Exponential backoff + retry

#### Permanent Errors (Non-retryable)
- Invalid command syntax
- Missing executables
- Permission denied

**Handling**: Move to DLQ immediately (optional enhancement)

#### System Errors
- Database corruption
- Disk full
- Worker crashes

**Handling**: Stale lock cleanup + manual intervention

### Future Enhancements

#### Priority Queue
```sql
ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0;
CREATE INDEX idx_priority ON jobs(priority DESC, created_at ASC);
```

#### Scheduled Jobs
```sql
ALTER TABLE jobs ADD COLUMN run_at TEXT;
SELECT * FROM jobs WHERE state='pending' AND run_at <= NOW();
```

#### Job Dependencies
```sql
CREATE TABLE job_dependencies (
  job_id TEXT,
  depends_on_job_id TEXT,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

#### Metrics & Monitoring
- Job completion rates
- Average execution time
- Failure reasons histogram
- Worker utilization

### Testing Strategy

#### Unit Tests
- Queue operations (enqueue, dequeue)
- State transitions
- Retry logic
- Lock acquisition

#### Integration Tests
- End-to-end job execution
- Multi-worker scenarios
- Database persistence
- Configuration management

#### Stress Tests
- High job volume
- Many concurrent workers
- Long-running jobs
- Failure scenarios

---

## Technology Choices Justification

### Python
- ✅ Excellent CLI frameworks (Click)
- ✅ Rich standard library (subprocess, sqlite3)
- ✅ Cross-platform compatibility
- ✅ Quick development time

### Click
- ✅ Declarative command definition
- ✅ Automatic help generation
- ✅ Type validation
- ✅ Nested command groups

### SQLite
- ✅ Zero configuration
- ✅ ACID transactions
- ✅ Built into Python
- ✅ Single file database
- ❌ Limited write concurrency

### Process-based Workers
- ✅ True parallelism
- ✅ Fault isolation
- ✅ Simple lifecycle management
- ❌ Higher memory overhead

---

**Design Philosophy**: Simple, reliable, maintainable. Optimize for correctness over performance.
