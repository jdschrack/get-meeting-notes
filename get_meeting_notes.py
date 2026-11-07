#!/usr/bin/env python3 

"""
get_meeting_notes.py 

Downloads files from a specific Google Drive Folder using the `gws` CLI,
and converts the document to markdown.
"""

import argparse 
import json
import os
import subprocess
import sys 
import tempfile 

from pathlib import Path
from datetime import datetime, timezone

def run_gws_command(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["gws"] + args 
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command {' '.join(cmd)} failed:\n{result.stderr}")
    return result

def resolve_folder_id(folder_identifier: str) -> str:
    if len(folder_identifier) >= 25 and " " not in folder_identifier:
        return folder_identifier

    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_identifier}' and trashed = false"
    res = run_gws_command([
        "drive", "files", "list",
        "--params", json.dumps({"q": query, "fields": "files(id, name)"}),
        "--format", "json"
        ])

    data = json.loads(res.stdout)
    files = data.get("files", [])
    if not files:
        raise ValueError(f"no drive folder found matching name: '{folder_identifier}")

    folder_id = files[0]["id"]
    print(f"[*] found folder '{files[0]['name']}' (ID: {folder_id})")
    return folder_id

def parse_rfc3339_date(date_str: str, is_end_of_day: bool = False) -> str:
    date_str = date_str.strip()
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError as e:
        raise ValueError(
            f"Invalid date format '{date_str}'. Expected YYYY-MM-DD or ISO 8601 format."
        ) from e

    if len(date_str) <= 10:
        if is_end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        else:
            dt = dt.replace(hour=0, minute=0, second=0)

    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def list_google_docs(
        folder_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
    query_parts = [
        f"'{folder_id}' in parents",
        "mimeType = 'application/vnd.google-apps.document'",
        "trashed = false",
    ]

    if start_date:
        start_rfc = parse_rfc3339_date(start_date, is_end_of_day=False)
        query_parts.append(f"createdTime >= '{start_rfc}'")

    if end_date:
        end_rfc = parse_rfc3339_date(end_date, is_end_of_day=True)
        query_parts.append(f"createdTime <= '{end_rfc}'")

    full_query = " and ".join(query_parts)

    cmd: list[str] = [
        "drive",
        "files",
        "list",
        "--params",
        json.dumps({
            "q": full_query,
            "fields": "files(id, name, createdTime)",
            "pageSize": 100,
        }),
        "--format",
        "json",
    ]

    res = run_gws_command(cmd)

    data = json.loads(res.stdout)
    return data.get("files", [])

def export_doc_to_markdown(file_info: dict, output_dir: Path):
    file_id = file_info["id"]
    name = file_info["name"]
    created_time = file_info.get("createdTime", "unknown")

    clean_name = Path(name.replace("/", "-")).stem
    output_path = output_dir / f"{clean_name}.md"

    run_gws_command([
        "drive", "files", "export", 
        "--params", json.dumps({"fileId": file_id, "mimeType": "text/markdown"}),
        "-o", str(output_path)
        ])
    print(f"[✓] Exported: {name} {created_time} -> {output_path.name}")

def main():
    parser = argparse.ArgumentParser(
    description="Download only Google Docs from a Drive folder and export them directly to Markdown."
            )
    parser.add_argument("folder", help="Goggle Drive Folder Name or Folder Id.")
    parser.add_argument(
            "-o", "--output", default="./markdown_output",
            help="Local directory where Markdown files will be saved (default: ./markdown_output)."
            )

    parser.add_argument(
        "--start-date",
        help="Earliest creation date (format: YYYY-MM-DD or ISO 8601).",
    )
    parser.add_argument(
        "--end-date",
        help="Latest creation date (format: YYYY-MM-DD or ISO 8601).",
    )

    args = parser.parse_args()

    try:
        run_gws_command(["--version"])
    except FileNotFoundError:
        print("GWS must be installed and authenticated")
        sys.exit(1)

    output_path = Path(args.output).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    folder_id = resolve_folder_id(args.folder)
    docs = list_google_docs(folder_id, start_date=args.start_date, end_date=args.end_date)

    if not docs:
        print("No google docs found in the specified folder")
        sys.exit(1)

    print(f"[*] Found {len(docs)} Google Doc(s). Exporting...")

    for doc in docs:
        try:
            export_doc_to_markdown(doc, output_path)
        except Exception as e:
            print(f"[!] Error processing {doc.get('name', doc['id'])}: {e}", file=sys.stderr)

    print(f"\n[DONE] Markdown files saved to {output_path}")

if __name__ == "__main__":
    main()
