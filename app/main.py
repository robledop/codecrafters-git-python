import datetime
import enum
import sys
import os
import zlib
from hashlib import sha1
import time

GIT_AUTHOR_EMAIL = "robledo@gmail.com"
GIT_AUTHOR_NAME = "Robledo Pazotto"


class Mode(enum.IntEnum):
    FILE = 100644
    EXECUTABLE = 100755
    SYMLINK = 120000
    DIRECTORY = 40000


class TreeEntry:
    def __init__(self, mode, name, item_hash):
        self.mode: Mode = mode
        self.name: str = name
        self.hash: bytes = item_hash


def main():
    command = sys.argv[1]
    if command == "init":
        os.mkdir(".git")
        os.mkdir(".git/objects")
        os.mkdir(".git/refs")
        with open(".git/HEAD", "w") as f:
            f.write("ref: refs/heads/main\n")
        print("Initialized git directory")
    elif command == "cat-file" and sys.argv[2] == "-p":
        object_hash = sys.argv[3]
        # The first 2 chars of the hash is the folder, and the remaining is the file name
        path = f".git/objects/{object_hash[:2]}/{object_hash[2:]}"
        with open(path, "rb") as f:
            decompressed = zlib.decompress(f.read())
            header, data = decompressed.split(b"\0", maxsplit=1)
            print(data.decode(), end="")
    elif command == "hash-object" and sys.argv[2] == "-w":
        file_name = sys.argv[3]
        sha_hash = hash_file(file_name)
        print(sha_hash, end="")

    elif command == "ls-tree":
        param, tree_hash = sys.argv[2], sys.argv[3]
        tree_items = []
        with open(f".git/objects/{tree_hash[:2]}/{tree_hash[2:]}", "rb") as f:
            decompressed = zlib.decompress(f.read())
            header, data = decompressed.split(b"\0", maxsplit=1)
            if header[:4] == b"tree":
                while data:
                    header, data = data.split(b"\0", maxsplit=1)
                    mode, name = header.split(b" ", maxsplit=1)
                    mode = int(mode)
                    name = name.decode()
                    item_hash = data[:20]

                    tree_items.append(TreeEntry(mode, name, item_hash))
                    print(
                        f"Tree entry name: {name}, mode: {mode}, hash: {item_hash.hex()}",
                        file=sys.stderr,
                    )

                    data = data[20:]

            if param == "--name-only":
                for item in tree_items:
                    print(item.name)
            else:
                for item in tree_items:
                    print(f"{item.mode} ", end="")
                    if item.mode == Mode.DIRECTORY:
                        print("tree ", end="")
                    else:
                        print("blob ", end="")
                    print(f"{item.hash.hex()}\t{item.name}")

    elif command == "write-tree":
        tree = hash_tree(os.getcwd())
        hashed = sha1(tree).hexdigest()
        print(hashed, end="")
        folder_path = f".git/objects/{hashed[:2]}"
        hashed_file_name = hashed[2:]
        os.makedirs(folder_path, exist_ok=True)
        with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
            hf.write(zlib.compress(tree))

    elif command == "commit-tree":
        tree_sha, p, commit_sha, m, commit_message = sys.argv[2:]

        content = (
            f"tree {tree_sha}\n"
            f"parent {commit_sha}\n"
            f"author {GIT_AUTHOR_NAME} <{GIT_AUTHOR_EMAIL}> {int(time.time())} {time.timezone} "
            f"commiter {GIT_AUTHOR_NAME} <{GIT_AUTHOR_EMAIL}> {int(time.time())} {time.timezone}\n\n"
            f"{commit_message}\n"
        )

        tree = f"commit {len(content)}\0{content}"

        folder_path = f".git/objects/{tree_sha[:2]}"
        hashed_file_name = tree_sha[2:]

        with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
            hf.write(zlib.compress(tree.encode()))

        print(tree_sha, end="")

    else:
        raise RuntimeError(f"Unknown command #{command}")


def hash_tree(path, write=True):
    dir_items = os.listdir(path)
    git_items = []
    for item in dir_items:
        if item == ".git":
            continue
        if os.path.isfile(os.path.join(path, item)):
            print(f"file {item}", file=sys.stderr)
            file_hash = hash_file(os.path.join(path, item), write)
            git_items.append(
                TreeEntry(
                    Mode.FILE,
                    item,
                    file_hash,
                )
            )
        elif os.path.isdir(os.path.join(path, item)):
            print(f"directory {item}", file=sys.stderr)
            tree = hash_tree(os.path.join(path, item))
            git_items.append(TreeEntry(Mode.DIRECTORY, item, sha1(tree).hexdigest()))

    git_items.sort(key=lambda i: i.name)

    tree_content = b""
    for item in git_items:
        tree_content += f"{str(item.mode)} {item.name}\0".encode()
        tree_content += int.to_bytes(int(item.hash, 16), length=20, byteorder="big")

    tree = f"tree {str(len(tree_content))}\0".encode() + tree_content

    return tree


def hash_file(path, write=True):
    with open(path, "r") as f:
        file_content = f.read()
        to_be_hashed = f"blob {len(file_content)}\0{file_content}".encode()
        sha_hash = sha1(to_be_hashed).hexdigest()
        if write:
            folder_path = f".git/objects/{sha_hash[:2]}"
            hashed_file_name = sha_hash[2:]
            os.makedirs(folder_path, exist_ok=True)
            with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
                hf.write(zlib.compress(to_be_hashed))

        return sha_hash


if __name__ == "__main__":
    main()
