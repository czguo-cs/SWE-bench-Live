#!/usr/bin/env python3
"""
Test script to verify large patch handling.
"""

import io
import os
import tarfile
import time


def test_tar_creation():
    """Test creating tar archive with large content."""
    # Simulate a large patch (1MB)
    large_content = "A" * 1024 * 1024
    patch_bytes = large_content.encode('utf-8')

    # Create tar archive in memory
    tar_stream = io.BytesIO()
    tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

    # Add content to tar
    tarinfo = tarfile.TarInfo(name='test.patch')
    tarinfo.size = len(patch_bytes)
    tarinfo.mtime = time.time()
    tar.addfile(tarinfo, io.BytesIO(patch_bytes))
    tar.close()

    # Verify tar was created
    tar_stream.seek(0)
    tar_size = len(tar_stream.getvalue())

    print(f"✓ Successfully created tar archive")
    print(f"  Original size: {len(patch_bytes):,} bytes ({len(patch_bytes)/1024:.1f} KB)")
    print(f"  Tar size: {tar_size:,} bytes ({tar_size/1024:.1f} KB)")
    print(f"  Overhead: {(tar_size - len(patch_bytes)):,} bytes")

    return True


def test_real_patch_size():
    """Test with actual cantools patch."""
    import json

    instance_path = '/home/disk2/guochuanzhe/workplace/icode/baidu/personal-code/envsetupbench/agent/SWE-bench-Live/launch/playground/benchmark_python_v3.0/cantools__cantools-296/instance.json'

    if not os.path.exists(instance_path):
        print("✗ Instance file not found, skipping real patch test")
        return True

    with open(instance_path, 'r') as f:
        data = json.load(f)
        test_patch = data.get('test_patch', '')

    print(f"\n✓ Testing with real cantools__cantools-296 patch")
    print(f"  Patch size: {len(test_patch):,} bytes ({len(test_patch)/1024:.1f} KB)")

    # Create tar
    patch_bytes = test_patch.encode('utf-8')
    tar_stream = io.BytesIO()
    tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

    tarinfo = tarfile.TarInfo(name='test.patch')
    tarinfo.size = len(patch_bytes)
    tarinfo.mtime = time.time()
    tar.addfile(tarinfo, io.BytesIO(patch_bytes))
    tar.close()

    tar_stream.seek(0)
    tar_size = len(tar_stream.getvalue())

    print(f"  Tar created: {tar_size:,} bytes ({tar_size/1024:.1f} KB)")
    print(f"  ✓ Can handle large real-world patches")

    return True


if __name__ == '__main__':
    print("="*60)
    print("Testing Large Patch Handling")
    print("="*60)
    print()

    try:
        # Test 1: Synthetic large content
        test_tar_creation()

        # Test 2: Real patch
        test_real_patch_size()

        print()
        print("="*60)
        print("✓ All tests passed!")
        print("="*60)

    except Exception as e:
        print()
        print("="*60)
        print(f"✗ Test failed: {e}")
        print("="*60)
        exit(1)
