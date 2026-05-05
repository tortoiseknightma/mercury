import subprocess
import json
import statistics
from pathlib import Path

def run_cmd(cmd: str):
    print(f"\n> {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def main():
    metrics_path = Path("results/metrics_evolved.json")
    library_dir = Path("src/mercury/skills/library")
    
    pass_rates = []
    avg_tokens = []
    verified_skills_counts = []

    for i in range(1):
        print(f"\n======================================")
        print(f"         BENCHMARK RUN {i+1} / 3        ")
        print(f"======================================")
        
        # Reset state and skills
        run_cmd("uv run mercury reset")
        
        # Run baseline
        run_cmd("uv run mercury bench --mode baseline")
        
        # Run evolve
        run_cmd("uv run mercury evolve")
        
        # Run evolved benchmark
        run_cmd("uv run mercury bench --mode evolved")
        
        # Read metrics
        if not metrics_path.exists():
            print(f"ERROR: {metrics_path} not found!")
            continue
            
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        pass_rate = data.get("pass_at_1", 0.0)
        tokens = data.get("avg_tokens", 0.0)
        pass_rates.append(pass_rate)
        avg_tokens.append(tokens)
        
        # Count verified skills
        verified_skills = 0
        if library_dir.exists():
            for d in library_dir.iterdir():
                if d.is_dir() and not d.name.startswith("_"):
                    skill_md = d / "SKILL.md"
                    if skill_md.exists():
                        with open(skill_md, "r", encoding="utf-8") as f:
                            if "status: verified" in f.read():
                                verified_skills += 1
                                
        verified_skills_counts.append(verified_skills)
        
        print(f"--- RUN {i+1} RESULTS ---")
        print(f"Pass@1: {pass_rate*100:.2f}%")
        print(f"Avg Tokens: {tokens:.1f}")
        print(f"Verified Skills: {verified_skills}")
        
    print(f"\n======================================")
    print(f"            FINAL SUMMARY             ")
    print(f"======================================")
    
    if len(pass_rates) > 1:
        pass_variance = statistics.variance(pass_rates)
        token_variance = statistics.variance(avg_tokens)
        token_mean = statistics.mean(avg_tokens)
        
        # Calculate Coefficient of Variation for tokens (std_dev / mean) as a percentage
        token_cv = (statistics.stdev(avg_tokens) / token_mean) * 100 if token_mean else 0
        
        print(f"Pass@1 values: {[f'{p*100:.2f}%' for p in pass_rates]}")
        print(f"Pass@1 Variance: {pass_variance:.6f}")
        
        print(f"Avg Tokens values: {[f'{t:.1f}' for t in avg_tokens]}")
        print(f"Tokens Variance: {token_variance:.1f}")
        print(f"Tokens CV (StdDev/Mean): {token_cv:.2f}%")
        
        print(f"Verified Skills counts: {verified_skills_counts}")
        
        if token_cv < 8.0:
            print("[PASS] Variance is < 8%")
        else:
            print("[FAIL] Variance is >= 8%")
            
        if all(count >= 5 for count in verified_skills_counts):
            print("[PASS] Verified skills >= 5")
        else:
            print("[FAIL] Not all runs produced >= 5 verified skills")
    else:
        print("Only 1 run performed. Verified Skills count:", verified_skills_counts[0])

if __name__ == "__main__":
    main()
