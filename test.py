import hashlib
import os
import pathlib

import zstd


def test_zstd_compression():
    # Create some sample data
    file_path = pathlib.Path("data/test.mca")
    original_data = file_path.read_bytes()

    # Compress the data using Zstd
    compressed_data = zstd.ZSTD_compress(original_data)

    file_path_compressed = pathlib.Path("data/test.mca.zst")
    file_path_compressed.write_bytes(compressed_data)

    # Decompress the data
    decompressed_data = zstd.ZSTD_uncompress(compressed_data)

    # Verify that the original and decompressed data are the same
    assert original_data == decompressed_data, (
        "Decompressed data does not match original data"
    )

    # Print the sizes of the original, compressed, and decompressed data
    print(f"Original size: {len(original_data)} bytes")
    print(f"Compressed size: {len(compressed_data)} bytes")
    print(f"Decompressed size: {len(decompressed_data)} bytes")
    print(f"Compression ratio: {len(compressed_data) / len(original_data):.5%}")


if __name__ == "__main__":
    test_zstd_compression()
