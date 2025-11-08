# QueueCTL - Background Job Queue System

A production-grade CLI-based background job queue system with worker processes, automatic retries with exponential backoff, and a Dead Letter Queue (DLQ) for permanently failed jobs.

## Features

- ✅ **Job Queue Management**: Enqueue and manage background jobs
- ✅ **Multi-Worker Support**: Run multiple worker processes in parallel
- ✅ **Automatic Retries**: Failed jobs retry automatically with exponential backoff
- ✅ **Dead Letter Queue**: Permanently failed jobs moved to DLQ for inspection
- ✅ **Persistent Storage**: Jobs survive system restarts using SQLite
- ✅ **Concurrency Control**: Lock-based mechanism prevents duplicate job execution
- ✅ **Graceful Shutdown**: Workers finish current jobs before stopping
- ✅ **Configuration Management**: Configurable retry counts, backoff strategy
- ✅ **Rich CLI Interface**: User-friendly commands with colored output

## Requirements

- Python 3.7+
- pip

## Setup Instructions

### Quick Install (Recommended)

**Windows:**
```bash
install.bat
```

**Unix/Linux/Mac:**
```bash
chmod +x install.sh
./install.sh
```

This will automatically install all dependencies and verify the installation.

### Manual Install

#### 1. Clone or Download the Repository

```bash
cd Flam
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 3. Install the Package

```bash
pip install -e .
```

#### 4. Verify Installation

```bash
python verify_install.py
```

This will install `queuectl` as a command-line tool accessible from anywhere.

## 💻 Usage Examples

### Basic Workflow

#### 1. Enqueue a Job

```bash
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'
```

#### 2. Start Workers

```bash
# Start a single worker
queuectl worker start

# Start multiple workers
queuectl worker start --count 3
```

#### 3. Check Status

```bash
queuectl status
```

Output:
```
Queue Status:
  Total Jobs: 1
  Pending: 0
  Processing: 0
  Completed: 1
  Failed: 0
  Dead (DLQ): 0

Workers:
  Active Workers: 3
```

#### 4. List Jobs

```bash
# List all jobs
queuectl list

# List jobs by state
queuectl list --state pending
queuectl list --state completed
queuectl list --state failed
```

#### 5. Get Job Details

```bash
queuectl info job1
```

#### 6. Stop Workers

```bash
queuectl worker stop
```

### Working with Failed Jobs and DLQ

#### Enqueue a Job That Will Fail

```bash
queuectl enqueue '{"id":"failing-job","command":"nonexistentcommand"}'
```

#### Check DLQ

```bash
queuectl dlq list
```

#### Retry a Job from DLQ

```bash
queuectl dlq retry failing-job
```

### Configuration Management

#### View Configuration

```bash
queuectl config show
```

#### Update Configuration

```bash
# Set max retry attempts
queuectl config set max-retries 5

# Set backoff base (delay = base ^ attempts)
queuectl config set backoff-base 3
```

### Advanced Examples

#### Custom Job with Max Retries

```bash
queuectl enqueue '{"id":"job2","command":"sleep 2","max_retries":5}'
```

#### Process Multiple Jobs

```bash
# Enqueue multiple jobs
queuectl enqueue '{"id":"job1","command":"echo Task 1"}'
queuectl enqueue '{"id":"job2","command":"echo Task 2"}'
queuectl enqueue '{"id":"job3","command":"echo Task 3"}'

# Start multiple workers to process in parallel
queuectl worker start --count 3

# Watch the status
queuectl status
```

## Architecture Overview

### System Components

```
┌─────────────┐
│     CLI     │  User Interface
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────┐
│              Job Queue Manager                   │
│  - Job lifecycle management                      │
│  - Retry logic with exponential backoff          │
│  - DLQ management                                │
└──────┬───────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────┐
│           Persistent Storage (SQLite)            │
│  - Job data persistence                          │
│  - State management                              │
│  - Atomic lock operations                        │
└──────┬───────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────┐
│         Worker Processes (Multiple)              │
│  - Execute job commands                          │
│  - Update job states                             │
│  - Handle failures                               │
└──────────────────────────────────────────────────┘
```

### Job Lifecycle

```
┌─────────┐
│ PENDING │  Initial state when job is enqueued
└────┬────┘
     │
     ▼
┌────────────┐
│ PROCESSING │  Worker acquired lock and executing
└────┬───┬───┘
     │   │
     │   └──────────────┐
     │                  │
     ▼ (success)        ▼ (failure)
┌───────────┐      ┌─────────┐
│ COMPLETED │      │ FAILED  │  Retry scheduled
└───────────┘      └────┬────┘
                        │
                        ├─── (attempts < max_retries) ───┐
                        │                                 │
                        │                                 ▼
                        │                         ┌──────────────┐
                        │                         │ Wait backoff │
                        │                         │ (2^attempts) │
                        │                         └──────┬───────┘
                        │                                │
                        │                                ▼
                        │                         Back to PENDING
                        │
                        ▼ (attempts >= max_retries)
                   ┌────────┐
                   │  DEAD  │  Moved to DLQ
                   └────────┘
```

### Data Persistence

- **Database**: SQLite for reliable, file-based persistence
- **Schema**: Jobs table with indexes on state and retry time
- **Location**: `~/.queuectl/queuectl.db` by default
- **Atomic Operations**: Lock acquisition uses database transactions

### Worker Concurrency

- **Lock Mechanism**: Database-level locking prevents duplicate processing
- **Process Isolation**: Each worker runs as a separate OS process
- **Graceful Shutdown**: SIGTERM/SIGINT handlers ensure clean exits
- **Polling**: Workers poll for jobs at configurable intervals

### Retry Strategy

- **Exponential Backoff**: `delay = backoff_base ^ attempts` seconds
- **Default**: Base = 2 (delays: 2s, 4s, 8s...)
- **Configurable**: Both base and max retries are user-configurable
- **DLQ Threshold**: Jobs move to DLQ after max_retries exhausted

## Configuration

Configuration is stored in `~/.queuectl/config.json`

### Available Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts before DLQ |
| `backoff_base` | 2 | Base for exponential backoff calculation |
| `db_path` | `queuectl.db` | Database file path |
| `worker_poll_interval` | 1 | Seconds between job polls |

## Testing Instructions

### Automated Test Suite

Run the comprehensive test suite:

```bash
python test_queuectl.py
```

This tests:
1. ✅ Basic job completion
2. ✅ Failed job retry with backoff → DLQ
3. ✅ Multiple workers without overlap
4. ✅ Invalid command handling
5. ✅ Data persistence across restarts

### Quick Manual Test (Windows)

```bash
quick_test.bat
```

### Manual Testing Scenarios

#### Test 1: Basic Job Execution

```bash
queuectl enqueue '{"id":"test1","command":"echo Success"}'
queuectl worker start
# Wait 2 seconds
queuectl status
queuectl worker stop
```

Expected: Job shows as "completed"

#### Test 2: Retry with Backoff

```bash
queuectl config set max-retries 2
queuectl config set backoff-base 2
queuectl enqueue '{"id":"test2","command":"invalidcmd"}'
queuectl worker start
# Wait 10 seconds (2s + 4s delays)
queuectl dlq list
queuectl worker stop
```

Expected: Job appears in DLQ after 2 retries

#### Test 3: Multiple Workers

```bash
queuectl enqueue '{"id":"t1","command":"sleep 2"}'
queuectl enqueue '{"id":"t2","command":"sleep 2"}'
queuectl enqueue '{"id":"t3","command":"sleep 2"}'
queuectl worker start --count 3
# Wait 3 seconds
queuectl status
queuectl worker stop
```

Expected: All 3 jobs complete in ~2-3 seconds (parallel execution)

#### Test 4: Persistence

```bash
queuectl enqueue '{"id":"persist1","command":"echo Test"}'
queuectl info persist1
# Close terminal and reopen
queuectl info persist1
```

Expected: Job still exists after restart

## Project Structure

```
Flam/
├── queuectl/
│   ├── __init__.py       # Package initialization
│   ├── cli.py            # CLI interface (Click)
│   ├── config.py         # Configuration management
│   ├── storage.py        # SQLite persistence layer
│   ├── queue.py          # Job queue manager
│   └── worker.py         # Worker process logic
├── requirements.txt      # Python dependencies
├── setup.py              # Package setup
├── test_queuectl.py      # Automated test suite
├── quick_test.bat        # Quick manual test (Windows)
└── README.md             # This file
```

## Assumptions & Trade-offs

### Assumptions

1. **Single Machine**: Designed for single-machine deployment (not distributed)
2. **Trusted Commands**: Job commands are trusted (no sandboxing)
3. **File System Access**: Workers have read/write access to config directory
4. **Process Management**: OS supports subprocess management and signals

### Trade-offs

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| SQLite vs Redis | Simpler setup, no external dependencies | Not suitable for distributed systems |
| Process-based workers | OS-level isolation, cross-platform | Higher overhead than threads |
| Polling vs Push | Simpler implementation, easier debugging | Slight delay in job pickup |
| Database locking | ACID guarantees, no race conditions | Potential bottleneck at very high scale |

### Limitations

- **Scale**: Optimized for 10-100 workers, not thousands
- **Distribution**: Single database, no sharding
- **Job Size**: Commands stored as text (large payloads not ideal)
- **Security**: No command validation or sandboxing

## Design Decisions

### Why SQLite?

- ✅ No external dependencies
- ✅ ACID transactions for safe concurrency
- ✅ File-based persistence
- ✅ Good performance for single-machine use
- ✅ Built into Python

### Why Process-based Workers?

- ✅ True parallelism (no GIL issues)
- ✅ Process isolation (crashes don't affect others)
- ✅ Easier to manage lifecycle
- ✅ Works on Windows and Unix

### Why Exponential Backoff?

- ✅ Avoids overwhelming failing services
- ✅ Gives transient errors time to resolve
- ✅ Industry-standard pattern
- ✅ Configurable for different scenarios
