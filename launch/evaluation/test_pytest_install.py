#!/usr/bin/env python3
"""
Test script to verify pytest installation functionality.
"""

import docker
import time


def test_pytest_installation():
    """Test pytest installation in a fresh container."""
    print("="*60)
    print("Testing Pytest Installation Function")
    print("="*60)
    print()

    # Import the function
    import sys
    sys.path.insert(0, '/home/disk2/guochuanzhe/workplace/icode/baidu/personal-code/envsetupbench/agent/SWE-bench-Live/launch/evaluation')
    from evaluate_images import install_pytest_in_container

    client = docker.from_env()
    container = None

    try:
        # Start a simple Python container
        print("1. Starting test container (python:3.9-slim)...")
        container = client.containers.run(
            "python:3.9-slim",
            command="tail -f /dev/null",
            detach=True,
            remove=False
        )
        time.sleep(2)
        print("   ✓ Container started")
        print()

        # Test 1: Check if pytest is NOT installed initially
        print("2. Checking pytest before installation...")
        check_cmd = ["bash", "-c", "python -m pytest --version 2>/dev/null"]
        result = container.exec_run(check_cmd)
        if result.exit_code == 0:
            print("   ⚠ pytest already installed (unexpected):")
            print(f"   {result.output.decode().strip()}")
        else:
            print("   ✓ pytest not found (as expected)")
        print()

        # Test 2: Install pytest
        print("3. Installing pytest...")
        success, message = install_pytest_in_container(container, timeout_seconds=120)
        if success:
            print(f"   ✓ {message}")
        else:
            print(f"   ✗ {message}")
            return False
        print()

        # Test 3: Verify installation
        print("4. Verifying pytest installation...")
        verify_result = container.exec_run(check_cmd)
        if verify_result.exit_code == 0:
            print(f"   ✓ pytest verified: {verify_result.output.decode().strip()}")
        else:
            print("   ✗ pytest verification failed")
            return False
        print()

        # Test 4: Test idempotency (install again)
        print("5. Testing idempotency (install again)...")
        success2, message2 = install_pytest_in_container(container, timeout_seconds=30)
        if success2:
            print(f"   ✓ {message2}")
        else:
            print(f"   ✗ {message2}")
            return False
        print()

        print("="*60)
        print("✓ All pytest installation tests passed!")
        print("="*60)
        return True

    except Exception as e:
        print()
        print("="*60)
        print(f"✗ Test failed with exception: {e}")
        print("="*60)
        return False

    finally:
        if container:
            try:
                print("\nCleaning up container...")
                container.stop(timeout=5)
                container.remove()
                print("✓ Container cleaned up")
            except:
                pass


if __name__ == '__main__':
    success = test_pytest_installation()
    exit(0 if success else 1)
