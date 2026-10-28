import argparse
import asyncio
from pathlib import Path
from experiments.ar01_free_agent.harness import suite


def main():
    parser=argparse.ArgumentParser(description="AR01 deterministic local-only A/B comparison; no Provider construction")
    parser.add_argument("--output",type=Path,required=True,help="New output directory; never overwritten")
    args=parser.parse_args()
    result=asyncio.run(suite(args.output.resolve()))
    print(f"AR01 local suite: {len(result['results'])} pairs; real Provider NOT_RUN")
    if result["status"] != "LOCAL_DETERMINISTIC_VALIDATED":
        raise SystemExit(1)


if __name__=="__main__": main()
