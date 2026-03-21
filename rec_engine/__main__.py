"""Recommendation engine CLI."""
import argparse
import asyncio
import sys


async def cmd_status(args):
    from rec_engine.sync import NASClient
    client = NASClient(args.nas_url, args.api_secret)
    status = await client.get_status()
    print(f"Last updated: {status.get('last_updated', 'never')}")
    print(f"Source: {status.get('source', 'none')}")
    print(f"Count: {status.get('count', 0)}")
    print(f"Model: {status.get('model', 'none')}")


async def cmd_run(args):
    from rec_engine.embedder import Embedder
    from rec_engine.scorer import Scorer
    from rec_engine.candidates import CandidateFetcher
    from rec_engine.sync import NASClient
    import uuid, yaml
    from pathlib import Path

    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    client = NASClient(args.nas_url, args.api_secret)
    model_name = args.model or config["models"]["preferred"]

    print(f"[1/5] Loading model: {model_name}")
    embedder = Embedder(config, model_override=model_name)

    print("[2/5] Fetching watch history and candidates...")
    history = await client.get_watch_history()
    subs = await client.get_subscriptions()
    fetcher = CandidateFetcher()
    candidates = await fetcher.fetch(history, subs)
    print(f"  {len(history)} watched, {len(candidates)} candidates")

    print("[3/5] Computing embeddings...")
    history_embeddings = embedder.embed_videos(history)
    candidate_embeddings = embedder.embed_videos(candidates)

    print("[4/5] Scoring candidates...")
    scorer = Scorer()
    profile = scorer.build_profile(history, history_embeddings)
    scored = scorer.score_candidates(
        candidates, candidate_embeddings, profile, history,
        limit=config.get("output_count", 100),
    )
    if scored:
        print(f"  Top score: {scored[0]['score']:.3f}, Bottom: {scored[-1]['score']:.3f}")
    else:
        print("  No candidates scored")

    print("[5/5] Syncing to NAS...")
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    result = await client.sync_recommendations(
        run_id, embedder.model_name,
        [{"id": v["id"], "score": v["score"], "reason": v.get("reason"),
          "title": v.get("title", ""), "channel_name": v.get("channel_name", ""),
          "channel_id": v.get("channel_id", ""), "view_count": v.get("view_count"),
          "duration": v.get("duration"), "published_at": v.get("published_at")}
         for v in scored],
    )
    print(f"  Synced {result['count']} recommendations")

    dl_result = await client.enqueue_downloads(
        [{"id": v["id"], "score": v["score"]} for v in scored],
        threshold=config.get("download_threshold", 0.7),
    )
    print(f"  Enqueued {dl_result['enqueued']} downloads")


def main():
    parser = argparse.ArgumentParser(prog="rec_engine", description="ShieldTube Recommendation Engine")
    parser.add_argument("--nas-url", required=True, help="NAS backend URL")
    parser.add_argument("--api-secret", default=None, help="API secret (or set SHIELDTUBE_API_SECRET)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Check recommendation status on NAS")

    run_parser = sub.add_parser("run", help="Full recommendation run")
    run_parser.add_argument("--model", default=None, help="Override model name")

    sub.add_parser("embed", help="Embed only (no scoring/sync)")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "embed":
        print("Embed-only mode not yet implemented")


if __name__ == "__main__":
    main()
