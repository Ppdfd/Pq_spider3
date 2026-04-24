import json
import os
from pathlib import Path

class DataLoader:
    """
    Centralized utility for handling simulation data and performance metrics.
    Standardizes directory structures:
        - Results: {phase}/results/ours_metrics.json
        - Simulation Data: {phase}/output/{filename}.json
    """

    @staticmethod
    def _ensure_dir(path: Path):
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save_metrics(phase_dir: Path, metrics: dict, filename="ours_metrics.json"):
        """Saves performance metrics (latencies) to the results/ folder."""
        results_dir = phase_dir / "results"
        DataLoader._ensure_dir(results_dir)
        filepath = results_dir / filename
        with open(filepath, "w") as f:
            json.dump(metrics, f, indent=4)
        print(f"  -> Metrics saved: {filepath.relative_to(Path.cwd()) if filepath.is_relative_to(Path.cwd()) else filepath}")

    @staticmethod
    def save_data(phase_dir: Path, filename: str, data: any):
        """Saves simulation data (keys, packets, etc.) to the output/ folder."""
        output_dir = phase_dir / "output"
        DataLoader._ensure_dir(output_dir)
        filepath = output_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
        print(f"  -> Data saved: {filepath.relative_to(Path.cwd()) if filepath.is_relative_to(Path.cwd()) else filepath}")

    @staticmethod
    def load_data(phase_dir: Path, filename: str):
        """Loads simulation data from the output/ folder of a specific phase."""
        filepath = phase_dir / "output" / filename
        if not filepath.exists():
            raise FileNotFoundError(f"\nError: {filepath} not found. Please ensure the previous phase simulation has been run.")
        with open(filepath, "r") as f:
            return json.load(f)

    @staticmethod
    def load_metrics(phase_dir: Path, filename="ours_metrics.json"):
        """Loads performance metrics from the results/ folder of a specific phase."""
        filepath = phase_dir / "results" / filename
        if not filepath.exists():
            return None
        with open(filepath, "r") as f:
            return json.load(f)
