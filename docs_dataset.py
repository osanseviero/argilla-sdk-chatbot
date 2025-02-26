r"""Script to generate a dataset from the markdown docs files in a repository.

Usage:
$ python docs_dataset.py -h

Example:
$ python docs_dataset.py \
    "argilla-io/argilla-python" \
    --dataset-name "plaguss/argilla_sdk_docs_raw_unstructured"

$ python docs_dataset.py \
    "argilla-io/argilla-python" \
    "argilla-io/distilabel" \
    --dataset-name "plaguss/argilla_sdk_docs_raw_unstructured"

$ python docs_dataset.py \
    "argilla-io/argilla" \
    --docs_folder "argilla/docs" \
    --dataset-name "plaguss/argilla_sdk_docs_raw_dev"
"""

import pandas as pd
from datasets import Dataset, concatenate_datasets

from github import Github, Repository, ContentFile
import requests
import os

from typing import List, Optional

from pathlib import Path


# The github related functions are a copy from the following repository
# https://github.com/Nordgaren/Github-Folder-Downloader/blob/master/gitdl.py
def download(c: ContentFile, out: str) -> None:
    r = requests.get(c.download_url)
    output_path = f"{out}/{c.path}"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        print(f"downloading {c.path} to {out}")
        f.write(r.content)


def download_folder(repo: Repository, folder: str, out: str, recursive: bool) -> None:
    contents = repo.get_contents(folder)
    for c in contents:
        if c.download_url is None:
            if recursive:
                download_folder(repo, c.path, out, recursive)
            continue
        download(c, out)


def create_chunks(md_files: List[Path]) -> dict[str, List[str]]:
    """Create the chunks of text from the markdown files.

    Note:
        We should allow the chunking strategy to take into account the max size delimited
        by the number of tokens.

    Args:
        md_files: List of paths to the markdown files.

    Returns:
        Dictionary from filename to the list of chunks.
    """
    from unstructured.chunking.title import chunk_by_title
    from unstructured.partition.auto import partition
    data = {}
    for file in md_files:
        partitioned_file = partition(filename=file)
        chunks = [str(chunk) for chunk in chunk_by_title(partitioned_file)]

        data[str(file)] = chunks
    return data


def create_dataset(data: dict[str, List[str]], repo_name: Optional[str] = None) -> Dataset:
    """Creates a dataset from the dictionary of chunks.

    Args:
        data: Dictionary from filename to the list of chunks,
            as obtained from `create_chunks`.

    Returns:
        Dataset with `filename` and `chunks` columns.
    """
    df = pd.DataFrame.from_records(
        [(k, v) for k, values in data.items() for v in values],
        columns=["filename", "chunks"],
    )
    if repo_name:
        df["repo_name"] = repo_name
    ds = Dataset.from_pandas(df)
    return ds


def main():
    import argparse

    description = (
        "Download the docs from a github repository and generate a dataset "
        "from the markdown files. The dataset will be pushed to the hub."
    )
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "repo",
        nargs="+",
        help="Name of the repository in the hub. For example 'argilla-io/argilla-python'.",
    )
    parser.add_argument(
        "--dataset-name",
        help="Name to give to the new dataset. For example 'my-name/argilla_sdk_docs_raw'.",
    )
    parser.add_argument(
        "--docs_folder",
        default="docs",
        help="Name of the docs folder in the repo, defaults to 'docs'.",
    )
    parser.add_argument(
        "--output_dir",
        help="Path to save the downloaded files from the repo (optional)",
    )
    parser.add_argument(
        "--private",
        action=argparse.BooleanOptionalAction,
        help="Whether to keep the repository private or not. Defaults to False.",
    )

    args = parser.parse_args()

    # Instantiate the Github object to download the files
    dss = []
    print("Instantiate repository...")
    for repo_name in args.repo:
        gh = Github()
        repo = gh.get_repo(repo_name)

        docs_path = Path(args.output_dir or repo_name.split("/")[1])

        if docs_path.exists():
            print(f"Folder {docs_path} already exists, skipping download.")
        else:
            print("Start downloading the files...")
            download_folder(repo, args.docs_folder, str(docs_path), True)

        md_files = list(docs_path.glob("**/*.md"))

        # Loop to iterate over the files and generate chunks from the text pieces
        print("Generating the chunks from the markdown files...")
        data = create_chunks(md_files)

        # Create a dataset to push it to the hub
        print("Creating dataset...")
        dss.append(create_dataset(data, repo_name=repo_name))

    ds = concatenate_datasets(dss)
    # Create multiple datasets and merge them
    ds.push_to_hub(args.dataset_name, private=args.private)
    print("Dataset pushed to the hub")


if __name__ == "__main__":
    main()
