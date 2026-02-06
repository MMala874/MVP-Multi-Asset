import pandas as pd

df = pd.read_csv("outputs/research_dataset.csv")

event_cols = [
    "SWEEP_PREV_DAY_HIGH",
    "SWEEP_PREV_DAY_LOW",
    "IMPULSE_BODY",
    "RANGE_COMPRESSION",
    "VOL_REGIME_SHIFT",
]

print("ROWS:", len(df))

missing = [c for c in event_cols if c not in df.columns]
print("MISSING COLS:", missing)

any_event = df[event_cols].sum(axis=1) > 0

print("ROWS WITH ANY EVENT:", int(any_event.sum()))
print("PCT ANY EVENT:", float(any_event.mean()))
print("PCT ALL ZERO:", float((df[event_cols].sum(axis=1) == 0).mean()))

print("\nEVENT COUNTS:")
print(df[event_cols].sum().sort_values(ascending=False).to_string())
