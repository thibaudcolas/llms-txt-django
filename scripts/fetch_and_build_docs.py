#!/usr/bin/env -S uv run
# /// script
# dependencies = ["httpx", "tiktoken"]
# ///
"""Fetch the latest Django version and build its documentation."""

import httpx
import io
import json
import os
import re
import subprocess
import tiktoken
import zipfile


def get_latest_django_version():
    """Fetch the latest Django version from the Ecosystem API."""
    url = "https://packages.ecosyste.ms/api/v1/registries/pypi.org/packages/django/versions/?per_page=10"
    response = httpx.get(url)
    response.raise_for_status()

    for v in response.json():
        if v.get("latest"):
            return v["number"]

    raise ValueError("Could not find latest Django version")


def download_django_source(version):
    """Download Django source code from GitHub as a ZIP file."""
    url = f"https://github.com/django/django/archive/refs/tags/{version}.zip"
    response = httpx.get(url, follow_redirects=True)
    response.raise_for_status()

    return response.content


def extract_zip(zip_content):
    """Extract the ZIP content and rename to 'django'."""
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
        zip_ref.extractall(".")

    # Find the extracted directory (starts with "django-") and rename to "django"
    for item in os.listdir("."):
        if item.startswith("django-") and os.path.isdir(item):
            if os.path.exists("django"):
                import shutil

                shutil.rmtree("django")
            os.rename(item, "django")
            return "django"

    raise FileNotFoundError("Could not find extracted Django directory")


def install_dependencies(extracted_dir):
    """Install documentation dependencies using uv."""
    requirements_path = os.path.join(extracted_dir, "docs", "requirements.txt")
    subprocess.run(
        ["uv", "pip", "install", "-r", requirements_path, "sphinx-llm"], check=True
    )


def modify_conf_py(extracted_dir):
    """Modify docs/conf.py to add sphinx_llm.txt to extensions."""
    conf_path = os.path.join(extracted_dir, "docs", "conf.py")

    with open(conf_path, "r") as f:
        content = f.read()

    # Find the extensions list and add sphinx_llm.txt
    # This regex looks for the closing bracket of the extensions list
    pattern = r"(\s+\]\s*)"
    replacement = r'    "sphinx_llm.txt",\n\1'

    if '"sphinx_llm.txt"' not in content:
        content = re.sub(pattern, replacement, content, count=1)

        with open(conf_path, "w") as f:
            f.write(content)


def build_docs(docs_dir):
    """Build the Django documentation."""
    os.chdir(docs_dir)
    subprocess.run(["make", "dirhtml"], check=True)


def count_tokens_in_files(docs_dir, build_dir="_build/dirhtml"):
    """Count tokens in all documentation files using tiktoken o200k_base encoding."""
    encoder = tiktoken.get_encoding("o200k_base")
    build_path = os.path.join(docs_dir, build_dir)

    def count_file(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return len(encoder.encode(f.read()))
        except Exception:
            return 0

    def count_if_exists(path):
        return count_file(path) if os.path.exists(path) else 0

    if not os.path.exists(build_path):
        print(f"Error: Build directory {build_path} does not exist")
        return {}, {}, 0

    # Collect all doc paths by finding index.html files
    doc_paths = set()
    for root, dirs, files in os.walk(build_path):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        if "index.html" in files:
            rel_dir = os.path.relpath(root, build_path)
            if rel_dir != ".":
                doc_paths.add(rel_dir)

    # Count tokens for each doc in three formats
    doc_tokens = {}
    total_tokens = 0

    for doc_path in doc_paths:
        source_path = os.path.join(build_path, "_sources", f"{doc_path}.txt")
        if not os.path.exists(source_path):
            source_path = os.path.join(build_path, "_sources", doc_path, "index.txt")

        counts = {
            "source": count_if_exists(source_path),
            "html": count_if_exists(os.path.join(build_path, doc_path, "index.html")),
            "markdown": count_if_exists(
                os.path.join(build_path, doc_path, "index.html.md")
            ),
        }
        doc_tokens[doc_path] = counts
        total_tokens += sum(counts.values())

    # Count llms.txt files separately
    llms_tokens = {
        name: count_if_exists(os.path.join(build_path, name))
        for name in ["llms.txt", "llms-full.txt"]
    }
    total_tokens += sum(llms_tokens.values())

    return doc_tokens, llms_tokens, total_tokens


def generate_reports(doc_tokens, llms_tokens, total_tokens):
    """Generate JSON and Markdown reports."""
    # Create report.json
    report_data = {
        "total_tokens": total_tokens,
        "llms_tokens": llms_tokens,
        "doc_tokens": doc_tokens,
        "doc_count": len(doc_tokens),
    }

    with open("report.json", "w") as f:
        json.dump(report_data, f, indent=2)

    # Create report.md
    with open("report.md", "w") as f:
        f.write("# Django Documentation Token Report\n\n")
        f.write(f"**Total Documents**: {len(doc_tokens)}\n\n")
        f.write(f"**Total Tokens**: {total_tokens:,}\n\n")

        # LLMs.txt section
        f.write("## LLMs.txt Files\n\n")
        f.write("| File | Tokens |\n")
        f.write("|------|-------:|\n")
        for file, count in sorted(llms_tokens.items()):
            f.write(f"| `{file}` | {count:,} |\n")
        f.write("\n")

        # Documentation files section
        f.write("## Documentation Files\n\n")
        f.write("| Path | Source | HTML | Markdown |\n")
        f.write("|------|-------:|-----:|---------:|\n")

        # Sort by path alphabetically
        for doc_path in sorted(doc_tokens.keys()):
            counts = doc_tokens[doc_path]
            f.write(
                f"| `{doc_path}` | {counts['source']:,} | {counts['html']:,} | {counts['markdown']:,} |\n"
            )


def main():
    """Main function to orchestrate the process."""
    # Store original working directory for later use
    original_cwd = os.path.abspath(os.getcwd())

    # print("Fetching latest Django version...")
    # latest_version = get_latest_django_version()
    # print(f"Latest Django version: {latest_version}")

    # print("Downloading Django source code...")
    # zip_content = download_django_source(latest_version)

    # print("Extracting source code...")
    # extracted_dir = extract_zip(zip_content)
    # # Convert to absolute path before build_docs changes cwd
    # extracted_dir = os.path.abspath("django")
    # print(f"Extracted to: {extracted_dir}")

    # print("Installing dependencies...")
    # install_dependencies(extracted_dir)

    # print("Modifying docs/conf.py...")
    # modify_conf_py(extracted_dir)

    docs_dir = os.path.join(os.path.abspath("django"), "docs")

    # print("Building documentation...")
    # build_docs(docs_dir)

    print("Counting tokens in documentation files...")
    doc_tokens, llms_tokens, total_tokens = count_tokens_in_files(docs_dir)

    # Change back to original directory for report generation
    os.chdir(original_cwd)

    print("Generating reports...")
    generate_reports(doc_tokens, llms_tokens, total_tokens)

    print(f"Documentation built successfully!")
    print(f"Total tokens: {total_tokens:,}")
    print(f"Reports generated: report.json and report.md")


if __name__ == "__main__":
    main()
