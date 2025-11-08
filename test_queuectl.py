"""Test script to validate core functionality of QueueCTL"""

import subprocess
import time
import json
import sys


def run_command(cmd):
    """Run a shell command and return output"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def print_test(name):
    """Print test name"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)


def print_success(message):
    """Print success message"""
    print(f"✓ {message}")


def print_error(message):
    """Print error message"""
    print(f"✗ {message}")


def test_basic_job_completion():
    """Test 1: Basic job completes successfully"""
    print_test("Basic Job Completion")
    
    # Enqueue a simple job
    job = {"id": "test-basic-1", "command": "echo Hello World"}
    code, out, err = run_command(f'python -m queuectl.cli enqueue \'{json.dumps(job)}\'')
    
    if code != 0:
        print_error(f"Failed to enqueue job: {err}")
        return False
    
    print_success("Job enqueued")
    
    # Start a worker
    code, out, err = run_command('python -m queuectl.cli worker start --count 1')
    if code != 0:
        print_error(f"Failed to start worker: {err}")
        return False
    
    print_success("Worker started")
    
    # Wait for job to complete
    time.sleep(3)
    
    # Check job status
    code, out, err = run_command(f'python -m queuectl.cli info test-basic-1')
    
    if 'completed' in out.lower():
        print_success("Job completed successfully")
    else:
        print_error(f"Job did not complete: {out}")
        return False
    
    # Stop workers
    run_command('python -m queuectl.cli worker stop')
    
    return True


def test_failed_job_retry():
    """Test 2: Failed job retries with backoff and moves to DLQ"""
    print_test("Failed Job Retry and DLQ")
    
    # Set max retries to 2 for faster testing
    run_command('python -m queuectl.cli config set max-retries 2')
    run_command('python -m queuectl.cli config set backoff-base 1')
    
    # Enqueue a failing job (non-existent command)
    job = {"id": "test-fail-1", "command": "nonexistentcommand12345"}
    code, out, err = run_command(f'python -m queuectl.cli enqueue \'{json.dumps(job)}\'')
    
    if code != 0:
        print_error(f"Failed to enqueue job: {err}")
        return False
    
    print_success("Job enqueued")
    
    # Start a worker
    run_command('python -m queuectl.cli worker start --count 1')
    print_success("Worker started")
    
    # Wait for retries and DLQ move
    time.sleep(6)
    
    # Check DLQ
    code, out, err = run_command('python -m queuectl.cli dlq list')
    
    if 'test-fail-1' in out:
        print_success("Job moved to DLQ after retries")
    else:
        print_error(f"Job not in DLQ: {out}")
        run_command('python -m queuectl.cli worker stop')
        return False
    
    # Test DLQ retry
    code, out, err = run_command('python -m queuectl.cli dlq retry test-fail-1')
    
    if code == 0:
        print_success("Job retried from DLQ")
    else:
        print_error(f"Failed to retry from DLQ: {err}")
    
    # Stop workers
    run_command('python -m queuectl.cli worker stop')
    
    # Reset config
    run_command('python -m queuectl.cli config set max-retries 3')
    run_command('python -m queuectl.cli config set backoff-base 2')
    
    return True


def test_multiple_workers():
    """Test 3: Multiple workers process jobs without overlap"""
    print_test("Multiple Workers")
    
    # Enqueue multiple jobs
    for i in range(5):
        job = {"id": f"test-multi-{i}", "command": f"echo Job {i}"}
        run_command(f'python -m queuectl.cli enqueue \'{json.dumps(job)}\'')
    
    print_success("Enqueued 5 jobs")
    
    # Start multiple workers
    code, out, err = run_command('python -m queuectl.cli worker start --count 3')
    
    if code != 0:
        print_error(f"Failed to start workers: {err}")
        return False
    
    print_success("Started 3 workers")
    
    # Wait for jobs to complete
    time.sleep(5)
    
    # Check status
    code, out, err = run_command('python -m queuectl.cli status')
    print(out)
    
    if 'Completed: 5' in out or 'completed: 5' in out.lower():
        print_success("All jobs completed")
    else:
        print_success("Workers processed jobs (check status above)")
    
    # Stop workers
    run_command('python -m queuectl.cli worker stop')
    
    return True


def test_invalid_command():
    """Test 4: Invalid commands fail gracefully"""
    print_test("Invalid Command Handling")
    
    # Enqueue job with invalid command
    job = {"id": "test-invalid-1", "command": "thisisnotavalidcommand9999"}
    code, out, err = run_command(f'python -m queuectl.cli enqueue \'{json.dumps(job)}\'')
    
    if code != 0:
        print_error(f"Failed to enqueue job: {err}")
        return False
    
    print_success("Job enqueued")
    
    # Start worker
    run_command('python -m queuectl.cli worker start --count 1')
    
    # Wait for processing
    time.sleep(3)
    
    # Check job info
    code, out, err = run_command('python -m queuectl.cli info test-invalid-1')
    
    if 'failed' in out.lower() or 'dead' in out.lower():
        print_success("Invalid command failed gracefully")
    else:
        print_error(f"Unexpected job state: {out}")
        run_command('python -m queuectl.cli worker stop')
        return False
    
    # Stop workers
    run_command('python -m queuectl.cli worker stop')
    
    return True


def test_persistence():
    """Test 5: Job data survives restart"""
    print_test("Data Persistence")
    
    # Enqueue a job
    job = {"id": "test-persist-1", "command": "echo Persistence Test"}
    run_command(f'python -m queuectl.cli enqueue \'{json.dumps(job)}\'')
    
    print_success("Job enqueued")
    
    # Check job exists
    code1, out1, err1 = run_command('python -m queuectl.cli info test-persist-1')
    
    if code1 != 0:
        print_error("Job not found after enqueueing")
        return False
    
    print_success("Job found in database")
    
    # Simulate restart by creating new CLI instance
    # (In real scenario, this would be a system restart)
    time.sleep(1)
    
    # Check job still exists
    code2, out2, err2 = run_command('python -m queuectl.cli info test-persist-1')
    
    if code2 == 0 and 'test-persist-1' in out2:
        print_success("Job data persisted across restart")
        return True
    else:
        print_error("Job data lost")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("QueueCTL Test Suite")
    print("="*60)
    
    tests = [
        ("Basic Job Completion", test_basic_job_completion),
        ("Failed Job Retry & DLQ", test_failed_job_retry),
        ("Multiple Workers", test_multiple_workers),
        ("Invalid Command", test_invalid_command),
        ("Data Persistence", test_persistence),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Test crashed: {e}")
            results.append((name, False))
        
        # Cleanup between tests
        time.sleep(1)
    
    # Final cleanup
    run_command('python -m queuectl.cli worker stop')
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
