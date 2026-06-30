"""Bunshin CLI."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from bunshin.ingestion.claude_history import import_claude_history
from bunshin.ingestion.claude_memory import import_claude_memory
from bunshin.ingestion.files import DEFAULT_EXTENSIONS, import_files
from bunshin.storage import (
    DEFAULT_DB_PATH,
    count_records,
    count_short_records,
    count_vectors,
    delete_short_records,
    get_records_without_vectors,
    init_db,
    init_vector_db,
    insert_vector,
    list_sources_with_counts,
)


console = Console()


@click.group()
@click.version_option(version=__import__("bunshin").__version__)
def main():
    """分身（Bunshin）— Personal memory engine."""


@main.command("init")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def init_cmd(db: Path):
    """Initialize the Bunshin database."""
    conn = init_db(db)
    conn.close()
    console.print(f"[green]OK[/green] Initialized database at [cyan]{db}[/cyan]")


@main.command("import-claude")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.home() / ".claude" / "projects",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
@click.option("--verbose", "-v", is_flag=True, help="Print each file as it is processed")
def import_claude_cmd(path: Path, db: Path, verbose: bool):
    """Import Claude Code transcript history."""
    conn = init_db(db)
    console.print(f"Scanning [cyan]{path}[/cyan] for transcript .jsonl files...")
    stats = import_claude_history(conn, path, verbose=verbose)

    table = Table(title="Claude history import results")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Files scanned", str(stats["files_scanned"]))
    table.add_row("Lines parsed", str(stats.get("lines_parsed", 0)))
    table.add_row("Records inserted", str(stats["records_inserted"]))
    table.add_row("Records skipped (dup)", str(stats.get("records_skipped", 0)))
    table.add_row("Files failed to read", str(stats["files_failed"]))
    console.print(table)

    conn.close()


@main.command("import-claude-memory")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.home() / ".claude" / "projects",
)
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB_PATH,
              help="Database file path")
@click.option("--force", is_flag=True, help="Reimport all files regardless of mtime")
@click.option("--verbose", "-v", is_flag=True, help="Print each file as it is processed")
def import_claude_memory_cmd(path: Path, db: Path, force: bool, verbose: bool):
    """Import Claude Code's auto-memory notes (~/.claude/projects/*/memory/*.md).

    These are the long-lived observations Claude writes about your projects,
    preferences, and feedback — the same notes that appear in the system
    prompt as "auto-memory". Importing them lets Bunshin find them via
    search / chat / MCP.
    """
    conn = init_db(db)
    console.print(f"Scanning [cyan]{path}[/cyan] for memory/*.md notes...")
    stats = import_claude_memory(conn, path, force=force, verbose=verbose)
    table = Table(title="Claude memory import results")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Files scanned", str(stats["files_scanned"]))
    table.add_row("Files unchanged", str(stats["files_unchanged"]))
    table.add_row("Files reimported", str(stats["files_reimported"]))
    table.add_row("Records inserted", str(stats["records_inserted"]))
    table.add_row("Files skipped (empty)", str(stats["files_skipped_empty"]))
    console.print(table)
    conn.close()


@main.command("re-describe-all")
@click.option("--host", default="127.0.0.1", help="Bunshin web host")
@click.option("--port", default=8000, type=int, help="Bunshin web port")
@click.option("--limit", default=0, type=int,
              help="Cap how many entities to refresh (0 = all)")
@click.option("--min-mentions", default=2, type=int,
              help="Skip entities with fewer than N mentions (1-mention noise)")
@click.option("--skip-existing", is_flag=True,
              help="Skip entities that already have a description")
def re_describe_all_cmd(host: str, port: int, limit: int,
                         min_mentions: int, skip_existing: bool):
    """Refresh AI descriptions for all entities (top-N by mentions).

    Bunshin web (or the desktop app) must be running on the given
    host:port. Each entity takes 30-60s; 137 entities ≈ 1-2 hours.
    Safe to leave overnight — progress is printed line by line so
    you can ^C and resume by re-running with --skip-existing.
    """
    import time as _time
    import urllib.request
    import urllib.parse
    base = f"http://{host}:{port}"
    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as r:
            health = json.loads(r.read())
        console.print(f"[green]✓[/green] Connected to Bunshin v{health.get('version','?')}")
    except Exception as e:
        console.print(f"[red]✗ Bunshin web is not reachable at {base}[/red]: {e}")
        console.print("  → Open Bunshin.app or run [cyan]bunshin web[/cyan] first.")
        return
    qs = urllib.parse.urlencode({"limit": 500})
    with urllib.request.urlopen(f"{base}/api/entities?{qs}", timeout=15) as r:
        data = json.loads(r.read())
    entities = data.get("entities", [])
    entities.sort(key=lambda e: -(e.get("mentions") or 0))
    eligible = [
        e for e in entities
        if (e.get("mentions") or 0) >= min_mentions
        and not (skip_existing and (e.get("description") or "").strip())
    ]
    if limit > 0:
        eligible = eligible[:limit]
    console.print(
        f"[cyan]Refreshing {len(eligible)} entities[/cyan] "
        f"(skipped: {len(entities) - len(eligible)}, "
        f"avg ~45s each, total ~{len(eligible) * 45 // 60} min)"
    )
    ok = err = 0
    started = _time.time()
    for i, ent in enumerate(eligible, 1):
        eid = ent["id"]
        name = ent.get("name", "?")
        t0 = _time.time()
        try:
            req = urllib.request.Request(
                f"{base}/api/entities/{eid}/describe",
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read())
            elapsed = _time.time() - t0
            judge = body.get("judge", "?")
            desc_preview = (body.get("description") or "")[:60].replace("\n", " ")
            console.print(
                f"  [green]✓[/green] [{i:3d}/{len(eligible)}] "
                f"[bold]{name}[/bold] ({elapsed:.0f}s · {judge}) — {desc_preview}…"
            )
            ok += 1
        except Exception as e:
            console.print(
                f"  [red]✗[/red] [{i:3d}/{len(eligible)}] {name}: {e}"
            )
            err += 1
    total = _time.time() - started
    console.print(
        f"\n[bold]Done[/bold]: {ok} OK / {err} failed in {total/60:.1f} min"
    )


@main.command("merge-entities")
@click.argument("source")
@click.argument("target")
@click.option("--dry-run", is_flag=True,
              help="Show what would be merged without changing anything.")
def merge_entities_cmd(source: str, target: str, dry_run: bool):
    """Merge entity SOURCE into TARGET. Both can be IDs or exact names.

    All record_entities rows pointing at SOURCE are rewritten to TARGET,
    then SOURCE is deleted. Useful for collapsing duplicates like
    「分身」 + 「Bunshin」 that NER pulled out as two entities.

    The merged entity keeps TARGET's name, type, and description, but
    inherits SOURCE's mention rows so search hits stay intact.

    Example:
      bunshin merge-entities "Bunshin" "分身"
      bunshin merge-entities 137 22 --dry-run
    """
    import sqlite3
    from bunshin.storage import init_db
    conn = init_db()
    conn.row_factory = sqlite3.Row
    try:
        def resolve(spec: str):
            if spec.isdigit():
                row = conn.execute(
                    "SELECT id, name, type FROM entities WHERE id = ?", (int(spec),)
                ).fetchone()
                if row:
                    return {"id": row["id"], "name": row["name"], "type": row["type"]}
            row = conn.execute(
                "SELECT id, name, type FROM entities WHERE name = ?", (spec,)
            ).fetchone()
            return {"id": row["id"], "name": row["name"], "type": row["type"]} if row else None

        src = resolve(source)
        tgt = resolve(target)
        if not src:
            console.print(f"[red]✗ source entity not found:[/red] {source}")
            return
        if not tgt:
            console.print(f"[red]✗ target entity not found:[/red] {target}")
            return
        if src["id"] == tgt["id"]:
            console.print("[yellow]source and target are the same entity — nothing to do[/yellow]")
            return

        # Count what's about to move.
        n_rows = conn.execute(
            "SELECT COUNT(*) FROM record_entities WHERE entity_id = ?",
            (src["id"],),
        ).fetchone()[0]
        # Records already linked to BOTH (would dup if we just moved).
        n_conflict = conn.execute(
            "SELECT COUNT(*) FROM record_entities re "
            "WHERE re.entity_id = ? "
            "AND EXISTS (SELECT 1 FROM record_entities re2 "
            "            WHERE re2.entity_id = ? AND re2.record_id = re.record_id)",
            (src["id"], tgt["id"]),
        ).fetchone()[0]
        n_move = n_rows - n_conflict

        console.print(
            f"[cyan]Merge plan:[/cyan]\n"
            f"  source:  #{src['id']} {src['name']!r} ({src.get('type','?')})\n"
            f"  target:  #{tgt['id']} {tgt['name']!r} ({tgt.get('type','?')})\n"
            f"  rewrite: {n_move} record_entities rows  (drop {n_conflict} dup, total {n_rows})\n"
            f"  delete:  entities row #{src['id']}\n"
        )
        if dry_run:
            console.print("[yellow]--dry-run: no changes made[/yellow]")
            return
        # Drop conflicts first to satisfy the UNIQUE (record_id, entity_id) constraint.
        with conn:
            conn.execute(
                "DELETE FROM record_entities "
                "WHERE entity_id = ? "
                "AND EXISTS (SELECT 1 FROM record_entities re2 "
                "            WHERE re2.entity_id = ? AND re2.record_id = record_entities.record_id)",
                (src["id"], tgt["id"]),
            )
            conn.execute(
                "UPDATE record_entities SET entity_id = ? WHERE entity_id = ?",
                (tgt["id"], src["id"]),
            )
            # Carry co-occurrence edges if the table exists.
            try:
                conn.execute(
                    "UPDATE OR IGNORE entity_relations SET a_id = ? WHERE a_id = ?",
                    (tgt["id"], src["id"]),
                )
                conn.execute(
                    "UPDATE OR IGNORE entity_relations SET b_id = ? WHERE b_id = ?",
                    (tgt["id"], src["id"]),
                )
                conn.execute(
                    "DELETE FROM entity_relations WHERE a_id = b_id"
                )
                conn.execute(
                    "DELETE FROM entity_relations WHERE a_id = ? OR b_id = ?",
                    (src["id"], src["id"]),
                )
            except Exception:
                pass
            conn.execute("DELETE FROM entities WHERE id = ?", (src["id"],))
        console.print(
            f"[green]✓[/green] merged #{src['id']} → #{tgt['id']} "
            f"({n_move} rows moved, {n_conflict} duplicates dropped)"
        )
    finally:
        conn.close()


@main.command("find-duplicates")
@click.option("--limit", default=30, type=int,
              help="Max duplicate groups to show.")
@click.option("--min-mentions", default=1, type=int,
              help="Skip entities with fewer than N mentions.")
def find_duplicates_cmd(limit: int, min_mentions: int):
    """Find candidate-duplicate entities (NER variants of the same thing).

    Two entities are considered candidates when their names normalize to
    the same string. Normalization strips whitespace, parenthesized
    suffixes ("MARINE FLIGHT（主催ブランド名）" → "MARINE FLIGHT"),
    case, and a few common punctuation marks.

    Prints a ready-to-paste `bunshin merge-entities <source> <target>`
    line for each group, with the most-mentioned entity as TARGET.

    Read the suggestions, then run the merge commands you agree with.
    """
    import re as _re
    import sqlite3
    from bunshin.storage import init_db
    conn = init_db()
    conn.row_factory = sqlite3.Row

    def _normalize(name: str) -> str:
        if not name:
            return ""
        # Strip parenthesized suffix groups (both ASCII and 全角)
        s = _re.sub(r"\s*[（(].*?[)）]\s*", "", name)
        # Strip leading/trailing whitespace, lowercase, drop common punctuation
        s = s.strip().lower()
        s = _re.sub(r"[ \t/・,，、:：·]", "", s)
        return s

    try:
        rows = conn.execute(
            "SELECT e.id, e.name, e.type, "
            "       (SELECT COUNT(*) FROM record_entities re WHERE re.entity_id = e.id) AS mentions "
            "FROM entities e"
        ).fetchall()
        groups: dict[str, list[dict]] = {}
        for r in rows:
            mentions = r["mentions"] or 0
            if mentions < min_mentions:
                continue
            key = _normalize(r["name"])
            if not key or len(key) < 2:
                continue
            groups.setdefault(key, []).append({
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "mentions": mentions,
            })
        dup_groups = [g for g in groups.values() if len(g) >= 2]
        # Sort: groups with the highest single-entity mention count first
        dup_groups.sort(key=lambda g: -max(e["mentions"] for e in g))
        if not dup_groups:
            console.print("[green]No duplicate-candidate entities found.[/green]")
            return
        console.print(f"[cyan]{len(dup_groups)} duplicate-candidate group(s):[/cyan]\n")
        for i, group in enumerate(dup_groups[:limit], 1):
            # Most mentions wins; tie-break on shorter name (the "cleaner"
            # canonical form — "ホークす" over "ホークす(海外帰りの模索日記)").
            group.sort(key=lambda e: (-e["mentions"], len(e["name"] or "")))
            target = group[0]
            console.print(f"[bold]{i}.[/bold]  ({len(group)} entities, normalized: {_normalize(group[0]['name'])!r})")
            for e in group:
                marker = "→ " if e is target else "  "
                console.print(
                    f"  {marker}#{e['id']:4d}  {e['name']!r:40s} "
                    f"({e['type'] or '?':12s}, {e['mentions']:5d} mentions)"
                )
            for e in group[1:]:
                console.print(
                    f"     [yellow]$ bunshin merge-entities {e['id']} {target['id']} --dry-run[/yellow]"
                )
            console.print()
        if len(dup_groups) > limit:
            console.print(
                f"[dim]... and {len(dup_groups) - limit} more "
                f"(pass --limit {len(dup_groups)} to see all)[/dim]"
            )
    finally:
        conn.close()


@main.command("status")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def status_cmd(db: Path):
    """Show database stats."""
    if not db.exists():
        console.print(
            f"[red]No database found at {db}. Run [bold]bunshin init[/bold] first.[/red]"
        )
        return

    conn = init_db(db)
    total = count_records(conn)

    table = Table(title=f"分身 status — {db}")
    table.add_column("Source", style="cyan")
    table.add_column("Records", justify="right")
    for source, count in list_sources_with_counts(conn):
        table.add_row(source, str(count))
    table.add_row("[bold]Total records[/bold]", f"[bold]{total}[/bold]")

    try:
        init_vector_db(conn)
        vcount = count_vectors(conn)
        table.add_row("[bold]Embeddings[/bold]", f"[bold]{vcount}[/bold]")
    except Exception as e:
        table.add_row("[bold]Embeddings[/bold]", f"[red]error: {e}[/red]")

    console.print(table)
    conn.close()


@main.command("embed")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
@click.option("--batch-size", default=32, help="Batch size for embedding")
def embed_cmd(db: Path, batch_size: int):
    """Generate embeddings for all records that don't have one yet."""
    from bunshin.embeddings import DIMENSIONS, embed_passages

    conn = init_db(db)
    init_vector_db(conn, dimensions=DIMENSIONS)

    pending = get_records_without_vectors(conn)
    if not pending:
        console.print("[yellow]No records to embed (all up to date).[/yellow]")
        conn.close()
        return

    console.print(
        f"Embedding [bold]{len(pending)}[/bold] records "
        f"(first run downloads ~120 MB model, then ~30s for {len(pending)} records)..."
    )

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding", total=len(pending))
        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            ids = [r[0] for r in batch]
            texts = [r[1] for r in batch]
            embeddings = list(embed_passages(texts))
            for rec_id, emb in zip(ids, embeddings):
                insert_vector(conn, rec_id, emb)
            conn.commit()
            progress.update(task, advance=len(batch))

    console.print(f"[green]OK[/green] Embedded {len(pending)} records.")
    conn.close()


@main.command("search")
@click.argument("query", type=str)
@click.option("--limit", "-n", default=5, help="Max results")
@click.option("--full", is_flag=True, help="Show full content (no truncation)")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def search_cmd(query: str, limit: int, full: bool, db: Path):
    """Search records by semantic similarity."""
    from bunshin.search import search as do_search

    if not db.exists():
        console.print(f"[red]No database at {db}. Run [bold]bunshin init[/bold] first.[/red]")
        return

    conn = init_db(db)
    results = do_search(conn, query, limit=limit)
    conn.close()

    if not results:
        console.print(
            "[yellow]No results.[/yellow] "
            "Did you run [bold]bunshin embed[/bold]?"
        )
        return

    console.print(f"\n[bold]'{query}'[/bold] の検索結果（{len(results)}件）\n")
    for i, r in enumerate(results, 1):
        ts = (
            datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M")
            if r["timestamp"]
            else "n/a"
        )
        role = (r["metadata"] or {}).get("role", "?")
        console.print(
            f"[bold cyan]#{i}[/bold cyan] "
            f"[dim]{ts} | {r['source']}/{role} | "
            f"distance={r['distance']:.3f}[/dim]"
        )
        content = r["content"]
        if not full and len(content) > 300:
            content = content[:300] + "..."
        console.print(content)
        console.print()


@main.command("watch")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=lambda: Path.home() / "Documents",
)
@click.option("--ext", multiple=True, help="File extensions to watch (default: same as import-files)")
@click.option("--idle", default=3.0, help="Idle seconds before re-ingesting after a change")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def watch_cmd(path: Path, ext: tuple[str, ...], idle: float, db: Path):
    """Watch a directory and re-ingest files on change (Ctrl+C to stop)."""
    from bunshin.file_watcher import WATCHDOG_AVAILABLE, start_watcher
    from bunshin.ingestion.files import DEFAULT_EXTENSIONS

    if not WATCHDOG_AVAILABLE:
        console.print("[red]watchdog not installed.[/red] Run: [cyan]pip install watchdog[/cyan]")
        return

    extensions = set(ext) if ext else DEFAULT_EXTENSIONS
    console.print(
        f"[green]Watching[/green] [cyan]{path}[/cyan] for {sorted(extensions)} "
        f"(idle={idle}s)\n[dim]Press Ctrl+C to stop.[/dim]\n"
    )

    def on_import(info):
        console.print(
            f"[dim]{info['path']}[/dim] → chunks={info.get('chunks_inserted', 0)}"
        )

    stop = start_watcher(
        db_path=db, root=path, extensions=extensions,
        idle_seconds=idle, on_import=on_import,
    )
    try:
        import signal
        signal.pause()
    except (KeyboardInterrupt, AttributeError):
        pass
    finally:
        console.print("\n[yellow]Stopping watcher...[/yellow]")
        stop()


@main.command("import-files")
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd,
)
@click.option(
    "--ext",
    multiple=True,
    help="File extensions to include (default: .md .markdown .txt)",
)
@click.option("--force", is_flag=True, help="Reimport even if file unchanged")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def import_files_cmd(path: Path, ext: tuple[str, ...], force: bool, db: Path):
    """Import local Markdown / text files."""
    conn = init_db(db)
    extensions = set(ext) if ext else DEFAULT_EXTENSIONS
    console.print(f"Scanning [cyan]{path}[/cyan] for {sorted(extensions)} files...")
    stats = import_files(conn, path, extensions=extensions, force=force)
    table = Table(title="File import results")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)
    conn.close()


@main.command("reindex")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
@click.option(
    "--claude-path",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.home() / ".claude" / "projects",
)
def reindex_cmd(db: Path, claude_path: Path):
    """Force re-chunk and re-embed all Claude history (~30s)."""
    from bunshin.embeddings import DIMENSIONS, embed_passages
    from bunshin.storage import (
        get_records_without_vectors,
        init_vector_db,
        insert_vector,
    )

    conn = init_db(db)

    console.print("[yellow]Force-reindexing all Claude sessions...[/yellow]")
    stats = import_claude_history(conn, claude_path, force=True)

    console.print(
        f"Sessions: scanned={stats['files_scanned']} "
        f"reimported={stats['files_reimported']} "
        f"records={stats['records_inserted']}"
    )

    # Re-embed
    init_vector_db(conn, dimensions=DIMENSIONS)
    pending = [
        (rid, text) for rid, text in get_records_without_vectors(conn)
        if len(text or "") >= 20
    ]
    if pending:
        console.print(f"Embedding {len(pending)} new chunks...")
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Embedding", total=len(pending))
            for i in range(0, len(pending), 32):
                batch = pending[i : i + 32]
                ids = [r[0] for r in batch]
                texts = [r[1] for r in batch]
                for rec_id, emb in zip(ids, embed_passages(texts)):
                    insert_vector(conn, rec_id, emb)
                conn.commit()
                progress.update(task, advance=len(batch))

    console.print(f"[green]Reindex complete.[/green]")
    conn.close()


@main.command("chat")
@click.argument("query", type=str)
@click.option("--model", default=None, help="Ollama model (auto-pick if not set)")
@click.option("--context-limit", default=5, help="Number of past memories to load")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def chat_cmd(query: str, model: Optional[str], context_limit: int, db: Path):
    """Chat with your memory via local LLM (Ollama)."""
    from bunshin.chat import build_context, chat_ollama, check_ollama, pick_model

    ok, available = check_ollama()
    if not ok:
        console.print("[red]Ollama not running.[/red]")
        console.print("Install: [cyan]https://ollama.com[/cyan]")
        console.print("Start:   [cyan]ollama serve[/cyan]")
        console.print("Pull a model: [cyan]ollama pull llama3.2:3b[/cyan]")
        return

    if not available:
        console.print("[red]No Ollama models installed.[/red]")
        console.print("Try: [cyan]ollama pull llama3.2:3b[/cyan]")
        return

    chosen = model or pick_model(available)
    if not chosen:
        console.print("[red]Could not pick a model.[/red]")
        return

    if not db.exists():
        console.print(f"[red]No database at {db}.[/red]")
        return

    conn = init_db(db)
    console.print(f"[dim]Model: {chosen} | Loading {context_limit} memories...[/dim]")
    context = build_context(conn, query, limit=context_limit)
    conn.close()

    if not context:
        console.print("[yellow](No relevant past memory found, answering without context)[/yellow]")

    console.print(f"\n[bold cyan]Q:[/bold cyan] {query}\n")
    console.print(f"[bold green]分身:[/bold green] ", end="")
    try:
        for chunk in chat_ollama(query, context, model=chosen, stream=True):
            console.print(chunk, end="")
        console.print()
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")


@main.command("import-browser")
@click.option(
    "--browser",
    "browsers",
    multiple=True,
    type=click.Choice(["safari", "chrome", "arc"]),
    help="Which browser to import (repeatable). Defaults to all available.",
)
@click.option("--initial-days", default=90, help="Days back to fetch on first run")
@click.option(
    "--full",
    is_flag=True,
    help="Ignore last-sync marker. Combine with --initial-days 36500 to backfill everything the browser still has on disk.",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_browser_cmd(browsers: tuple[str, ...], initial_days: int, full: bool, db: Path):
    """Import Safari / Chrome / Arc visit history."""
    from bunshin.ingestion.browser import import_browser_history
    conn = init_db(db)
    chosen = list(browsers) if browsers else None
    if full and initial_days == 90:
        initial_days = 36500
    if full:
        console.print("[yellow]Full re-sync: ignoring last-sync marker.[/yellow]")
    console.print(f"Importing browser history (browsers={chosen or 'all'})…")
    stats = import_browser_history(conn, browsers=chosen, initial_days=initial_days, full=full)
    table = Table(title="Browser import")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for k in ("safari", "chrome", "arc", "inserted", "skipped"):
        table.add_row(k, str(stats.get(k, 0)))
    console.print(table)
    conn.close()


@main.command("import-line")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--verbose", "-v", is_flag=True)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_line_cmd(path: Path, verbose: bool, db: Path):
    """Import LINE chat exports (single .txt or a directory of .txt files).

    LINE's Mac client (v15+) sandboxes its chat DB and encrypts the
    binary, so direct DB ingestion isn't possible. Workflow:

      1. In LINE app: open a talk → ⚙ → 'トーク履歴を送信' → mail it to
         yourself or save the .txt to a folder.
      2. Drop one or many .txt files into a folder (e.g. ~/Downloads/line-talks/).
      3. Run `bunshin import-line ~/Downloads/line-talks/` for the whole
         folder, or `bunshin import-line ~/Downloads/[LINE]talk.txt` for
         a single talk.
    """
    from bunshin.ingestion.line import import_line_file

    conn = init_db(db)

    if path.is_dir():
        # v0.10.13 (Honda TOP3): support a directory of LINE exports so
        # users with many talks don't have to invoke the CLI per file.
        files = sorted(path.glob("*.txt"))
        if not files:
            console.print(f"[yellow]No .txt files found in {path}[/yellow]")
            conn.close()
            return
        console.print(f"Importing [cyan]{len(files)}[/cyan] LINE talks from {path}...")
        total_msgs = 0
        total_chunks = 0
        ok = 0
        skipped = 0
        for f in files:
            stats = import_line_file(conn, f, verbose=verbose)
            if stats.get("error_msg"):
                console.print(f"  [yellow]⚠[/yellow] {f.name}: {stats['error_msg']}")
                skipped += 1
                continue
            ok += 1
            total_msgs += stats["messages_parsed"]
            total_chunks += stats["chunks_inserted"]
            if verbose:
                console.print(f"  [green]✓[/green] {f.name}: {stats['messages_parsed']} msgs → {stats['chunks_inserted']} chunks")
        table = Table(title=f"LINE bulk import — {ok}/{len(files)} talks")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("talks imported", str(ok))
        table.add_row("talks skipped", str(skipped))
        table.add_row("messages parsed", f"{total_msgs:,}")
        table.add_row("chunks inserted", f"{total_chunks:,}")
        console.print(table)
    else:
        console.print(f"Reading [cyan]{path.name}[/cyan]...")
        stats = import_line_file(conn, path, verbose=verbose)
        if stats.get("error_msg"):
            console.print(f"[red]Error:[/red] {stats['error_msg']}")
        else:
            table = Table(title=f"LINE import — {stats.get('title','')[:60]}")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", justify="right")
            table.add_row("messages_parsed", str(stats["messages_parsed"]))
            table.add_row("chunks_inserted", str(stats["chunks_inserted"]))
            console.print(table)
    conn.close()


@main.command("import-photos-app")
@click.option("--limit", default=0, type=int, help="Only the first N items (0 = all)")
@click.option("--days", default=0, type=int, help="Only items dated within last N days (0 = all)")
@click.option("--with-ocr", is_flag=True, help="Export each item and run Vision OCR (slow)")
@click.option("--verbose", "-v", is_flag=True)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_photos_app_cmd(
    limit: int, days: int, with_ocr: bool, verbose: bool, db: Path
):
    """Import the Photos.app library via AppleScript (no FDA needed)."""
    from bunshin.ingestion.photos_app import import_photos_app

    conn = init_db(db)
    console.print(
        f"Reading Photos.app library "
        f"({'all' if not days else f'last {days} days'}"
        f"{f', max {limit}' if limit else ''}, "
        f"{'with OCR' if with_ocr else 'metadata only'})…"
    )
    stats = import_photos_app(
        conn, limit=limit, days=days, with_ocr=with_ocr, verbose=verbose
    )
    if stats.get("applescript_failed"):
        console.print(
            "[red]Photos.app へのアクセス許可が必要です。[/red] "
            "システム設定 → プライバシーとセキュリティ → オートメーション → "
            "ターミナル → 写真 をオンにしてください。"
        )
        conn.close()
        return
    table = Table(title="Photos.app import")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for k in ("scanned", "imported", "unchanged", "with_gps", "with_ocr", "failed"):
        table.add_row(k, str(stats.get(k, 0)))
    console.print(table)
    conn.close()


@main.command("import-photos")
@click.argument(
    "root",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
    default=Path.home() / "Pictures",
)
@click.option("--skip-ocr", is_flag=True, help="Skip Vision OCR (EXIF only)")
@click.option("--verbose", "-v", is_flag=True)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_photos_cmd(root: Path, skip_ocr: bool, verbose: bool, db: Path):
    """Import photos: EXIF + macOS Vision OCR (Japanese + English)."""
    from bunshin.ingestion.photos import ensure_ocr_binary, import_photos

    conn = init_db(db)
    if not skip_ocr:
        console.print("[dim]Vision OCR バイナリを準備中…[/dim]")
        binary = ensure_ocr_binary()
        if not binary:
            console.print(
                "[yellow]Swift がない or コンパイル失敗。EXIF のみで取り込みます。[/yellow]"
            )
            skip_ocr = True
        else:
            console.print(f"[dim]OCR バイナリ: {binary}[/dim]")
    console.print(f"Scanning [cyan]{root}[/cyan] for images…")
    stats = import_photos(conn, root, skip_ocr=skip_ocr, verbose=verbose)

    table = Table(title="Photo import")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for k in ("scanned", "imported", "unchanged", "with_gps", "with_ocr", "failed"):
        table.add_row(k, str(stats.get(k, 0)))
    console.print(table)
    conn.close()


@main.command("import-imessage")
@click.option("--initial-days", default=365, help="Days back to fetch on first run")
@click.option("--verbose", "-v", is_flag=True)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_imessage_cmd(initial_days: int, verbose: bool, db: Path):
    """Import iMessage / SMS history (requires Full Disk Access)."""
    from bunshin.ingestion.imessage import import_imessage

    conn = init_db(db)
    console.print("iMessage を取り込み中…")
    stats = import_imessage(conn, initial_days=initial_days, verbose=verbose)

    if stats.get("error"):
        console.print(f"[red]{stats['error']}[/red]")
        console.print(
            "[dim]設定後、ターミナルを開き直してから再実行してください。[/dim]"
        )
        conn.close()
        return

    table = Table(title="iMessage import")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for k in ("scanned", "inserted", "recovered_from_blob", "skipped_no_text"):
        table.add_row(k, str(stats.get(k, 0)))
    console.print(table)
    conn.close()


@main.command("import-notes")
@click.option(
    "--force",
    is_flag=True,
    help="Re-import all notes, ignoring per-note modification timestamps",
)
@click.option("--verbose", "-v", is_flag=True, help="Print each note as it is imported")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_notes_cmd(force: bool, verbose: bool, db: Path):
    """Import Apple Notes (macOS only — runs Notes.app via AppleScript)."""
    from bunshin.ingestion.notes import import_apple_notes

    conn = init_db(db)
    console.print("Asking Notes.app for your notes via AppleScript…")
    console.print(
        "[dim]初回は Notes.app へのアクセス許可を求められます — 「OK」を選んでください。[/dim]"
    )
    stats = import_apple_notes(conn, force=force, verbose=verbose)

    if stats.get("applescript_failed"):
        console.print(
            "[red]AppleScript の実行に失敗しました。[/red] "
            "Notes.app の自動化を許可する設定が必要です：\n"
            "  システム設定 → プライバシーとセキュリティ → オートメーション → ターミナル → メモ をオン"
        )
        conn.close()
        return

    table = Table(title="Apple Notes import")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for k in ("scanned", "unchanged", "imported", "failed", "chunks"):
        table.add_row(k, str(stats.get(k, 0)))
    console.print(table)
    conn.close()


@main.command("migrate-embeddings")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
@click.option(
    "--force",
    is_flag=True,
    help="Force re-embed all records even if dimensions match",
)
def migrate_embeddings_cmd(db: Path, force: bool):
    """Migrate to the currently configured embedding model.

    Compares the on-disk vector dimensions with the configured model.
    If they differ, drops the vector table and re-embeds all records.
    """
    from bunshin.embeddings import DIMENSIONS, MODEL_NAME, embed_passages
    from bunshin.storage import (
        detect_vec_dimensions,
        drop_vector_db,
        get_records_without_vectors,
        init_vector_db,
        insert_vector,
    )

    conn = init_db(db)
    existing_dim = detect_vec_dimensions(conn)
    target_dim = DIMENSIONS

    console.print(f"Configured model:  [cyan]{MODEL_NAME}[/cyan] ({target_dim}d)")
    console.print(f"Existing vec dim:  [cyan]{existing_dim}[/cyan]")

    if existing_dim == target_dim and not force:
        console.print("[green]✓[/green] Dimensions match, no migration needed.")
        console.print("[dim]Use --force to re-embed anyway.[/dim]")
        return

    if existing_dim is not None:
        console.print(f"[yellow]Dropping old vector table ({existing_dim}d)...[/yellow]")
        drop_vector_db(conn)

    console.print(f"[yellow]Creating new vector table ({target_dim}d)...[/yellow]")
    init_vector_db(conn, dimensions=target_dim)

    # Re-embed everything (model will be downloaded on first call if new)
    pending = [
        (rid, text) for rid, text in get_records_without_vectors(conn)
        if len(text or "") >= 20
    ]
    console.print(f"Re-embedding [bold]{len(pending)}[/bold] records (first run downloads the model)...")

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding", total=len(pending))
        batch_size = 16  # smaller batch for the larger model
        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            ids = [r[0] for r in batch]
            texts = [r[1] for r in batch]
            for rec_id, emb in zip(ids, embed_passages(texts)):
                insert_vector(conn, rec_id, emb)
            conn.commit()
            progress.update(task, advance=len(batch))

    console.print(f"[green]✓[/green] Migrated to {MODEL_NAME} ({target_dim}d)")
    conn.close()


@main.command("backup")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
@click.option("--keep", default=7, help="Number of daily snapshots to retain")
def backup_cmd(db: Path, keep: int):
    """Take a consistent snapshot of the DB into ~/.bunshin/backups/."""
    from bunshin.backup import backup_db
    stats = backup_db(db, keep=keep)
    if stats.get("error"):
        console.print(f"[red]✗[/red] {stats['error']}")
        return
    mb = stats["bytes"] / 1024 / 1024
    console.print(
        f"[green]✓[/green] Backup: {stats['backup_path']} ({mb:.1f} MB)\n"
        f"  retained={stats['retained']} removed={stats['removed']}"
    )


@main.command("backups")
def backups_cmd():
    """List existing backups."""
    from bunshin.backup import list_backups
    items = list_backups()
    if not items:
        console.print("[yellow]No backups yet.[/yellow] Run `bunshin backup` first.")
        return
    table = Table(title="Backups")
    table.add_column("Date", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Path", style="dim")
    for it in items:
        mb = it["bytes"] / 1024 / 1024
        table.add_row(it["mtime_str"], f"{mb:.1f} MB", it["path"])
    console.print(table)


@main.command("install-scheduler")
def install_scheduler_cmd():
    """Install hourly auto-update via OS-appropriate scheduler.

    Auto-detects:
      - macOS → launchd user agent
      - Linux + systemd → systemd --user timer
      - Linux + cron → crontab entry
    """
    from bunshin.scheduler import detect_platform, install_scheduler

    plat = detect_platform()
    console.print(f"Detected platform: [cyan]{plat}[/cyan]")
    ok, msg = install_scheduler()
    if ok:
        console.print(f"[green]✓[/green] {msg}")
        console.print(
            "[dim]Logs: ~/.bunshin/logs/update.{out,err}.log[/dim]"
        )
    else:
        console.print(f"[red]✗[/red] {msg}")


@main.command("uninstall-scheduler")
def uninstall_scheduler_cmd():
    """Remove the auto-update scheduler installed via `install-scheduler`."""
    from bunshin.scheduler import uninstall_scheduler

    ok, msg = uninstall_scheduler()
    if ok:
        console.print(f"[green]✓[/green] {msg}")
    else:
        console.print(f"[red]✗[/red] {msg}")


@main.command("doctor")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def doctor_cmd(db: Path):
    """Diagnose setup, show what's working and what's missing."""
    import subprocess

    console.print("\n[bold]🩺 分身 セットアップ診断[/bold]\n")

    issues = []  # (level, label, detail, fix)

    # ── 1. Database
    if not db.exists():
        issues.append(("❌", "データベース", "未初期化", "bunshin init"))
    else:
        conn = init_db(db)
        total = count_records(conn)
        if total == 0:
            issues.append(
                ("⚠", "データベース",
                 f"DB は存在するが空 ({db})",
                 "bunshin import-claude && bunshin embed")
            )
        else:
            sources = dict(list_sources_with_counts(conn))
            console.print(f"[green]✓[/green] データベース: {total} 件 ({db})")
            for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
                console.print(f"   [dim]├ {src}: {cnt}[/dim]")

        try:
            init_vector_db(conn)
        except Exception:
            pass
        vec_count = count_vectors(conn)
        if vec_count < total * 0.8:
            issues.append(
                ("⚠", "ベクトル化",
                 f"{vec_count}/{total} のみ (検索品質が下がる)",
                 "bunshin embed")
            )
        else:
            console.print(f"[green]✓[/green] ベクトル化: {vec_count}/{total}")
        conn.close()

    # ── 2. Ollama
    try:
        from bunshin.chat import check_ollama
        ok, models = check_ollama()
        if not ok:
            issues.append(
                ("⚠", "Ollama (オフラインチャット)",
                 "未起動 — オンラインAIのみ使用可",
                 "open /Applications/Ollama.app   # または ollama serve")
            )
        elif not models:
            issues.append(
                ("⚠", "Ollama モデル",
                 "Ollama 稼働中だがモデル未インストール",
                 "ollama pull qwen2.5:14b   # 推奨")
            )
        else:
            console.print(f"[green]✓[/green] Ollama: {len(models)} モデル ({', '.join(models[:3])})")
    except Exception as e:
        issues.append(("⚠", "Ollama", f"確認失敗: {e}", "ollama 確認"))

    # ── 3. Gmail
    try:
        from bunshin.ingestion.gmail import load_credentials as gmail_creds
        creds = gmail_creds()
        if not creds:
            issues.append(
                ("ℹ", "Gmail取り込み",
                 "未設定 (オプション)",
                 "bunshin setup-gmail --email YOU@gmail.com")
            )
        else:
            console.print(f"[green]✓[/green] Gmail: {creds['email']}")
    except Exception:
        pass

    # ── 4. Calendar
    try:
        from bunshin.ingestion.calendar import load_url as cal_url
        if not cal_url():
            issues.append(
                ("ℹ", "カレンダー取り込み",
                 "未設定 (オプション)",
                 "bunshin setup-calendar 'iCal URL'   # Google Calendar 設定 → 統合 から取得")
            )
        else:
            console.print(f"[green]✓[/green] カレンダー: URL 設定済")
    except Exception:
        pass

    # ── 5. auto-update (cross-platform scheduler)
    try:
        from bunshin.scheduler import scheduler_status
        st = scheduler_status()
        plat = st.get("platform", "unknown")
        if not st.get("installed"):
            issues.append(
                ("ℹ", "自動更新",
                 f"未設定 ({plat}) — 手動で update が必要",
                 "bunshin install-scheduler")
            )
        elif not st.get("active"):
            issues.append(
                ("⚠", "自動更新",
                 f"設定済 ({plat}) だが稼働してない",
                 "bunshin install-scheduler  # 再インストール")
            )
        else:
            console.print(f"[green]✓[/green] 自動更新: {plat} で毎時実行中")
    except Exception as e:
        issues.append(("⚠", "自動更新", f"確認失敗: {e}", "—"))

    # ── 6. MCP integration
    project_mcp = Path.cwd() / ".mcp.json"
    desktop_mcp = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"

    if project_mcp.exists():
        console.print(f"[green]✓[/green] Claude Code MCP: {project_mcp}")
    else:
        issues.append(
            ("ℹ", "Claude Code MCP",
             "プロジェクトディレクトリに .mcp.json なし",
             "docs/SETUP.md → 「オプション：MCP連携」参照")
        )

    if desktop_mcp.exists():
        try:
            import json as _json
            config = _json.loads(desktop_mcp.read_text())
            if "bunshin" in config.get("mcpServers", {}):
                console.print("[green]✓[/green] Claude Desktop MCP: 設定済")
            else:
                issues.append(
                    ("ℹ", "Claude Desktop MCP", "設定ファイルあるが bunshin 未登録",
                     "docs/SETUP.md 参照")
                )
        except Exception:
            pass

    # ── 6.5. Anthropic API key (optional but lifts describe quality)
    try:
        if db.exists():
            import sqlite3 as _sqlite3
            _c = _sqlite3.connect(str(db))
            _row = _c.execute(
                "SELECT value FROM settings WHERE key = ?", ("anthropic_api_key",)
            ).fetchone()
            _c.close()
            v = (_row[0] if _row else "") or ""
            if v.strip():
                masked = v[:7] + "…" + v[-4:] if len(v) > 12 else "(short)"
                console.print(f"[green]✓[/green] Anthropic API キー: 設定済 ({masked}) — Claude describe 有効")
            else:
                issues.append(
                    ("ℹ", "Anthropic API キー",
                     "未設定 — describe はローカル LLM のみ (品質低下)",
                     "設定タブ → Anthropic API キー (任意) → console.anthropic.com")
                )
    except Exception:
        pass

    # ── 6.6. bunshin web reachability
    try:
        import urllib.request as _ur
        with _ur.urlopen("http://127.0.0.1:8000/api/health", timeout=2) as _r:
            import json as _json
            _body = _json.loads(_r.read())
        console.print(
            f"[green]✓[/green] bunshin web v{_body.get('version','?')} 起動中 "
            f"(rss {_body.get('rss_mb','?')} MB)"
        )
    except Exception:
        issues.append(
            ("ℹ", "bunshin web",
             "127.0.0.1:8000 で起動してない",
             "Bunshin.app を開く  または  bunshin web")
        )

    # ── 7. Knowledge Graph
    try:
        from bunshin.knowledge_graph import init_kg_schema
        conn = init_db(db)
        init_kg_schema(conn)
        e_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        link_count = conn.execute("SELECT COUNT(*) FROM record_entities").fetchone()[0]
        if e_count == 0:
            issues.append(
                ("ℹ", "Knowledge Graph",
                 "エンティティ未抽出",
                 "bunshin graph build")
            )
        else:
            console.print(f"[green]✓[/green] Knowledge Graph: {e_count} エンティティ, {link_count} リンク")

            # v0.10.21: duplicate-candidate summary — same normalize logic as
            # find-duplicates. Just count groups, don't print details (that's
            # what `bunshin find-duplicates` is for).
            try:
                import re as _re
                def _normalize(name):
                    if not name: return ""
                    s = _re.sub(r"\s*[（(].*?[)）]\s*", "", name)
                    s = s.strip().lower()
                    return _re.sub(r"[ \t/・,，、:：·]", "", s)
                rows = conn.execute(
                    "SELECT e.name, (SELECT COUNT(*) FROM record_entities re WHERE re.entity_id = e.id) AS m "
                    "FROM entities e"
                ).fetchall()
                groups: dict = {}
                for name, m in rows:
                    if (m or 0) < 1:
                        continue
                    k = _normalize(name)
                    if not k or len(k) < 2:
                        continue
                    groups.setdefault(k, 0)
                    groups[k] += 1
                dup_count = sum(1 for v in groups.values() if v >= 2)
                if dup_count > 0:
                    issues.append(
                        ("ℹ", "重複候補エンティティ",
                         f"{dup_count} 件の merge 候補グループあり",
                         "bunshin find-duplicates  →  bunshin merge-entities …")
                    )
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    # ── Summary
    console.print()
    if not issues:
        console.print("[bold green]🎉 すべて整っています！[/bold green]")
        console.print("[dim]ブラウザで http://127.0.0.1:8000 を開いて使ってください。[/dim]")
        return

    console.print("[bold]── 改善できる項目 ──[/bold]\n")
    for level, label, detail, fix in issues:
        color = "red" if level == "❌" else "yellow" if level == "⚠" else "cyan"
        console.print(f"[{color}]{level}[/{color}] [bold]{label}[/bold]: {detail}")
        console.print(f"   [dim]→[/dim] [cyan]{fix}[/cyan]\n")


@main.command("graph")
@click.argument("action", type=click.Choice(["build", "rebuild", "list", "add", "discover", "cleanup"]))
@click.option("--name", default=None, help="Entity name (for `add`)")
@click.option("--type", "type_", default="topic", help="Entity type (for `add`)")
@click.option("--alias", multiple=True, help="Entity alias (repeatable, for `add`)")
@click.option("--description", default=None, help="Entity description (for `add`)")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def graph_cmd(
    action: str,
    name: Optional[str],
    type_: str,
    alias: tuple[str, ...],
    description: Optional[str],
    db: Path,
):
    """Knowledge graph commands.

    Actions:
      build    Seed entities + link records (incremental)
      rebuild  Same as build (currently identical, idempotent)
      list     Show all entities with mention counts
      add      Add a custom entity (--name required)
    """
    from bunshin.knowledge_graph import (
        add_custom_entity,
        entity_with_counts,
        init_kg_schema,
        link_records_to_entities,
        seed_entities,
    )

    conn = init_db(db)
    init_kg_schema(conn)

    if action in ("build", "rebuild"):
        console.print("Seeding entities...")
        seed_stats = seed_entities(conn)
        console.print(
            f"  ✓ from memory: {seed_stats['from_memory']} | "
            f"user config: {seed_stats.get('from_user_config', 0)} | "
            f"generic: {seed_stats.get('from_generic', 0)}"
        )
        console.print("Linking records to entities...")
        link_stats = link_records_to_entities(conn, verbose=False)
        console.print(
            f"  ✓ scanned {link_stats['records_scanned']} records | "
            f"{link_stats['links_inserted']} links | "
            f"{link_stats['entities_used']} entities used"
        )

    elif action == "list":
        entities = entity_with_counts(conn)
        table = Table(title=f"Entities ({len(entities)})")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Mentions", justify="right")
        table.add_column("Description", style="dim")
        for e in entities[:50]:
            table.add_row(
                e["name"],
                e["type"],
                str(e["mentions"]),
                (e["description"] or "")[:60],
            )
        console.print(table)
        if len(entities) > 50:
            console.print(f"[dim](showing 50 of {len(entities)})[/dim]")

    elif action == "cleanup":
        from bunshin.knowledge_graph import cleanup_noise_entities
        n = cleanup_noise_entities(conn)
        console.print(f"[green]✓[/green] Removed {n} noise entities")

    elif action == "discover":
        from bunshin.knowledge_graph import discover_entities_via_llm, link_records_to_entities
        sample = 100  # could be parametrized
        console.print(f"[yellow]Discovering entities via LLM (sample={sample})...[/yellow]")
        console.print("[dim]This calls Ollama for each sampled record (~1-3min total).[/dim]")
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("LLM discovery", total=sample)
            def cb(i, total, found):
                progress.update(task, completed=i, description=f"LLM discovery (found: {found})")
            stats = discover_entities_via_llm(conn, sample_size=sample, progress_callback=cb)
        if "error" in stats:
            console.print(f"[red]Error:[/red] {stats['error']}")
        else:
            console.print(
                f"[green]✓[/green] processed={stats['records_processed']} "
                f"found={stats['entities_found']} new={stats['entities_new']} "
                f"errors={stats.get('errors',0)} (model={stats.get('model','?')})"
            )
            console.print("[dim]Now run `bun graph rebuild` to link them to records.[/dim]")

    elif action == "add":
        if not name:
            console.print("[red]--name is required for `add`[/red]")
            return
        eid = add_custom_entity(
            conn, name, type_,
            aliases=list(alias) or None,
            description=description,
        )
        console.print(f"[green]OK[/green] Added entity #{eid}: {name} ({type_})")
        console.print("[dim]Run `bun graph rebuild` to link existing records.[/dim]")

    conn.close()


@main.command("insights")
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB_PATH)
def insights_cmd(db: Path):
    """Show today's auto-generated insights."""
    from bunshin.insights import generate_insights

    conn = init_db(db)
    data = generate_insights(conn)
    conn.close()

    console.print(f"\n[bold]💡 分身からのお知らせ — {data['generated_at']}[/bold]\n")

    if data["inactive_projects"]:
        console.print("[bold yellow]🔥 長期未活動プロジェクト[/bold yellow]")
        for p in data["inactive_projects"]:
            console.print(
                f"  [bold]{p['name']}[/bold] — "
                f"[red]{p['days_ago']}日未活動[/red] (最終 {p['last_seen']})"
            )
            console.print(f"    {p['description'][:120]}")
        console.print()

    if data["upcoming_events"]:
        console.print("[bold cyan]📅 直近の予定（14日以内）[/bold cyan]")
        for e in data["upcoming_events"]:
            loc = f" @ {e['location']}" if e["location"] else ""
            console.print(f"  {e['start']} — [bold]{e['summary']}[/bold]{loc}")
        console.print()

    if data["recent_notes"]:
        console.print("[bold green]📝 直近の手動メモ[/bold green]")
        for n in data["recent_notes"]:
            console.print(f"  {n['date']} {n['content'][:120]}")
        console.print()

    if data["pending_questions"]:
        console.print("[bold magenta]❓ 直近1週間で未回答の質問[/bold magenta]")
        for q in data["pending_questions"]:
            console.print(f"  {q['date']}")
            console.print(f"    {q['content'][:200]}")
            console.print()


@main.command("transcribe")
@click.argument(
    "path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--model", default="small", help="Whisper model size (tiny, base, small, medium, large)")
@click.option("--language", default="ja", help="Language hint (ja, en, auto, ...)")
@click.option("--save/--no-save", default=True, help="Save the transcript as a manual memo")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def transcribe_cmd(path: Path, model: str, language: str, save: bool, db: Path):
    """Transcribe an audio file and (by default) save it as a memo.

    Requires one of: faster-whisper, openai-whisper, or whisper-cpp.
    """
    from bunshin.ingestion.audio import detect_backend, transcribe

    backend = detect_backend()
    console.print(f"Backend: [cyan]{backend or 'none'}[/cyan]")
    if not backend:
        console.print(
            "[red]No transcription backend installed.[/red]\n"
            "Run one of:\n"
            "  [cyan]pip install faster-whisper[/cyan]   # recommended\n"
            "  [cyan]pip install openai-whisper[/cyan]   # reference (needs torch)\n"
            "  [cyan]brew install whisper-cpp[/cyan]     # Apple-Silicon native"
        )
        return

    console.print(f"Transcribing [cyan]{path.name}[/cyan] with model={model} lang={language}…")
    console.print("[dim]First run downloads the model (~80MB-1GB depending on size).[/dim]")
    result = transcribe(path, model_name=model, language=language)
    if result.get("error"):
        console.print(f"[red]Error:[/red] {result['error']}")
        return

    text = result["text"]
    console.print(f"\n[green]✓[/green] Transcribed {len(text)} chars\n")
    console.print(text[:500] + ("..." if len(text) > 500 else ""))

    if save:
        from bunshin.embeddings import DIMENSIONS, embed_passages
        from bunshin.ingestion.manual import add_note
        from bunshin.storage import init_vector_db, insert_vector

        conn = init_db(db)
        rid = add_note(conn, content=f"[音声: {path.name}]\n\n{text}", tags=["audio", "transcript"])
        if rid and len(text) >= 20:
            init_vector_db(conn, dimensions=DIMENSIONS)
            for emb in embed_passages([text]):
                insert_vector(conn, rid, emb)
            conn.commit()
        conn.close()
        console.print(f"\n[green]✓[/green] Saved as memo (record_id={rid})")


@main.command("note")
@click.argument("content", type=str)
@click.option("--tag", multiple=True, help="Tag (repeatable)")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def note_cmd(content: str, tag: tuple[str, ...], db: Path):
    """Add a manual memo. Embeds it immediately for instant search."""
    from bunshin.embeddings import DIMENSIONS, embed_passages
    from bunshin.ingestion.manual import add_note
    from bunshin.storage import init_vector_db, insert_vector

    conn = init_db(db)
    record_id = add_note(conn, content, tags=list(tag))
    if not record_id:
        console.print("[yellow]Empty memo, nothing saved.[/yellow]")
        conn.close()
        return

    # Immediate embedding so it's searchable right away
    if len(content) >= 20:
        init_vector_db(conn, dimensions=DIMENSIONS)
        for emb in embed_passages([content]):
            insert_vector(conn, record_id, emb)
        conn.commit()

    console.print(f"[green]OK[/green] Saved memo: {content[:80]}")
    conn.close()


@main.command("setup-calendar")
@click.argument("ical_url", type=str)
def setup_calendar_cmd(ical_url: str):
    """Save iCal feed URL for calendar import (Google Calendar private URL)."""
    from bunshin.ingestion.calendar import save_url
    save_url(ical_url)
    console.print("[green]OK[/green] Saved calendar URL.")
    console.print("Next: [bold]bunshin import-calendar[/bold]")


@main.command("import-calendar")
@click.option("--url", default=None, help="iCal URL (uses saved URL if not given)")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_calendar_cmd(url: Optional[str], db: Path):
    """Import calendar events from iCal feed."""
    from bunshin.ingestion.calendar import import_calendar

    conn = init_db(db)
    console.print("Fetching calendar...")
    stats = import_calendar(conn, url=url)
    if stats.get("error_msg"):
        console.print(f"[red]Error:[/red] {stats['error_msg']}")
    else:
        table = Table(title="Calendar import")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        for k in ("fetched", "imported", "errors"):
            table.add_row(k, str(stats.get(k, 0)))
        console.print(table)
    conn.close()


@main.command("setup-gmail")
@click.option("--email", required=True, help="Your Gmail address")
@click.option(
    "--app-password",
    required=True,
    prompt=True,
    hide_input=True,
    help="App password (https://myaccount.google.com/apppasswords)",
)
def setup_gmail_cmd(email: str, app_password: str):
    """Save Gmail credentials. Needs an App Password (not your regular password)."""
    from bunshin.ingestion.gmail import save_credentials
    save_credentials(email, app_password.strip())
    console.print(f"[green]OK[/green] Saved credentials for [cyan]{email}[/cyan]")
    console.print("Next: [bold]bunshin import-gmail[/bold]")


@main.command("import-gmail")
@click.option("--limit", type=int, default=None, help="Max emails to fetch")
@click.option("--initial-days", default=90, help="Days back to fetch on first run")
@click.option(
    "--full",
    is_flag=True,
    help="Ignore last-sync marker and refetch the full initial-days range (use with --initial-days 36500 for everything)",
)
@click.option(
    "--folder",
    default='"[Gmail]/All Mail"',
    help='IMAP folder (default: all mail)',
)
@click.option("--verbose", "-v", is_flag=True)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def import_gmail_cmd(
    limit: Optional[int],
    initial_days: int,
    full: bool,
    folder: str,
    verbose: bool,
    db: Path,
):
    """Import emails via Gmail IMAP (run setup-gmail first)."""
    from bunshin.ingestion.gmail import import_gmail, load_credentials

    creds = load_credentials()
    if not creds:
        console.print("[red]No Gmail credentials.[/red]")
        console.print("Run: [bold]bunshin setup-gmail --email you@gmail.com[/bold]")
        return

    # `--full` without an explicit --initial-days means "everything" —
    # IMAP SINCE doesn't need an exact date, ~100 years is plenty.
    if full and initial_days == 90:
        initial_days = 36500

    conn = init_db(db)
    console.print(f"Connecting to Gmail as [cyan]{creds['email']}[/cyan]...")
    if full:
        console.print("[yellow]Full re-sync: ignoring last-sync marker.[/yellow]")
    stats = import_gmail(
        conn,
        creds["email"],
        creds["app_password"],
        folder=folder,
        limit=limit,
        initial_days=initial_days,
        verbose=verbose,
        full=full,
    )

    if stats.get("error_msg"):
        console.print(f"[red]Error:[/red] {stats['error_msg']}")
    else:
        table = Table(title="Gmail import results")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        for k in ("fetched", "imported", "chunks_inserted", "errors"):
            table.add_row(k, str(stats.get(k, 0)))
        console.print(table)
    conn.close()


@main.command("clean")
@click.option("--min-length", default=20, help="Minimum content length to keep")
@click.option("--dry-run", is_flag=True, help="Count only, don't delete")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def clean_cmd(min_length: int, dry_run: bool, db: Path):
    """Delete records shorter than min-length characters (semantic noise)."""
    if not db.exists():
        console.print(f"[red]No database at {db}.[/red]")
        return

    conn = init_db(db)
    short = count_short_records(conn, min_length=min_length)
    total = count_records(conn)

    if short == 0:
        console.print(
            f"[green]Nothing to clean.[/green] All {total} records are {min_length}+ chars."
        )
        conn.close()
        return

    console.print(
        f"Found [bold]{short}[/bold] short records (< {min_length} chars) "
        f"out of [bold]{total}[/bold] total."
    )

    if dry_run:
        console.print("[yellow]Dry run, not deleting.[/yellow]")
        conn.close()
        return

    deleted = delete_short_records(conn, min_length=min_length)
    remaining = count_records(conn)
    remaining_vec = count_vectors(conn)
    console.print(f"[green]OK[/green] Deleted {deleted} records.")
    console.print(f"Remaining: [bold]{remaining}[/bold] records, [bold]{remaining_vec}[/bold] embeddings.")
    conn.close()


@main.command("export")
@click.option(
    "--out", type=click.Path(path_type=Path),
    default=Path("bunshin-export.jsonl"),
    help="Output JSONL path",
)
@click.option("--since", type=str, default=None,
              help="Only export records timestamped >= this ISO date (YYYY-MM-DD)")
@click.option("--source", type=str, default=None,
              help="Limit to a single source (gmail / claude / file / ...)")
@click.option("--include-browser", is_flag=True, default=False,
              help="Include browser history (excluded by default for privacy)")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
def export_cmd(out: Path, since: Optional[str], source: Optional[str],
               include_browser: bool, db: Path):
    """Export records as newline-delimited JSON, ready for `bunshin import`
    on another machine."""
    from datetime import datetime as _dt
    conn = init_db(db)
    where = []
    params: list = []
    if since:
        try:
            ts = int(_dt.fromisoformat(since).timestamp())
            where.append("timestamp >= ?")
            params.append(ts)
        except ValueError:
            console.print(f"[red]invalid date: {since}[/red]")
            return
    if source:
        where.append("source = ?")
        params.append(source)
    elif not include_browser:
        where.append("source != 'browser'")
    sql = "SELECT id, source, source_id, timestamp, content, metadata FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp ASC"

    n = 0
    with out.open("w", encoding="utf-8") as f:
        for row in conn.execute(sql, params):
            rec = {
                "id": row[0],
                "source": row[1],
                "source_id": row[2],
                "timestamp": row[3],
                "content": row[4],
                "metadata": json.loads(row[5]) if row[5] else None,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    conn.close()
    console.print(f"[green]✓[/green] Exported [bold]{n}[/bold] records → {out}")


@main.command("import")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
)
@click.option("--skip-existing", is_flag=True, default=True,
              help="Skip records whose id is already in the DB (default)")
@click.option("--embed/--no-embed", default=True,
              help="Re-embed imported records after insert (default: yes)")
def import_cmd(path: Path, db: Path, skip_existing: bool, embed: bool):
    """Import records from a JSONL file produced by `bunshin export`.

    Designed for moving a memory between Macs, or restoring after a wipe.
    """
    from bunshin.storage import insert_record_raw
    conn = init_db(db)
    inserted = 0
    skipped = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skip_existing:
                row = conn.execute(
                    "SELECT 1 FROM records WHERE id = ?", (rec["id"],)
                ).fetchone()
                if row:
                    skipped += 1
                    continue
            try:
                conn.execute(
                    "INSERT INTO records(id, source, source_id, timestamp, content, metadata) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        rec["id"],
                        rec.get("source", "manual"),
                        rec.get("source_id"),
                        rec.get("timestamp"),
                        rec.get("content", ""),
                        json.dumps(rec["metadata"], ensure_ascii=False)
                        if rec.get("metadata") else None,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    conn.commit()
    conn.close()
    console.print(
        f"[green]✓[/green] Imported [bold]{inserted}[/bold] records, "
        f"skipped {skipped} existing."
    )
    if embed and inserted:
        console.print("Tip: run [cyan]bunshin migrate-embeddings[/cyan] "
                      "(or restart Bunshin) to backfill embeddings for "
                      "the new records.")


@main.command("web")
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def web_cmd(host: str, port: int, db: Path):
    """Start the Bunshin web UI."""
    import uvicorn

    from bunshin.web.server import create_app

    if not db.exists():
        console.print(
            f"[red]No database at {db}. Run [bold]bunshin init[/bold] first.[/red]"
        )
        return

    url = f"http://{host}:{port}"
    console.print(f"[green]分身 Web UI[/green] starting on [cyan]{url}[/cyan]")
    console.print("[dim]Open the URL in your browser. Press Ctrl+C to stop.[/dim]\n")

    app = create_app(db)
    uvicorn.run(app, host=host, port=port, log_level="warning")


@main.command("photos-time-stories")
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB_PATH,
              help="Bunshin DB path.")
@click.option("--min-photos", type=int, default=4,
              help="Min photos per story (default 4).")
@click.option("--gap-hours", type=int, default=48,
              help="Max gap between consecutive photos in same story.")
@click.option("--verbose", is_flag=True)
def photos_time_stories_cmd(db: Path, min_photos: int, gap_hours: int,
                             verbose: bool):
    """Group photos by place × contiguous date span → `event` entities.

    Run after `photos-place-clusters`. Photos sharing a place_entity
    and falling within `gap_hours` of one another become a single
    "story" — usually a trip, a day out, or a multi-day project. The
    story is registered as an `event` entity ("壱岐市 2026-04-15〜
    2026-04-18 (37 枚)") and linked to every photo in the span.
    """
    from bunshin.photos_clusters import compute_time_stories
    conn = init_db(db)
    try:
        stats = compute_time_stories(
            conn,
            min_photos=min_photos,
            gap_sec=gap_hours * 3600,
            verbose=verbose,
        )
    finally:
        conn.close()
    table = Table(title="Time-series stories")
    table.add_column("Metric"); table.add_column("Count", justify="right")
    for k, v in stats.items():
        table.add_row(k.replace("_", " "), str(v))
    console.print(table)


@main.command("photos-place-clusters")
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB_PATH,
              help="Bunshin DB path.")
@click.option("--min-photos", type=int, default=5,
              help="Min photos per bucket (default 5).")
@click.option("--max-clusters", type=int, default=50,
              help="Cap on entities created (default 50).")
@click.option("--verbose", is_flag=True)
def photos_place_clusters_cmd(db: Path, min_photos: int, max_clusters: int,
                               verbose: bool):
    """Group GPS-tagged photos by proximity → create place entities.

    Bunshin already imports photo timestamps + GPS, but the raw
    coordinates don't surface in search. This pass buckets photos at
    ~1.1km resolution, reverse-geocodes each bucket via Wikipedia
    geosearch, and registers the result as a `place` entity linked to
    every photo in the cluster. After running, queries like "壱岐島
    の写真" / "ハワイの写真" surface the right images, and the
    relationships graph gets concrete geographic nodes.
    """
    from bunshin.photos_clusters import compute_place_clusters
    conn = init_db(db)
    try:
        stats = compute_place_clusters(
            conn,
            min_photos=min_photos,
            max_clusters=max_clusters,
            verbose=verbose,
        )
    finally:
        conn.close()
    table = Table(title="Place clusters")
    table.add_column("Metric"); table.add_column("Count", justify="right")
    for k, v in stats.items():
        table.add_row(k.replace("_", " "), str(v))
    console.print(table)


@main.command("photos-relabel-places")
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB_PATH,
              help="Bunshin DB path.")
@click.option("--dry-run", is_flag=True,
              help="Show what would change without touching the DB.")
def photos_relabel_places_cmd(db: Path, dry_run: bool):
    """Re-name existing place entities created by photos-place-clusters.

    Older runs of photos-place-clusters used Wikipedia geosearch, which
    sometimes picked historical 旧地名 ("小栗村 (長崎県)" for what is
    now 諫早市) or facility names ("Barcelona City Hall" instead of
    "Barcelona"). v0.10.23 added Nominatim as the primary geocoder —
    this command applies that to every existing place entity whose
    description still encodes the original GPS coordinates.

    Safe to re-run. Only renames; never merges or deletes. Use
    `bunshin merge-entities` afterwards if old and new names should
    collapse into one entity.
    """
    import re as _re
    import sqlite3 as _sql
    import time as _time
    from bunshin.photos_clusters import _nominatim_place
    conn = init_db(db)
    conn.row_factory = _sql.Row
    try:
        coord_re = _re.compile(r"GPS座標\s*([\-\d.]+)\s*,\s*([\-\d.]+)")
        rows = conn.execute(
            "SELECT id, name, description FROM entities "
            "WHERE type = 'place' AND description LIKE 'GPS座標%'"
        ).fetchall()
        if not rows:
            console.print("[yellow]No photo place entities found.[/yellow]")
            return
        console.print(f"[cyan]Found {len(rows)} photo place entities.[/cyan]\n")
        renames: list[tuple[int, str, str, str]] = []
        for r in rows:
            m = coord_re.search(r["description"] or "")
            if not m:
                continue
            lat, lon = float(m.group(1)), float(m.group(2))
            new_name = _nominatim_place(lat, lon)
            if not new_name:
                console.print(
                    f"  [yellow]?[/yellow] #{r['id']:4d}  {r['name']!r}  "
                    f"→ Nominatim 解決失敗 ({lat:.4f}, {lon:.4f}) — skip"
                )
                continue
            if new_name == r["name"]:
                continue
            renames.append((r["id"], r["name"], new_name, f"{lat:.4f},{lon:.4f}"))
            _time.sleep(1.0)
        if not renames:
            console.print("[green]All place entities already have Nominatim-current names.[/green]")
            return
        console.print(f"[bold]{len(renames)} entit{'y' if len(renames)==1 else 'ies'} to rename:[/bold]\n")
        for eid, old, new, coords in renames:
            console.print(f"  #{eid:4d}  [red]{old!r}[/red] → [green]{new!r}[/green]  ({coords})")
        console.print()
        if dry_run:
            console.print("[yellow]--dry-run: no changes made[/yellow]")
            return
        with conn:
            for eid, _old, new, _coords in renames:
                clash = conn.execute(
                    "SELECT id FROM entities WHERE name = ? AND id != ?",
                    (new, eid),
                ).fetchone()
                if clash:
                    console.print(
                        f"  [yellow]![/yellow] #{eid}: target name {new!r} already used by #{clash['id']} "
                        f"— skipping rename. Run [cyan]bunshin merge-entities {eid} {clash['id']}[/cyan] to collapse."
                    )
                    continue
                conn.execute(
                    "UPDATE entities SET name = ? WHERE id = ?", (new, eid),
                )
        console.print(f"[green]✓ Renamed {len(renames)} entit{'y' if len(renames)==1 else 'ies'}[/green]")
    finally:
        conn.close()


@main.command("re-describe-all")
@click.option("--limit", type=int, default=200,
              help="Max entities to refresh (default 200, ≥ current 137).")
@click.option("--server", default="http://127.0.0.1:8000",
              help="Bunshin web server URL (must be running).")
@click.option("--timeout", type=int, default=180,
              help="Per-entity timeout (seconds).")
@click.option("--min-mentions", type=int, default=1,
              help="Skip entities with fewer mentions than this.")
def re_describe_all_cmd(limit: int, server: str, timeout: int, min_mentions: int):
    """Refresh every entity's AI description via the running web server.

    Uses the /api/entities/{id}/describe POST endpoint so this CLI inherits
    the latest describe prompt (v0.9.13 style guide + retry) without
    re-importing the multi-source pipeline. Entities are processed in
    descending mentions order. Bunshin.app or `bunshin web` must already
    be running.
    """
    import httpx
    import time

    try:
        r = httpx.get(f"{server}/api/entities", params={"limit": limit}, timeout=15)
        r.raise_for_status()
        entities = r.json().get("entities", [])
    except Exception as e:
        console.print(f"[red]Failed to reach {server}/api/entities:[/red] {e}")
        console.print("[yellow]Hint:[/yellow] Start Bunshin.app or run `bunshin web` first.")
        return

    entities = [e for e in entities if e.get("mentions", 0) >= min_mentions]
    entities.sort(key=lambda e: -e.get("mentions", 0))

    if not entities:
        console.print("[yellow]No entities to refresh.[/yellow]")
        return

    console.print(f"Refreshing [cyan]{len(entities)}[/cyan] entities (timeout {timeout}s each)…")

    ok = 0
    fail = 0
    skipped = 0
    started = time.monotonic()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("re-describe", total=len(entities))
        for ent in entities:
            eid = ent.get("id")
            name = ent.get("name", "?")
            try:
                r = httpx.post(
                    f"{server}/api/entities/{eid}/describe",
                    timeout=timeout,
                )
                if r.status_code == 200 and (r.json() or {}).get("description"):
                    ok += 1
                else:
                    fail += 1
                    console.print(f"  [red]✗[/red] {name} (id={eid}) status={r.status_code}")
            except httpx.TimeoutException:
                skipped += 1
                console.print(f"  [yellow]⏱[/yellow] {name} (id={eid}) timeout")
            except Exception as e:
                fail += 1
                console.print(f"  [red]✗[/red] {name} (id={eid}) {type(e).__name__}: {e}")
            progress.update(task, advance=1, description=f"[{ok}✓ {fail}✗ {skipped}⏱] {name[:24]}")

    elapsed = time.monotonic() - started
    console.print()
    table = Table(title="Re-describe complete")
    table.add_column("Metric"); table.add_column("Count", justify="right")
    table.add_row("Refreshed OK", str(ok))
    table.add_row("Failed", str(fail))
    table.add_row("Timed out", str(skipped))
    table.add_row("Elapsed", f"{elapsed/60:.1f} min ({elapsed:.0f}s)")
    table.add_row("Avg per entity", f"{elapsed/max(1,len(entities)):.1f}s")
    console.print(table)


@main.command("update")
@click.option(
    "--claude-path",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.home() / ".claude" / "projects",
    help="Path to Claude Code projects directory",
)
@click.option(
    "--files-path",
    type=click.Path(file_okay=False, path_type=Path),
    default=lambda: Path.home() / "Documents",
    help="Path to scan for markdown / text files (default: ~/Documents)",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
@click.option("--no-files", is_flag=True, help="Skip file ingestion")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (for cron)")
def update_cmd(
    claude_path: Path,
    files_path: Path,
    db: Path,
    no_files: bool,
    quiet: bool,
):
    """Incremental import + embed of Claude history AND local files.

    Idempotent — safe to run from cron/launchd. Skips unchanged sessions/files
    via mtime cache.
    """
    from datetime import datetime

    from bunshin.embeddings import DIMENSIONS, embed_passages

    start = datetime.now()
    conn = init_db(db)

    # 1) Claude history
    if claude_path.exists():
        c_stats = import_claude_history(conn, claude_path)
    else:
        c_stats = {"files_scanned": 0, "files_reimported": 0, "records_inserted": 0}

    # 2) Local files
    if no_files or not files_path.exists():
        f_stats = {"files_scanned": 0, "files_reimported": 0, "chunks_inserted": 0}
    else:
        f_stats = import_files(conn, files_path)

    # 3) Gmail (only if user has set up credentials)
    g_stats = {"fetched": 0, "imported": 0, "chunks_inserted": 0, "errors": 0}
    try:
        from bunshin.ingestion.gmail import import_gmail, load_credentials
        creds = load_credentials()
        if creds:
            g_stats = import_gmail(
                conn, creds["email"], creds["app_password"]
            )
    except Exception:
        pass

    # 4) Calendar (only if user has set up URL)
    cal_stats = {"fetched": 0, "imported": 0, "errors": 0}
    try:
        from bunshin.ingestion.calendar import import_calendar, load_url
        if load_url():
            cal_stats = import_calendar(conn)
    except Exception:
        pass

    # 5) Browser history (incremental — uses last_ts watermark in settings)
    browser_stats = {"inserted": 0}
    try:
        from bunshin.ingestion.browser import import_browser_history
        browser_stats = import_browser_history(conn)
    except Exception:
        pass

    # 6) Embed everything that lacks a vector
    init_vector_db(conn, dimensions=DIMENSIONS)
    pending = [
        (rid, text) for rid, text in get_records_without_vectors(conn)
        if len(text or "") >= 20
    ]
    embedded = 0
    if pending:
        batch_size = 32
        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            ids = [r[0] for r in batch]
            texts = [r[1] for r in batch]
            embeddings = list(embed_passages(texts))
            for rec_id, emb in zip(ids, embeddings):
                insert_vector(conn, rec_id, emb)
            conn.commit()
            embedded += len(batch)

    # Daily backup if today's snapshot doesn't exist yet.
    try:
        from bunshin.backup import DEFAULT_BACKUP_DIR, backup_db
        today_snap = DEFAULT_BACKUP_DIR / f"data-{start.strftime('%Y-%m-%d')}.db"
        backup_taken = False
        if not today_snap.exists():
            conn.commit()  # flush pending writes before vacuuming
            bk = backup_db(db, keep=7)
            backup_taken = bool(bk.get("backup_path")) and not bk.get("error")
    except Exception:
        backup_taken = False

    duration = (datetime.now() - start).total_seconds()
    summary = (
        f"claude_sessions={c_stats['files_reimported']} "
        f"claude_records={c_stats['records_inserted']} "
        f"files_reimported={f_stats['files_reimported']} "
        f"file_chunks={f_stats['chunks_inserted']} "
        f"gmail_imported={g_stats['imported']} "
        f"gmail_chunks={g_stats['chunks_inserted']} "
        f"cal_events={cal_stats['imported']} "
        f"browser_visits={browser_stats.get('inserted', 0)} "
        f"embedded={embedded} "
        f"backup={'yes' if backup_taken else 'no'} "
        f"duration={duration:.1f}s"
    )

    # Stamp for /api/status
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        ("last_update_at", str(int(start.timestamp()))),
    )
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        ("last_update_summary", summary),
    )
    conn.commit()
    conn.close()

    if quiet:
        click.echo(f"[bunshin update] {start.strftime('%Y-%m-%d %H:%M:%S')} {summary}")
    else:
        console.print(f"[green]Update complete[/green]: {summary}")


@main.command("mcp")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=DEFAULT_DB_PATH,
    help="Database file path",
)
def mcp_cmd(db: Path):
    """Start the MCP server (stdio) for Claude Code / Desktop integration."""
    if not db.exists():
        click.echo(f"No database at {db}. Run `bunshin init` first.", err=True)
        return

    # IMPORTANT: stdout is reserved for MCP protocol. Don't print anything to it.
    from bunshin.mcp.server import run
    run(db)


if __name__ == "__main__":
    main()
