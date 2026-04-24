#!/usr/bin/env python3
"""
Convert NumPy .npy files to binary format for C++ consumption.

Usage: python convert.py <input.npy> <output.bin>
"""
import numpy as np
import sys
import os


def convert_npy_to_bin(input_path: str, output_path: str) -> None:
    """Convert .npy file to raw binary (float32 little-endian)."""
    print(f"Loading {input_path}...")
    data = np.load(input_path)
    
    print(f"  Shape: {data.shape}")
    print(f"  Dtype: {data.dtype}")
    
    # Ensure float32
    if data.dtype != np.float32:
        print(f"  Converting {data.dtype} -> float32")
        data = data.astype(np.float32)
    
    # Write raw binary
    print(f"Writing {output_path}...")
    data.tofile(output_path)
    
    # Verify
    file_size = os.path.getsize(output_path)
    expected_size = data.nbytes
    print(f"  File size: {file_size} bytes (expected {expected_size})")
    
    assert file_size == expected_size, "File size mismatch!"
    print("  Done!")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.npy> <output.bin>")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    convert_npy_to_bin(input_path, output_path)


if __name__ == "__main__":
    main()
