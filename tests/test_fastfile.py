"""Container checks use synthetic bytes, never bundled commercial game data."""

import hashlib
import json
import struct
import sys
import unittest
import zlib

from talos.fastfile import FastfileError, inspect_fastfile, unpack_fastfile


def make_zone(payload=None, *, magic=b"IWffu100", version=473):
    if payload is None:
        payload = struct.pack("<9I", 123, 456, 1, 2, 3, 4, 5, 6, 7) + b"synthetic"
    return magic + struct.pack("<I", version) + zlib.compress(payload)


class FastfileInspectionTests(unittest.TestCase):
    def test_known_header_is_only_header_validation(self):
        data = b"IWffu100" + struct.pack("<I", 473) + b"not zlib"
        report = inspect_fastfile(data)
        self.assertTrue(report["supported"])
        self.assertEqual(report["profile"], "bo1_pc_unsigned_473")
        self.assertEqual(report["compressed_bytes"], 8)
        self.assertEqual(report["validation"], "header_only")
        self.assertFalse(report["assets_decoded"])
        self.assertEqual(report["sha256"], hashlib.sha256(data).hexdigest())
        json.dumps(report, allow_nan=False)

    def test_unknown_magic_remains_inspectable_without_a_claimed_layout(self):
        for magic in (b"IWffs100", b"TAff0000", b"\xff\0unknow"):
            with self.subTest(magic=magic):
                report = inspect_fastfile(make_zone(magic=magic))
                self.assertFalse(report["supported"])
                self.assertIsNone(report["header_bytes"])
                self.assertIsNone(report["compressed_bytes"])
                self.assertIsNone(report["compression"])
                self.assertIn("Unsupported", report["reason"])
                json.dumps(report)

    def test_unsupported_versions_are_not_silently_treated_as_bo1(self):
        for version in (387, 468, 474, 0, 0xFFFFFFFF):
            with self.subTest(version=version):
                report = inspect_fastfile(make_zone(version=version))
                self.assertFalse(report["supported"])
                self.assertEqual(report["version"], version)

    def test_probe_requires_complete_prefix_and_binary_input(self):
        for data in (b"", b"IWffu100", b"IWffu100\xd9\x01\0", "IWffu100"):
            with self.subTest(data=data), self.assertRaises(FastfileError):
                inspect_fastfile(data)


class FastfileUnpackingTests(unittest.TestCase):
    def test_serialized_bytes_are_preserved_and_size_fields_are_reported(self):
        # The recorded size/allocation fields need not equal serialized length.
        payload = struct.pack("<9I", 1000, 77, 10, 20, 30, 40, 50, 60, 70) + bytes(range(256))
        unpacked, report = unpack_fastfile(make_zone(payload))
        self.assertEqual(unpacked, payload)
        self.assertEqual(report["validation"], "zlib_and_xfile_header")
        self.assertFalse(report["assets_decoded"])
        self.assertEqual(report["payload_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(report["xfile"]["declared_zone_size"], 1000)
        self.assertEqual(report["xfile"]["external_size"], 77)
        self.assertEqual(report["xfile"]["block_sizes"]["virtual"], 50)
        self.assertEqual(report["xfile"]["allocation_bytes"], 280)
        self.assertEqual(report["xfile"]["remaining_serialized_bytes"], 256)
        json.dumps(report, allow_nan=False)

    def test_output_limit_accepts_exact_boundary_and_rejects_one_less(self):
        payload = bytes(1000)
        zone = make_zone(payload)
        self.assertEqual(unpack_fastfile(zone, max_output_bytes=1000)[0], payload)
        with self.assertRaisesRegex(FastfileError, "exceeds"):
            unpack_fastfile(zone, max_output_bytes=999)

    def test_high_compression_input_cannot_bypass_output_limit(self):
        zone = make_zone(bytes(1024 * 1024))
        self.assertLess(len(zone), 2048)
        with self.assertRaisesRegex(FastfileError, "exceeds"):
            unpack_fastfile(zone, max_output_bytes=4096)

    def test_invalid_limits_fail_explicitly(self):
        for limit in (0, -1, True, 1.5, "100", None, sys.maxsize):
            with self.subTest(limit=limit), self.assertRaises(FastfileError):
                unpack_fastfile(make_zone(), max_output_bytes=limit)

    def test_unsupported_profiles_are_rejected_before_inflate(self):
        for zone in (
            make_zone(magic=b"IWffs100"),
            make_zone(version=468),
            b"IWffu100" + struct.pack(">I", 473) + b"nonsense",
        ):
            with self.subTest(zone=zone), self.assertRaisesRegex(FastfileError, "Unsupported"):
                unpack_fastfile(zone)

    def test_invalid_compression_or_checksum_fails(self):
        zone = make_zone()
        damaged_checksum = zone[:-1] + bytes([zone[-1] ^ 1])
        invalid = b"IWffu100" + struct.pack("<I", 473) + b"not-zlib"
        for data in (damaged_checksum, invalid):
            with self.subTest(data=data), self.assertRaisesRegex(FastfileError, "Invalid zlib"):
                unpack_fastfile(data)

    def test_truncated_stream_fails_even_when_payload_is_decodable(self):
        zone = make_zone()
        for trim in (1, 4, len(zone) - 12):
            with self.subTest(trim=trim), self.assertRaisesRegex(FastfileError, "incomplete"):
                unpack_fastfile(zone[:-trim])

    def test_trailing_bytes_and_second_stream_are_not_silently_ignored(self):
        for suffix in (b"\0", b"garbage", zlib.compress(b"second stream")):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(FastfileError, "Trailing data"):
                unpack_fastfile(make_zone() + suffix)

    def test_xfile_header_requires_all_seven_block_sizes(self):
        for length in (0, 8, 32, 35):
            with self.subTest(length=length), self.assertRaisesRegex(FastfileError, "XFile"):
                unpack_fastfile(make_zone(bytes(length)))

    def test_large_declared_block_allocations_are_metadata_not_allocations(self):
        payload = struct.pack("<9I", *([0xFFFFFFFF] * 9))
        unpacked, report = unpack_fastfile(make_zone(payload), max_output_bytes=36)
        self.assertEqual(unpacked, payload)
        self.assertEqual(report["xfile"]["allocation_bytes"], 7 * 0xFFFFFFFF)
        self.assertEqual(report["decompressed_bytes"], 36)


if __name__ == "__main__":
    unittest.main()
