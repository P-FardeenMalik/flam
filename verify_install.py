#!/usr/bin/env python3
"""
Installation verification script for QueueCTL

This script verifies that QueueCTL is properly installed and all components work.
Run this after installation to ensure everything is set up correctly.
"""

import sys
import subprocess


def check_command(cmd, description):
    """Check if a command runs successfully"""
    print(f"Checking {description}... ", end="")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ OK")
            return True
        else:
            print(f"❌ FAILED")
            print(f"  Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ FAILED")
        print(f"  Error: {e}")
        return False


def check_import(module, description):
    """Check if a Python module can be imported"""
    print(f"Checking {description}... ", end="")
    try:
        __import__(module)
        print("✅ OK")
        return True
    except ImportError as e:
        print(f"❌ FAILED")
        print(f"  Error: {e}")
        return False


def main():
    """Run all verification checks"""
    print("="*60)
    print("QueueCTL Installation Verification")
    print("="*60)
    print()
    
    checks = []
    
    # Check Python version
    print(f"Python version: {sys.version}")
    if sys.version_info >= (3, 7):
        print("✅ Python 3.7+ detected")
        checks.append(True)
    else:
        print("❌ Python 3.7+ required")
        checks.append(False)
    
    print()
    
    # Check dependencies
    print("Checking dependencies...")
    checks.append(check_import("click", "Click framework"))
    checks.append(check_import("colorama", "Colorama"))
    print()
    
    # Check queuectl package
    print("Checking QueueCTL package...")
    checks.append(check_import("queuectl", "queuectl package"))
    checks.append(check_import("queuectl.cli", "CLI module"))
    checks.append(check_import("queuectl.config", "Config module"))
    checks.append(check_import("queuectl.storage", "Storage module"))
    checks.append(check_import("queuectl.queue", "Queue module"))
    checks.append(check_import("queuectl.worker", "Worker module"))
    print()
    
    # Check CLI commands
    print("Checking CLI commands...")
    checks.append(check_command("queuectl --version", "queuectl --version"))
    checks.append(check_command("queuectl --help", "queuectl --help"))
    checks.append(check_command("queuectl config show", "queuectl config show"))
    print()
    
    # Summary
    print("="*60)
    passed = sum(checks)
    total = len(checks)
    
    if passed == total:
        print(f"✅ All checks passed ({passed}/{total})")
        print()
        print("QueueCTL is properly installed and ready to use!")
        print()
        print("Next steps:")
        print("  1. Run: queuectl --help")
        print("  2. Try: queuectl enqueue '{\"id\":\"test\",\"command\":\"echo Hello\"}'")
        print("  3. Read: QUICKSTART.md for more examples")
        return 0
    else:
        print(f"❌ Some checks failed ({passed}/{total} passed)")
        print()
        print("Installation may be incomplete. Try:")
        print("  1. pip install -r requirements.txt")
        print("  2. pip install -e .")
        print("  3. Run this script again")
        return 1


if __name__ == "__main__":
    sys.exit(main())
