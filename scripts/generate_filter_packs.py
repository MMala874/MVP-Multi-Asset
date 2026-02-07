from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_packs() -> list[dict]:
    packs: list[dict] = []

    def add(name: str, cfg: dict) -> None:
        packs.append({"name": name, "filters": cfg})

    add("london_only", {"london": True})

    for atr in [1.0, 1.1, 1.2, 1.3]:
        add(f"london_highvol_{atr}", {"london": True, "high_vol": {"min_atr_ratio": atr}})

    for z in [0.4, 0.5, 0.7, 1.0]:
        add(f"london_near_pdh_{z}", {"london": True, "near_pdh": {"max_dist_z": z}})
        add(f"london_near_pdl_{z}", {"london": True, "near_pdl": {"max_dist_z": z}})

    for lo, hi in [(0.2, 0.8), (0.3, 0.7), (0.35, 0.65)]:
        add(f"london_position_{lo}_{hi}", {"london": True, "position": {"lo": lo, "hi": hi}})

    for atr in [1.1, 1.2]:
        for z in [0.5, 0.7]:
            add(
                f"london_hv_{atr}_pdh_{z}",
                {"london": True, "high_vol": {"min_atr_ratio": atr}, "near_pdh": {"max_dist_z": z}},
            )
            add(
                f"london_hv_{atr}_pdl_{z}",
                {"london": True, "high_vol": {"min_atr_ratio": atr}, "near_pdl": {"max_dist_z": z}},
            )

    for atr in [1.1, 1.2]:
        for lo, hi in [(0.2, 0.8), (0.3, 0.7)]:
            add(
                f"london_hv_{atr}_pos_{lo}_{hi}",
                {"london": True, "high_vol": {"min_atr_ratio": atr}, "position": {"lo": lo, "hi": hi}},
            )

    for q in [0.0, -0.25]:
        add(f"london_compression_{q}", {"london": True, "compression": {"max_vol_z20": q}})
        add(
            f"london_hv11_compression_{q}",
            {"london": True, "high_vol": {"min_atr_ratio": 1.1}, "compression": {"max_vol_z20": q}},
        )

    for r2 in [0.15, 0.2, 0.3]:
        add(f"london_trendq_{r2}", {"london": True, "trend_quality": {"min_reg_r2_20": r2}})
        add(
            f"london_hv11_trendq_{r2}",
            {"london": True, "high_vol": {"min_atr_ratio": 1.1}, "trend_quality": {"min_reg_r2_20": r2}},
        )

    dedup: dict[str, dict] = {}
    for p in packs:
        dedup[p["name"]] = p
    return list(dedup.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a smart grid of event regime filter packs")
    parser.add_argument("--out", default="outputs/filter_packs.json")
    args = parser.parse_args()

    packs = build_packs()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packs, indent=2), encoding="utf-8")
    print(f"Saved {len(packs)} packs to {out}")


if __name__ == "__main__":
    main()
