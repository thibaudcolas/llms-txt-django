#!/usr/bin/env -S uv run
# /// script
# dependencies = ["tiktoken"]
# ///
"""Create an abridged version of llms-full.txt by removing releases and internals."""

import os
import re
import tiktoken


def parse_llms_txt(content):
    """Parse llms.txt to extract file paths and titles."""
    entries = []
    for line in content.split("\n"):
        # Match lines like: - [Title](path/index.html.md): description
        match = re.match(r"^- \[(.+?)\]\((.+?)\):", line)
        if match:
            title, path = match.groups()
            entries.append({"title": title, "path": path})
    return entries


def get_sections_to_remove(entries):
    """Get list of titles for sections to remove (releases and internals)."""
    titles_to_remove = set()
    for entry in entries:
        path = entry["path"]
        if path.startswith("releases/") or path.startswith("internals/"):
            titles_to_remove.add(entry["title"])
    return titles_to_remove


def split_into_sections(content):
    """Split llms-full.txt into sections based on # index.html.md markers."""
    sections = []
    current_section = []
    current_title = None
    
    for line in content.split("\n"):
        if line == "# index.html.md":
            # Save previous section if it exists
            if current_section and current_title:
                sections.append({
                    "title": current_title,
                    "content": "\n".join(current_section)
                })
            current_section = [line]
            current_title = None
        elif current_section and current_title is None and line.startswith("# "):
            # This is the actual title line after # index.html.md
            current_title = line[2:].strip()
            current_section.append(line)
        else:
            current_section.append(line)
    
    # Don't forget the last section
    if current_section and current_title:
        sections.append({
            "title": current_title,
            "content": "\n".join(current_section)
        })
    
    return sections


def count_tokens(encoder, text):
    """Count tokens in text."""
    return len(encoder.encode(text))


def main():
    encoder = tiktoken.get_encoding("o200k_base")
    build_dir = "django/docs/_build/dirhtml"
    
    # Read source files
    with open(os.path.join(build_dir, "llms.txt"), "r") as f:
        llms_txt = f.read()
    
    with open(os.path.join(build_dir, "llms-full.txt"), "r") as f:
        llms_full = f.read()
    
    # Parse llms.txt to get titles and paths
    entries = parse_llms_txt(llms_txt)
    print(f"Found {len(entries)} entries in llms.txt")
    
    # Get titles to remove
    titles_to_remove = get_sections_to_remove(entries)
    print(f"Sections to remove: {len(titles_to_remove)}")
    
    # Split llms-full.txt into sections
    sections = split_into_sections(llms_full)
    print(f"Found {len(sections)} sections in llms-full.txt")
    
    # Filter sections
    kept_sections = []
    removed_sections = []
    for section in sections:
        if section["title"] in titles_to_remove:
            removed_sections.append(section)
        else:
            kept_sections.append(section)
    
    print(f"Keeping {len(kept_sections)} sections, removing {len(removed_sections)}")
    
    # Build abridged content
    abridged_content = "\n\n".join(s["content"] for s in kept_sections)
    
    # Write abridged files
    with open("llms-full-abridged.txt", "w") as f:
        f.write(abridged_content)
    
    # Create abridged llms.txt (sitemap)
    abridged_entries = [e for e in entries if e["title"] not in titles_to_remove]
    llms_abridged_lines = ["# Django (Abridged)", "", "> Django documentation - core documentation only", "", "## Pages", ""]
    for entry in abridged_entries:
        llms_abridged_lines.append(f"- [{entry['title']}]({entry['path']})")
    
    with open("llms-abridged.txt", "w") as f:
        f.write("\n".join(llms_abridged_lines))
    
    # Token counts
    print("\n" + "=" * 60)
    print("TOKEN COUNTS")
    print("=" * 60)
    
    original_tokens = count_tokens(encoder, llms_full)
    abridged_tokens = count_tokens(encoder, abridged_content)
    removed_tokens = original_tokens - abridged_tokens
    
    print(f"\nOriginal llms-full.txt: {original_tokens:,} tokens")
    print(f"Abridged version:       {abridged_tokens:,} tokens")
    print(f"Removed:                {removed_tokens:,} tokens ({removed_tokens/original_tokens*100:.1f}%)")
    
    # Token counts per top-level section
    print("\n" + "-" * 60)
    print("TOKENS BY SECTION (in abridged version)")
    print("-" * 60)
    
    section_tokens = {}
    for section in kept_sections:
        # Get top-level category from title or group by prefix
        title = section["title"]
        tokens = count_tokens(encoder, section["content"])
        section_tokens[title] = tokens
    
    # Group by top-level path prefix
    path_groups = {}
    for entry in abridged_entries:
        path = entry["path"]
        title = entry["title"]
        
        # Get top-level prefix
        parts = path.split("/")
        if len(parts) > 1:
            prefix = parts[0]
        else:
            prefix = "root"
        
        if prefix not in path_groups:
            path_groups[prefix] = {"titles": [], "tokens": 0}
        path_groups[prefix]["titles"].append(title)
    
    # Sum tokens per group
    for prefix, group in path_groups.items():
        total = 0
        for title in group["titles"]:
            if title in section_tokens:
                total += section_tokens[title]
        group["tokens"] = total
    
    # Print sorted by token count
    for prefix, group in sorted(path_groups.items(), key=lambda x: x[1]["tokens"], reverse=True):
        print(f"{prefix:20} {group['tokens']:>10,} tokens ({len(group['titles']):>3} docs)")
    
    print("\n" + "-" * 60)
    print("TOP 20 LARGEST INDIVIDUAL SECTIONS")
    print("-" * 60)
    
    for title, tokens in sorted(section_tokens.items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"{tokens:>8,} tokens - {title}")
    
    print(f"\nAbridged files written:")
    print(f"  - llms-abridged.txt")
    print(f"  - llms-full-abridged.txt")


if __name__ == "__main__":
    main()
