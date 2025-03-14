import enum
import sys
import os
import zlib
from hashlib import sha1


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
            print(data.decode(encoding="utf-8"), end="")
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
                    name = name.decode("utf-8")
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
        current_dir = os.getcwd()
        tree, tree_hash = hash_directory(current_dir)
        print(tree, file=sys.stderr)
        print(tree_hash, end="")
        folder_path = f".git/objects/{tree_hash[:2]}"
        hashed_file_name = tree_hash[2:]
        if not os.path.exists(folder_path):
            os.mkdir(folder_path)
        with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
            hf.write(zlib.compress(tree))

    else:
        raise RuntimeError(f"Unknown command #{command}")


def hash_directory(path):
    dir_items = os.listdir(path)
    git_items = []
    for item in dir_items:
        if item == ".git":
            continue
        if os.path.isfile(os.path.join(path, item)):
            print(f"file {item}", file=sys.stderr)
            file_hash = hash_file(os.path.join(path, item))
            git_items.append(
                TreeEntry(
                    Mode.FILE,
                    item,
                    file_hash,
                )
            )
        elif os.path.isdir(os.path.join(path, item)):
            print(f"directory {item}", file=sys.stderr)
            _, h = hash_directory(os.path.join(path, item))
            git_items.append(TreeEntry(Mode.DIRECTORY, item, h))

    git_items.sort(key=lambda i: i.name)

    tree_content = b""
    for item in git_items:
        tree_content += f"{str(item.mode)} {item.name}\0".encode()
        tree_content += int.to_bytes(int(item.hash, 16), length=20, byteorder="big")

    tree = f"tree {str(len(tree_content))}\0".encode() + tree_content

    return tree, sha1(tree).hexdigest()


def hash_file(path):
    with open(path, "r") as f:
        file_content = f.read()
        to_be_hashed = f"blob {len(file_content)}\0{file_content}".encode("utf-8")
        sha_hash = sha1(to_be_hashed).hexdigest()
        folder_path = f".git/objects/{sha_hash[:2]}"
        hashed_file_name = sha_hash[2:]
        if not os.path.exists(folder_path):
            os.mkdir(folder_path)
        with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
            hf.write(zlib.compress(to_be_hashed))

        return sha_hash


if __name__ == "__main__":
    main()
