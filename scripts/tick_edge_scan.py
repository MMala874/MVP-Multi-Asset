#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tick-Level Edge Discovery on EURUSD
======================================

Input: MT5 tick export (CSV: time, bid, ask)
Process:
  1. Build 1-minute bars + tick-level features
  2. Detect compression events (tick_count, range, spread below percentiles, >=10min)
  3. For each event, compute forward metrics (5m/15m/30m)
  4. Summarize effect sizes + per-year stability
  5. GO/NO-GO decision

Output:
  - outputs/events.csv (one row per event)
  - outputs/summary.json (effect size, stability, decision)

No external paid libs. Vectorized numpy/pandas.
"""

import os
import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy import stats as sp_stats


def parse_args():
    parser = argparse.ArgumentParser(
        description="Tick-level edge discovery on EURUSD"
    )
    parser.add_argument(
        "--tick_file",
        type=str,
        default=None,
        help="Path to MT5 tick CSV (time, bid, ask). If None, generate synthetic.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs",
        help="Output directory for events.csv and summary.json",
    )
    parser.add_argument(
        "--bar_period_sec",
        type=int,
        default=60,
        help="Bar period in seconds (default 60 = 1min)",
    )
    parser.add_argument(
        "--compression_duration_min",
        type=int,
        default=10,
        help="Min duration for compression event in minutes",
    )
    parser.add_argument(
        "--tick_count_percentile",
        type=int,
        default=10,
        help="Percentile threshold for tick_count (lower = less active)",
    )
    parser.add_argument(
        "--range_percentile",
        type=int,
        default=10,
        help="Percentile threshold for tick range",
    )
    parser.add_argument(
        "--spread_percentile",
        type=int,
        default=20,
        help="Percentile threshold for spread_std",
    )
    parser.add_argument(
        "--assumed_spread_pips",
        type=float,
        default=1.0,
        help="Assumed spread in pips if ask column entirely missing (default 1.0)",
    )
    parser.add_argument(
        "--min_years_analyzed",
        type=int,
        default=5,
        help="Minimum years of data required (default 5)",
    )
    parser.add_argument(
        "--min_events_per_year",
        type=int,
        default=20,
        help="Minimum events per year required (default 20)",
    )
    parser.add_argument(
        "--lookback_window_days",
        type=int,
        default=2,
        help="Lookback window for percentile calculation (days)",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=2_000_000,
        help="Chunk size for streaming MT5 CSV read (default 2M rows)",
    )
    parser.add_argument(
        "--max_quote_age_ms",
        type=int,
        default=2000,
        help="Max age (ms) for quote reconstruction forward-fill (default 2000)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date filter YYYY-MM-DD (optional, applied while streaming)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date filter YYYY-MM-DD (optional, applied while streaming)",
    )
    parser.add_argument(
        "--progress_every_chunks",
        type=int,
        default=10,
        help="Print progress every N chunks (default 10)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output",
    )
    return parser.parse_args()


def parse_mt5_datetime(date_str, time_str):
    """
    Fast MT5 datetime parsing from DATE and TIME columns.
    Format: DATE="YYYY.MM.DD" TIME="HH:MM:SS.mmm"
    Returns: datetime or NaT
    """
    try:
        ts_str = f"{date_str} {time_str}"
        return pd.to_datetime(ts_str, format="%Y.%m.%d %H:%M:%S.%f", errors='raise')
    except (ValueError, TypeError):
        return pd.NaT


def reconstruct_quotes(bid_series, ask_series, time_series, max_quote_age_ms=2000, verbose=False):
    """
    Reconstruct BID/ASK for missing values using forward-fill with max age constraint.
    
    Args:
        bid_series, ask_series: pd.Series with NaN for missing updates
        time_series: pd.Series or DatetimeIndex of datetime
        max_quote_age_ms: max age in milliseconds for forward-fill
    
    Returns:
        (bid_reconstructed, ask_reconstructed, bid_ask_both_valid)
    """
    bid_recon = bid_series.copy()
    ask_recon = ask_series.copy()
    
    # Convert to Series if DatetimeIndex
    if not isinstance(time_series, pd.Series):
        time_series = pd.Series(time_series)
    
    last_bid = np.nan
    last_ask = np.nan
    last_bid_time = None
    last_ask_time = None
    
    bid_filled = 0
    ask_filled = 0
    skipped_stale = 0
    
    max_age_delta = timedelta(milliseconds=max_quote_age_ms)
    
    for i in range(len(bid_recon)):
        t = time_series.iloc[i]
        
        # Update last_bid if not NaN
        if not np.isnan(bid_recon.iloc[i]):
            last_bid = bid_recon.iloc[i]
            last_bid_time = t
        else:
            # Try to fill with last_bid if not too old
            if last_bid_time is not None and (t - last_bid_time) <= max_age_delta:
                bid_recon.iloc[i] = last_bid
                bid_filled += 1
        
        # Update last_ask if not NaN
        if not np.isnan(ask_recon.iloc[i]):
            last_ask = ask_recon.iloc[i]
            last_ask_time = t
        else:
            # Try to fill with last_ask if not too old
            if last_ask_time is not None and (t - last_ask_time) <= max_age_delta:
                ask_recon.iloc[i] = last_ask
                ask_filled += 1
            else:
                skipped_stale += 1
    
    # Create a boolean series indicating where both bid and ask are valid (not NaN)
    bid_ask_both_valid = (~bid_recon.isna()) & (~ask_recon.isna())
    
    if verbose:
        print(f"  Quote reconstruction: bid_filled={bid_filled}, ask_filled={ask_filled}, skipped_stale={skipped_stale}")
    
    return bid_recon, ask_recon, bid_ask_both_valid


def aggregate_ticks_to_minutes(chunk_df, verbose=False):
    """
    Stream-friendly 1-minute bar aggregation.
    
    Expects chunk_df with columns: timestamp, bid_recon, ask_recon, bid_ask_both_valid
    Returns: DataFrame with 1-minute aggregates
    """
    # Use timestamp if available, else time
    time_col = 'timestamp' if 'timestamp' in chunk_df.columns else 'time'
    bid_col = 'bid_recon' if 'bid_recon' in chunk_df.columns else 'bid'
    ask_col = 'ask_recon' if 'ask_recon' in chunk_df.columns else 'ask'
    
    # Floor time to minute
    chunk_df = chunk_df.copy()
    chunk_df['time_min'] = chunk_df[time_col].dt.floor('min')
    
    # Detailed aggregation
    minute_bars = []
    for time_min, group in chunk_df.groupby('time_min'):
        tick_count = len(group)
        
        bid_min = group[bid_col].min()
        bid_max = group[bid_col].max()
        bid_open = group[bid_col].iloc[0] if len(group) > 0 else np.nan
        bid_close = group[bid_col].iloc[-1] if len(group) > 0 else np.nan
        
        ask_min = group[ask_col].min()
        ask_max = group[ask_col].max()
        ask_open = group[ask_col].iloc[0] if len(group) > 0 else np.nan
        ask_close = group[ask_col].iloc[-1] if len(group) > 0 else np.nan
        
        # Mid prices
        mid_open = (bid_open + ask_open) / 2 if not (np.isnan(bid_open) or np.isnan(ask_open)) else np.nan
        mid_close = (bid_close + ask_close) / 2 if not (np.isnan(bid_close) or np.isnan(ask_close)) else np.nan
        
        # Spreads only where both bid and ask valid
        valid_mask = group.get('bid_ask_both_valid', True)
        if isinstance(valid_mask, bool):
            valid_mask = pd.Series(True, index=group.index)
        
        if valid_mask.sum() > 0:
            spreads = group.loc[valid_mask, ask_col] - group.loc[valid_mask, bid_col]
            spread_mean = spreads.mean()
            spread_std = spreads.std()
            n_valid_quotes = valid_mask.sum()
        else:
            spread_mean = np.nan
            spread_std = np.nan
            n_valid_quotes = 0
        
        minute_bars.append({
            'time': time_min,
            'tick_count': tick_count,
            'bid_open': bid_open,
            'bid_high': bid_max,
            'bid_low': bid_min,
            'bid_close': bid_close,
            'ask_open': ask_open,
            'ask_high': ask_max,
            'ask_low': ask_min,
            'ask_close': ask_close,
            'mid_open': mid_open,
            'mid_close': mid_close,
            'spread_mean': spread_mean,
            'spread_std': spread_std,
            'n_valid_quotes': n_valid_quotes,
        })
    
    return pd.DataFrame(minute_bars)


def load_ticks(tick_file, chunksize=2_000_000, max_quote_age_ms=2000, 
               start_date=None, end_date=None, progress_every_chunks=10, verbose=False):
    """
    Stream-friendly MT5 tick CSV loader for massive exports (15GB+).
    
    Format: TAB-separated columns <DATE> <TIME> <BID> <ASK> <LAST> <VOLUME> <FLAGS>
    DATE format: YYYY.MM.DD
    TIME format: HH:MM:SS.mmm
    
    Optimizations:
    - C-engine tab parsing (fast)
    - Pre-filter by DATE string before datetime parsing (avoids old years)
    - Fast datetime parsing (exact format, no fallback)
    - Quote reconstruction with max_quote_age_ms constraint
    - Chunked reading for memory efficiency
    
    Returns: (df_minute_bars, stats_dict)
    """
    start_time_total = datetime.now()
    
    if verbose:
        print(f"[MT5 Loader] Reading {tick_file}...")
        print(f"  Chunk size: {chunksize:,}, max_quote_age: {max_quote_age_ms}ms")
    
    # Convert date filters to string format (YYYY.MM.DD) for fast pre-filtering
    start_date_str = None
    end_date_str = None
    if start_date:
        start_date_str = pd.to_datetime(start_date).strftime('%Y.%m.%d')
    if end_date:
        end_date_str = pd.to_datetime(end_date).strftime('%Y.%m.%d')
    
    # Track stats
    total_rows_read = 0
    total_rows_processed = 0
    total_rows_filtered = 0
    total_minutes_built = 0
    nat_count = 0
    chunks_skipped = 0
    
    # Streaming minute bar aggregation
    all_minute_bars = []
    
    chunk_num = 0
    for chunk in pd.read_csv(
        tick_file,
        sep="\t",
        engine="c",
        header=0,
        chunksize=chunksize,
        na_values=[""],
        dtype={
            "<DATE>": "string",
            "<TIME>": "string",
            "<BID>": "float64",
            "<ASK>": "float64",
        },
    ):
        chunk_num += 1
        
        # Filter to required columns (handle case where <FLAGS> might be missing)
        required_cols = ["<DATE>", "<TIME>", "<BID>", "<ASK>"]
        optional_cols = ["<FLAGS>"]
        
        cols_to_keep = [c for c in required_cols if c in chunk.columns]
        cols_to_keep += [c for c in optional_cols if c in chunk.columns]
        
        if len(cols_to_keep) < len(required_cols):
            raise ValueError(f"Missing required columns. Required: {required_cols}, Found: {list(chunk.columns)}")
        
        chunk = chunk[cols_to_keep].copy()
        total_rows_read += len(chunk)
        
        # FAST PRE-FILTER: Skip chunks entirely before start_date or after end_date
        # This avoids parsing timestamps for entire years when user asks for --start 2024
        if start_date_str is not None or end_date_str is not None:
            chunk_min_date = chunk["<DATE>"].min()
            chunk_max_date = chunk["<DATE>"].max()
            
            # Skip chunk if entirely before start date
            if start_date_str is not None and chunk_max_date < start_date_str:
                chunks_skipped += 1
                if verbose and chunk_num % progress_every_chunks == 0:
                    print(f"  [Chunk {chunk_num}] Skipped (before {start_date_str}): "
                          f"{chunk_min_date} to {chunk_max_date}")
                continue
            
            # Break early if chunk is entirely after end date
            if end_date_str is not None and chunk_min_date > end_date_str:
                if verbose:
                    print(f"  [Chunk {chunk_num}] Breaking (past {end_date_str})")
                break
        
        # Immediately rename columns from <DATE> to DATE, etc.
        chunk.rename(columns={
            "<DATE>": "DATE",
            "<TIME>": "TIME",
            "<BID>": "BID",
            "<ASK>": "ASK",
            "<FLAGS>": "FLAGS",
        }, inplace=True)
        
        # Fast datetime parsing: DATE + " " + TIME with exact format
        chunk['timestamp'] = pd.to_datetime(
            chunk['DATE'].astype(str) + " " + chunk['TIME'].astype(str),
            format="%Y.%m.%d %H:%M:%S.%f",
            errors='coerce'
        )
        
        # Check for NaT (parsing failures)
        nat_mask = chunk['timestamp'].isna()
        nat_count += nat_mask.sum()
        
        if nat_mask.sum() > 0 and nat_mask.sum() / len(chunk) > 0.001:
            raise ValueError(f"Chunk {chunk_num}: NaT ratio > 0.1% (likely format mismatch)")
        
        # Drop NaT rows
        chunk = chunk[~nat_mask].copy()
        
        # Apply timestamp-based date filters (for rows within chunk date range)
        if start_date_str is not None:
            chunk = chunk[chunk['timestamp'] >= pd.to_datetime(start_date_str)]
        if end_date_str is not None:
            chunk = chunk[chunk['timestamp'] <= pd.to_datetime(end_date_str)]
        
        rows_after_filter = len(chunk)
        total_rows_filtered += rows_after_filter
        total_rows_processed += total_rows_read  # cumulative
        
        # Progress logging (happens immediately, not waiting for N chunks)
        if verbose:
            elapsed = (datetime.now() - start_time_total).total_seconds()
            rows_per_sec = total_rows_read / elapsed if elapsed > 0 else 0
            print(f"  [Chunk {chunk_num}] Read {total_rows_read:,} total, "
                  f"kept {total_rows_filtered:,}, {elapsed:.1f}s, {rows_per_sec:,.0f} rows/sec")
        
        if len(chunk) == 0:
            continue
        
        # Quote reconstruction: forward-fill with max age constraint
        bid_recon, ask_recon, bid_ask_valid = reconstruct_quotes(
            chunk['BID'], chunk['ASK'], chunk['timestamp'],
            max_quote_age_ms=max_quote_age_ms,
            verbose=False
        )
        
        chunk['bid_recon'] = bid_recon
        chunk['ask_recon'] = ask_recon
        chunk['bid_ask_both_valid'] = bid_ask_valid
        
        # 1-minute aggregation for this chunk
        chunk_minute_bars = aggregate_ticks_to_minutes(chunk, verbose=False)
        all_minute_bars.append(chunk_minute_bars)
        total_minutes_built += len(chunk_minute_bars)
    
    # Concatenate all minute bars and sort by time
    if not all_minute_bars:
        raise ValueError("No valid data processed from MT5 file")
    
    df_bars = pd.concat(all_minute_bars, ignore_index=True)
    df_bars = df_bars.sort_values('time').reset_index(drop=True)
    
    # Build realized vol from mid returns
    df_bars['mid'] = (df_bars['bid_open'] + df_bars['ask_open']) / 2
    df_bars['mid_return'] = df_bars['mid'].pct_change()
    df_bars['realized_vol'] = df_bars['mid_return'].abs().rolling(window=5, min_periods=1).mean()
    
    # Build micro range
    df_bars['micro_range'] = df_bars['bid_high'] - df_bars['bid_low']
    
    # Filter to rows with valid tick counts and spreads
    df_bars = df_bars[df_bars['tick_count'] > 0].copy()
    
    elapsed_total = (datetime.now() - start_time_total).total_seconds()
    
    stats = {
        'rows_read': total_rows_read,
        'rows_filtered': total_rows_filtered,
        'nat_dropped': nat_count,
        'chunks_skipped': chunks_skipped,
        'minutes_built': len(df_bars),
        'elapsed_sec': elapsed_total,
        'rows_per_sec': total_rows_read / elapsed_total if elapsed_total > 0 else 0,
        'date_range': (df_bars['time'].min(), df_bars['time'].max()),
    }
    
    if verbose:
        print(f"[MT5 Loader] Complete: {len(df_bars):,} minute bars")
        print(f"  Rows read: {stats['rows_read']:,}, Filtered to: {stats['rows_filtered']:,}, "
              f"NaT dropped: {stats['nat_dropped']}, Chunks skipped: {stats['chunks_skipped']}")
        print(f"  Elapsed: {elapsed_total:.2f}s ({stats['rows_per_sec']:,.0f} rows/sec)")
        print(f"  Date range: {stats['date_range'][0]} to {stats['date_range'][1]}")
    
    return df_bars, stats


def generate_synthetic_ticks(n_days=730, seed=42):
    """Generate synthetic MT5-like tick data for testing."""
    np.random.seed(seed)
    
    timestamps = pd.date_range(
        start='2023-01-01',
        periods=n_days,
        freq='D'
    )
    
    ticks_list = []
    base_price = 1.0900
    
    for day_idx, day in enumerate(timestamps):
        # Skip weekends
        if day.weekday() >= 5:
            continue
        
        # Generate 500-2000 ticks per day
        n_ticks_day = np.random.randint(500, 2000)
        
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        time_offsets = np.sort(np.random.randint(0, 86400, n_ticks_day))
        
        price = base_price + np.random.normal(0, 0.0005)
        
        for offset in time_offsets:
            tick_time = day_start + timedelta(seconds=int(offset))
            price += np.random.normal(0, 0.00005)
            bid = price
            ask = bid + np.random.choice([0.0001, 0.00015, 0.0002], p=[0.5, 0.3, 0.2])
            
            ticks_list.append({
                'time': tick_time,
                'bid': bid,
                'ask': ask,
            })
    
    df = pd.DataFrame(ticks_list)
    return df


def build_minute_bars(ticks_df, bar_period_sec=60, verbose=False):
    """
    Build 1-minute bars with tick-level features.
    
    Returns:
      df_bars with columns:
        time, bid_open, bid_close, bid_high, bid_low,
        tick_count, micro_range, spread_mean, spread_std,
        realized_vol (std of bid returns), bid_returns (list)
    """
    ticks_df = ticks_df.copy()
    
    # Set time as index for resampling
    ticks_df.set_index('time', inplace=True)
    
    # Resample to bar periods
    grouped = ticks_df.groupby(pd.Grouper(freq=f'{bar_period_sec}s'))
    
    bars_list = []
    
    for bar_time, group in grouped:
        if len(group) == 0:
            continue
        
        bid_prices = group['bid'].values
        ask_prices = group['ask'].values
        
        # OHLC
        bid_open = bid_prices[0]
        bid_close = bid_prices[-1]
        bid_high = bid_prices.max()
        bid_low = bid_prices.min()
        
        # Tick features
        tick_count = len(group)
        micro_range = bid_high - bid_low
        
        spread = ask_prices - bid_prices
        spread_mean = spread.mean()
        spread_std = spread.std()
        
        # Realized volatility (std of 1-tick returns)
        bid_returns = np.diff(bid_prices) / bid_prices[:-1]
        realized_vol = np.std(bid_returns) if len(bid_returns) > 0 else 0.0
        
        bars_list.append({
            'time': bar_time,
            'bid_open': bid_open,
            'bid_close': bid_close,
            'bid_high': bid_high,
            'bid_low': bid_low,
            'tick_count': tick_count,
            'micro_range': micro_range,
            'spread_mean': spread_mean,
            'spread_std': spread_std,
            'realized_vol': realized_vol,
        })
    
    df_bars = pd.DataFrame(bars_list)
    
    if verbose:
        print(f"Built {len(df_bars):,} minute bars from {len(ticks_df):,} ticks")
    
    return df_bars


def detect_compression_events(
    df_bars,
    tick_count_percentile=10,
    range_percentile=10,
    spread_percentile=20,
    lookback_window_days=2,
    compression_duration_min=10,
    verbose=False,
):
    """
    Detect compression events where:
      - tick_count < percentile
      - micro_range < percentile
      - spread_std < percentile
      - Duration >= compression_duration_min
    
    Returns:
      list of dict with event info (start_time, end_time, duration_min, etc.)
    """
    df_bars = df_bars.copy()
    lookback_bars = lookback_window_days * 24 * 60  # assume 1-min bars
    
    # Calculate rolling percentiles
    df_bars['tick_count_pct'] = df_bars['tick_count'].rolling(
        window=lookback_bars, min_periods=1
    ).apply(lambda x: sp_stats.percentileofscore(x, x.iloc[-1], kind='rank'), raw=False)
    
    df_bars['range_pct'] = df_bars['micro_range'].rolling(
        window=lookback_bars, min_periods=1
    ).apply(lambda x: sp_stats.percentileofscore(x, x.iloc[-1], kind='rank'), raw=False)
    
    df_bars['spread_std_pct'] = df_bars['spread_std'].rolling(
        window=lookback_bars, min_periods=1
    ).apply(lambda x: sp_stats.percentileofscore(x, x.iloc[-1], kind='rank'), raw=False)
    
    # Compression flag (all 3 conditions met)
    df_bars['compression'] = (
        (df_bars['tick_count_pct'] < tick_count_percentile) &
        (df_bars['range_pct'] < range_percentile) &
        (df_bars['spread_std_pct'] < spread_percentile)
    ).astype(int)
    
    # Identify contiguous compression blocks
    df_bars['compression_block'] = (
        (df_bars['compression'].diff() != 0).cumsum()
    )
    
    events = []
    for block_id, block_data in df_bars[df_bars['compression'] == 1].groupby('compression_block'):
        duration_min = len(block_data)
        
        if duration_min >= compression_duration_min:
            event = {
                'start_idx': block_data.index.min(),
                'end_idx': block_data.index.max(),
                'start_time': block_data['time'].iloc[0],
                'end_time': block_data['time'].iloc[-1],
                'duration_min': duration_min,
                'avg_tick_count': block_data['tick_count'].mean(),
                'avg_micro_range': block_data['micro_range'].mean(),
                'avg_spread_std': block_data['spread_std'].mean(),
            }
            events.append(event)
    
    if verbose:
        print(f"Detected {len(events)} compression events (>={compression_duration_min} min)")
    
    return events


def compute_forward_metrics(df_bars, event, horizon_min=[5, 15, 30]):
    """
    For a given event, compute forward returns/vol/spread over multiple horizons.
    Includes forward spread metrics for tradeability assessment.
    
    Returns:
      dict with forward metrics: forward_vol_5m, forward_range_5m, forward_spread_mean_5m, etc.
    """
    event_end_idx = event['end_idx']
    
    # Event entry point: one bar after event ends
    entry_idx = event_end_idx + 1
    
    if entry_idx >= len(df_bars):
        return None
    
    metrics = {
        'event_start_time': event['start_time'],
        'event_end_time': event['end_time'],
        'event_duration_min': event['duration_min'],
        'entry_time': df_bars.loc[entry_idx, 'time'],
        'entry_bid': df_bars.loc[entry_idx, 'bid_open'],
    }
    
    for h in horizon_min:
        end_idx = min(entry_idx + h, len(df_bars) - 1)
        horizon_bars = df_bars.loc[entry_idx:end_idx]
        
        if len(horizon_bars) < 2:
            metrics[f'forward_vol_{h}m'] = np.nan
            metrics[f'forward_range_{h}m'] = np.nan
            metrics[f'forward_return_mean_{h}m'] = np.nan
            metrics[f'forward_return_std_{h}m'] = np.nan
            metrics[f'forward_return_p95_{h}m'] = np.nan
            metrics[f'forward_spread_mean_{h}m'] = np.nan
            metrics[f'forward_spread_std_{h}m'] = np.nan
            continue
        
        # Forward volatility (realized vol in period)
        forward_vol = horizon_bars['realized_vol'].mean()
        metrics[f'forward_vol_{h}m'] = forward_vol
        
        # Forward range (max-min bid in period)
        bid_prices = horizon_bars['bid_close'].values
        forward_range = bid_prices.max() - bid_prices.min()
        metrics[f'forward_range_{h}m'] = forward_range
        
        # Forward returns (bid close-to-close)
        returns = np.diff(bid_prices) / bid_prices[:-1]
        metrics[f'forward_return_mean_{h}m'] = returns.mean()
        metrics[f'forward_return_std_{h}m'] = returns.std()
        metrics[f'forward_return_p95_{h}m'] = np.percentile(returns, 95) if len(returns) > 0 else np.nan
        
        # Forward spread metrics (tradeability)
        forward_spread_mean = horizon_bars['spread_mean'].mean()
        forward_spread_std = horizon_bars['spread_std'].mean()
        metrics[f'forward_spread_mean_{h}m'] = forward_spread_mean
        metrics[f'forward_spread_std_{h}m'] = forward_spread_std
    
    return metrics


def process_events(df_bars, events, verbose=False):
    """Compute forward metrics for all events."""
    results = []
    
    for event_idx, event in enumerate(events):
        fwd = compute_forward_metrics(df_bars, event)
        
        if fwd is not None:
            results.append(fwd)
    
    df_events = pd.DataFrame(results)
    
    if verbose:
        print(f"Computed forward metrics for {len(df_events)} valid events")
    
    return df_events


def compute_baseline(df_bars, events, max_horizon_min=30, verbose=False):
    """
    Compute baseline metrics excluding compression event windows and forward windows.
    
    This prevents contamination: events are removed before computing unconditional baseline.
    """
    df_bars_clean = df_bars.copy()
    
    # Mark bars to exclude: event windows + forward windows
    exclude_mask = np.zeros(len(df_bars_clean), dtype=bool)
    
    for event in events:
        event_start_idx = event['start_idx']
        event_end_idx = event['end_idx']
        forward_end_idx = min(event_end_idx + max_horizon_min, len(df_bars_clean) - 1)
        
        exclude_mask[event_start_idx:forward_end_idx+1] = True
    
    # Compute baseline only on non-excluded bars
    df_baseline = df_bars_clean[~exclude_mask]
    
    baseline = {
        'forward_vol_5m': df_baseline['realized_vol'].mean() if len(df_baseline) > 0 else 0.0,
        'forward_range_5m': (df_baseline['bid_high'] - df_baseline['bid_low']).mean() if len(df_baseline) > 0 else 0.0,
        'forward_spread_mean_5m': df_baseline['spread_mean'].mean() if len(df_baseline) > 0 else 0.0,
        'forward_return_mean_5m': 0.0,  # Neutral
    }
    
    if verbose:
        n_excluded = exclude_mask.sum()
        pct_excluded = (n_excluded / len(df_bars_clean) * 100) if len(df_bars_clean) > 0 else 0.0
        print(f"Baseline computed from {len(df_baseline):,} bars ({pct_excluded:.1f}% excluded due to events/forward windows)")
        print(f"  Baseline forward_vol: {baseline['forward_vol_5m']:.6f}")
    
    return baseline


def compute_effect_size(df_events, baseline, horizons=[5, 15, 30], verbose=False):
    """
    Compute effect size: ratio of post-event metrics to baseline.
    Includes spread metrics.
    
    Returns effect sizes and per-year stability.
    """
    if len(df_events) == 0:
        return None, None
    
    # Extract year from event times
    df_events['year'] = df_events['event_start_time'].dt.year
    years = sorted(df_events['year'].unique())
    
    effect_sizes = {}
    stability_per_year = {}
    
    for h in horizons:
        # Volatility ratio
        col = f'forward_vol_{h}m'
        if col in df_events.columns:
            post_event_vol = df_events[col].mean()
            baseline_vol = baseline.get(f'forward_vol_{h}m', 1.0)
            
            if baseline_vol > 0:
                effect_ratio = post_event_vol / baseline_vol
            else:
                effect_ratio = 1.0
            
            effect_sizes[f'vol_ratio_{h}m'] = effect_ratio
            
            # Per-year stability
            yearly_effects = []
            for year in years:
                year_data = df_events[df_events['year'] == year]
                if len(year_data) > 0:
                    year_effect = year_data[col].mean() / baseline_vol if baseline_vol > 0 else 1.0
                    yearly_effects.append({
                        'year': year,
                        'effect_ratio': year_effect,
                        'n_events': len(year_data),
                    })
            
            stability_per_year[f'vol_{h}m'] = yearly_effects
        
        # Spread ratio
        spread_col = f'forward_spread_mean_{h}m'
        if spread_col in df_events.columns:
            post_event_spread = df_events[spread_col].mean()
            baseline_spread = baseline.get(f'forward_spread_mean_{h}m', 1.0)
            
            if baseline_spread > 0:
                spread_ratio = post_event_spread / baseline_spread
            else:
                spread_ratio = 1.0
            
            effect_sizes[f'spread_ratio_{h}m'] = spread_ratio
    
    return effect_sizes, stability_per_year


def make_go_no_go_decision(effect_sizes, stability_per_year, min_years_analyzed=5, min_events_per_year=20, threshold_ratio=1.05, threshold_consistency=0.60):
    """
    GO/NO-GO decision based on:
      1. Sufficient data: years >= min_years_analyzed, all years have >= min_events_per_year
      2. Effect size consistency: >= threshold_consistency fraction of qualifying years
    
    Returns: decision dict with status, reasons, metadata
    """
    
    decision = {
        'status': 'PENDING',
        'reason': [],
        'effect_sizes': effect_sizes,
        'min_years_analyzed': min_years_analyzed,
        'min_events_per_year': min_events_per_year,
    }
    
    if not effect_sizes or not stability_per_year:
        decision['status'] = 'INSUFFICIENT_DATA'
        decision['reason'].append('No events detected')
        return decision
    
    # Check data sufficiency
    years_data = {}
    for metric, yearly_data in stability_per_year.items():
        if not yearly_data:
            continue
        
        n_years = len(yearly_data)
        years_data[metric] = {
            'n_years': n_years,
            'years': yearly_data,
        }
        
        # Check if any year has too few events
        years_below_threshold = [item for item in yearly_data if item['n_events'] < min_events_per_year]
        
        decision[f'{metric}_n_years'] = n_years
        decision[f'{metric}_min_events_per_year'] = min_events_per_year
        decision[f'{metric}_years_below_threshold'] = len(years_below_threshold)
        
        if n_years < min_years_analyzed:
            decision['status'] = 'INSUFFICIENT_DATA'
            decision['reason'].append(
                f"{metric}: Only {n_years} years analyzed (need {min_years_analyzed})"
            )
        
        if len(years_below_threshold) > 0:
            decision['status'] = 'INSUFFICIENT_DATA'
            threshold_years = [f"{item['year']}({item['n_events']})" for item in years_below_threshold]
            decision['reason'].append(
                f"{metric}: Years below {min_events_per_year} events: {', '.join(threshold_years)}"
            )
    
    # If insufficient data, return early
    if decision['status'] == 'INSUFFICIENT_DATA':
        return decision
    
    # Compute consistency on qualifying years only
    all_consistent = True
    
    for metric, yearly_data in (stability_per_year or {}).items():
        if not yearly_data:
            continue
        
        # Filter to years meeting min_events threshold
        qualifying_data = [item for item in yearly_data if item['n_events'] >= min_events_per_year]
        
        if not qualifying_data:
            decision['status'] = 'INSUFFICIENT_DATA'
            decision['reason'].append(f"{metric}: No years meet minimum event count")
            return decision
        
        n_qualifying = len(qualifying_data)
        n_positive = sum(1 for item in qualifying_data if item['effect_ratio'] > threshold_ratio)
        consistency = n_positive / n_qualifying if n_qualifying > 0 else 0.0
        
        decision[f'{metric}_consistency'] = consistency
        decision[f'{metric}_years_analyzed'] = n_qualifying
        decision[f'{metric}_years_positive'] = n_positive
        
        if consistency < threshold_consistency:
            all_consistent = False
    
    if all_consistent and len(effect_sizes) > 0:
        decision['status'] = 'GO'
        decision['reason'].append(
            f"Effect size consistent across years (>={threshold_consistency*100:.0f}% of qualifying years show effect)"
        )
    else:
        decision['status'] = 'NO-GO'
        decision['reason'].append(
            f"Effect size not consistent (<{threshold_consistency*100:.0f}% of qualifying years show effect)"
        )
    
    return decision


def main():
    args = parse_args()
    
    # Create output directory
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Initialize imputation metadata (for streaming mode compatibility)
    imputation_meta = {
        'ask_imputed_count': 0,
        'ask_imputed_ratio': 0.0,
        'median_spread_computed': None,
    }
    
    # Load ticks with MT5 streaming loader
    if args.tick_file and os.path.exists(args.tick_file):
        df_bars, load_stats = load_ticks(
            args.tick_file,
            chunksize=args.chunksize,
            max_quote_age_ms=args.max_quote_age_ms,
            start_date=args.start,
            end_date=args.end,
            progress_every_chunks=args.progress_every_chunks,
            verbose=args.verbose
        )
    else:
        if args.verbose:
            print("Generating synthetic tick data (no tick file provided)...")
        ticks_df = generate_synthetic_ticks(n_days=730)
        df_bars = build_minute_bars(ticks_df, bar_period_sec=args.bar_period_sec, verbose=args.verbose)
        load_stats = {
            'rows_read': len(ticks_df),
            'rows_filtered': len(ticks_df),
            'nat_dropped': 0,
            'chunks_skipped': 0,
            'minutes_built': len(df_bars),
            'elapsed_sec': 0,
            'rows_per_sec': 0,
            'date_range': (df_bars['time'].min(), df_bars['time'].max()),
        }
    
    # Detect compression events
    events = detect_compression_events(
        df_bars,
        tick_count_percentile=args.tick_count_percentile,
        range_percentile=args.range_percentile,
        spread_percentile=args.spread_percentile,
        lookback_window_days=args.lookback_window_days,
        compression_duration_min=args.compression_duration_min,
        verbose=args.verbose,
    )
    
    # Compute forward metrics
    df_events = process_events(df_bars, events, verbose=args.verbose)
    
    # Baseline (excluding event windows and forward windows)
    baseline = compute_baseline(df_bars, events, max_horizon_min=30, verbose=args.verbose)
    
    # Effect size + stability
    effect_sizes, stability_per_year = compute_effect_size(
        df_events, baseline, verbose=args.verbose
    )
    
    # Decision with stability gating
    decision = make_go_no_go_decision(
        effect_sizes,
        stability_per_year,
        min_years_analyzed=args.min_years_analyzed,
        min_events_per_year=args.min_events_per_year,
    )
    
    # Save events.csv
    events_csv_path = os.path.join(args.output_dir, 'events.csv')
    if len(df_events) > 0:
        df_events.to_csv(events_csv_path, index=False)
        if args.verbose:
            print(f"Saved events to {events_csv_path}")
    
    # Save summary.json with all metadata
    # Use load_stats for tick counts (works in streaming and synthetic mode)
    summary = {
        'metadata': {
            'n_ticks': load_stats['rows_read'],
            'n_ticks_filtered': load_stats['rows_filtered'],
            'n_ticks_dropped': load_stats['nat_dropped'],
            'n_bars': len(df_bars),
            'n_events': len(df_events),
            'ask_imputed_ratio': imputation_meta['ask_imputed_ratio'],
            'date_range': {
                'start': str(load_stats['date_range'][0]) if len(df_bars) > 0 else None,
                'end': str(load_stats['date_range'][1]) if len(df_bars) > 0 else None,
            },
        },
        'parameters': {
            'bar_period_sec': args.bar_period_sec,
            'compression_duration_min': args.compression_duration_min,
            'tick_count_percentile': args.tick_count_percentile,
            'range_percentile': args.range_percentile,
            'spread_percentile': args.spread_percentile,
            'lookback_window_days': args.lookback_window_days,
            'min_years_analyzed': args.min_years_analyzed,
            'min_events_per_year': args.min_events_per_year,
            'assumed_spread_pips': args.assumed_spread_pips,
        },
        'imputation': imputation_meta,
        'baseline': baseline,
        'effect_sizes': effect_sizes,
        'stability_per_year': stability_per_year,
        'decision': decision,
    }
    
    summary_json_path = os.path.join(args.output_dir, 'summary.json')
    with open(summary_json_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    if args.verbose:
        print(f"Saved summary to {summary_json_path}")
    
    # Print results
    print("\n" + "="*70)
    print("TICK-LEVEL EDGE DISCOVERY - RESULTS")
    print("="*70)
    if len(df_bars) > 0:
        print(f"\nData: {load_stats['rows_read']:,} ticks -> {load_stats['rows_filtered']:,} kept -> {len(df_bars):,} bars")
        print(f"Events detected: {len(df_events)}")
        print(f"Date range: {load_stats['date_range'][0]} to {load_stats['date_range'][1]}")
    else:
        print("\nNo data processed")
    
    if imputation_meta['ask_imputed_ratio'] > 0:
        print(f"\nAsk imputation: {imputation_meta['ask_imputed_ratio']:.1%} of ticks")
        if imputation_meta['median_spread_computed'] is not None:
            print(f"  Median spread: {imputation_meta['median_spread_computed']:.5f}")
    
    print("\nBaseline (unconditional forward metrics, events excluded):")
    for k, v in baseline.items():
        print(f"  {k}: {v:.6f}")
    
    print("\nEffect sizes (ratio post-event / baseline):")
    for k, v in (effect_sizes or {}).items():
        print(f"  {k}: {v:.3f}")
    
    print("\nStability per year (qualifying years only):")
    for metric, yearly_data in (stability_per_year or {}).items():
        print(f"\n  {metric}:")
        for item in yearly_data:
            ratio_str = f"{item['effect_ratio']:.3f}"
            print(
                f"    Year {item['year']}: ratio={ratio_str}, "
                f"n_events={item['n_events']}"
            )
    
    print("\n" + "="*70)
    print(f"DECISION: {decision['status']}")
    print("="*70)
    for reason in decision.get('reason', []):
        print(f"  • {reason}")
    
    for metric in [k for k in decision.keys() if 'consistency' in k]:
        val = decision[metric]
        print(f"  {metric}: {val:.2%}")
    
    print("\nOutput files:")
    print(f"  • {events_csv_path}")
    print(f"  • {summary_json_path}")
    print("="*70 + "\n")
    
    return decision['status']


if __name__ == '__main__':
    status = main()
    sys.exit(0 if status == 'GO' else 1)
