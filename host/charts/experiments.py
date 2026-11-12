#!/usr/bin/env python3
"""Generate simple comparison charts for the LEX write-up / slides."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def load_csv(path: Path) -> dict[str, list[float]]:
    cols: dict[str, list[float]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k, v in row.items():
                cols.setdefault(k, []).append(float(v))
    return cols


def bar_compare(out: Path, title: str, labels: list[str], values: list[float], ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = ["#3dd6c6", "#f0b429", "#7aa2ff", "#ff6b4a"]
    ax.bar(labels, values, color=colors[: len(labels)])
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/experiments"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # Demo seed charts (replace with real logged means after experiments)
    bar_compare(
        args.out / "motion_onpath_vs_offpath.png",
        "CSI motion: on-path walk vs off-path stand",
        ["On path", "Off path", "Empty"],
        [0.82, 0.21, 0.08],
        "Mean motion score",
    )
    bar_compare(
        args.out / "modality_count_estimate.png",
        "People-count quality (1–2 person scene)",
        ["Camera", "CSI", "Phones"],
        [0.95, 0.35, 0.55],
        "Relative reliability (1 = best)",
    )
    bar_compare(
        args.out / "privacy_vs_accuracy.png",
        "Trade-off sketch for LEX discussion",
        ["CSI privacy", "CSI count", "Cam privacy", "Cam count", "Phone privacy", "Phone count"],
        [0.95, 0.35, 0.2, 0.9, 0.55, 0.5],
        "Score",
    )
    print(f"Wrote charts to {args.out.resolve()}")


if __name__ == "__main__":
    main()
