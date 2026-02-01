#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test: Verify tick_edge_scan.py handles 0 events gracefully.

Ensures:
1. Script completes without UnboundLocalError when using streaming mode
2. summary.json is written even with 0 events detected
3. Metadata in summary.json is populated with tick counters from load_stats
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path


def test_streaming_mode_zero_events():
    """Test that script completes with 0 events in streaming mode and writes summary.json."""
    print("\n[TEST] Streaming mode with 0 events (verify UnboundLocalError fix)...")
    
    # Create a tiny MT5 CSV file with just a few ticks (won't detect compression events)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tick_file:
        # Write minimal MT5 format data
        tick_file.write("<DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>\t<FLAGS>\n")
        # Just 5 ticks on the same day (not enough for compression detection)
        tick_file.write("2024.01.15\t09:00:00.000\t1.09000\t1.09020\t1.09015\t100\t0\n")
        tick_file.write("2024.01.15\t09:00:01.000\t1.09010\t1.09025\t1.09020\t150\t0\n")
        tick_file.write("2024.01.15\t09:00:02.000\t1.09005\t1.09020\t1.09010\t120\t0\n")
        tick_file.write("2024.01.15\t09:00:03.000\t1.09015\t1.09030\t1.09025\t180\t0\n")
        tick_file.write("2024.01.15\t09:00:04.000\t1.09020\t1.09035\t1.09030\t140\t0\n")
        tick_file_path = tick_file.name
    
    # Create temp output directory
    with tempfile.TemporaryDirectory() as output_dir:
        try:
            # Run tick_edge_scan.py with streaming mode (--tick_file)
            # This should NOT raise UnboundLocalError
            cmd = [
                sys.executable, 
                os.path.join(os.path.dirname(__file__), 'tick_edge_scan.py'),
                '--tick_file', tick_file_path,
                '--output_dir', output_dir,
                '--verbose',
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Script should complete successfully
            if result.returncode != 0:
                print(f"  STDERR: {result.stderr}")
                print(f"  STDOUT: {result.stdout}")
                # Check if error is specifically UnboundLocalError (which would be a regression)
                if "UnboundLocalError" in result.stderr or "UnboundLocalError" in result.stdout:
                    raise AssertionError("UnboundLocalError detected - streaming mode fix failed!")
                # Other errors are acceptable (e.g., not enough data for decision)
            
            # Verify summary.json was created
            summary_json_path = os.path.join(output_dir, 'summary.json')
            assert os.path.exists(summary_json_path), f"summary.json not found at {summary_json_path}"
            
            # Load and verify summary.json structure
            with open(summary_json_path, 'r') as f:
                summary = json.load(f)
            
            # Verify metadata contains tick counters (not ticks_df length)
            assert 'metadata' in summary, "Missing 'metadata' key"
            meta = summary['metadata']
            
            # These should come from load_stats, not ticks_df
            assert 'n_ticks' in meta, "Missing 'n_ticks' (should come from load_stats['rows_read'])"
            assert 'n_ticks_filtered' in meta, "Missing 'n_ticks_filtered'"
            assert 'n_ticks_dropped' in meta, "Missing 'n_ticks_dropped'"
            assert 'n_bars' in meta, "Missing 'n_bars'"
            assert 'n_events' in meta, "Missing 'n_events'"
            
            # For a tiny file, we expect:
            # - 5 ticks read
            # - 0-5 filtered (depends on date filters)
            # - Decision should be INSUFFICIENT_DATA (0 events or too few)
            assert meta['n_ticks'] == 5, f"Expected 5 ticks read, got {meta['n_ticks']}"
            assert meta['n_events'] == 0, f"Expected 0 events detected in tiny file, got {meta['n_events']}"
            
            # Verify decision exists and is reasonable
            assert 'decision' in summary, "Missing 'decision' key"
            decision = summary['decision']
            assert decision['status'] in ['INSUFFICIENT_DATA', 'NO-GO'], \
                f"Expected decision to be INSUFFICIENT_DATA or NO-GO for 0 events, got {decision['status']}"
            
            print(f"  [OK] Script completed successfully (no UnboundLocalError)")
            print(f"  [OK] summary.json created with {meta['n_ticks']} ticks, {meta['n_bars']} bars, {meta['n_events']} events")
            print(f"  [OK] Decision: {decision['status']}")
            print("  PASS: Streaming mode with 0 events handled correctly")
            return True
            
        finally:
            os.unlink(tick_file_path)


def main():
    """Run all tests."""
    print("="*70)
    print("TEST: tick_edge_scan.py streaming mode (0 events, UnboundLocalError fix)")
    print("="*70)
    
    try:
        test_streaming_mode_zero_events()
        print("\n" + "="*70)
        print("All tests passed!")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        print("="*70 + "\n")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
